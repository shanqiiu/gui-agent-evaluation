import os
import time
import requests
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Tuple
from pyexpat.errors import messages

from .config import Config
from GUI_TestFramework_v1.api_service import mllm
from utils import cv_utils, json_utils, prompt_utils
from GUI_TestFramework_v1.api_service.prompts import single_image_prompts, ab_test_prompts
from GUI_TestFramework_v1.common.logger import default_logger as logger

import traceback
import sys


class ABPageValidator:
    def __init__(self, config: Config = None, max_workers: int = 5,
                 retry_times: int = 3):
        """
        初始化API验证器

        参数:
            config: config配置
            max_workers: 最大并发数（根据API的QPS限制调整）
            retry_times: 失败重试次数
        """
        self.config = config
        self.max_workers = max_workers  # 控制并发量，避免限流
        self.retry_times = retry_times  # 临时错误重试次数
        self.session = requests.Session()  # 复用会话，减少TCP连接开销
        self.session.headers = {"Content-Type": "application/json"}
        self.executor = None
        self.threading_lock = threading.Lock()

    def _call_single_api(self, image_pair: tuple[int, str, str, dict, None | str, str],
                         ab_test_results: dict = None):
        """
        调用API验证单个图像对（带重试机制）

        参数:
            image_pair: 图像对，如 (image_a_path, image_b_path)

        返回:
            包含验证结果的字典，格式:
            {"pair": (a, b), "success": True/False, "result": 验证结果/错误信息}
        """
        idx, img_a, img_b, action_info, img_a_raw, color = image_pair
        if action_info['parsed_action']['action_type'] not in ['click', 'long_press', 'type', 'set_text']:
            if action_info['parsed_action']['action_type'] in ['clarify', 'done', 'finished']:
                thought = '此处没有操作故无需判定'
                label = '符合预期'
                for _ in range(3):
                    try:
                        message = mllm.request_vlm(image=img_b,
                                                   user_query=single_image_prompts.page_des_prompt,
                                                   server_url=self.config.model.VLM_MODEL_URL,
                                                   model_name=self.config.model.VLM_MODEL_NAME)
                        parsed_res = json_utils.extract_json_from_string(message)
                        pageb_description = parsed_res['page_description']
                    except Exception as e:
                        logger.warning(f'ABPageValidator：API服务出现问题，重试...\n'
                                       f'message: {message}')
            elif action_info['parsed_action']['action_type'] in ['wait', 'do-nothing']:
                for _ in range(3):
                    try:
                        message = mllm.request_vlm(image=img_b,
                                                   user_query=single_image_prompts.wait_page_prompt,
                                                   server_url=self.config.model.VLM_MODEL_URL,
                                                   model_name=self.config.model.VLM_MODEL_NAME)
                        parsed_res = json_utils.extract_json_from_string(message)
                        thought = parsed_res['Answer']
                        pageb_description = parsed_res['page_description']
                        if thought in ['加载失败', '毛玻璃', '加载中']:
                            label = '不符合预期'
                        else:
                            label = '符合预期'
                    except Exception as e:
                        logger.warning(f'ABPageValidator：API服务出现问题，重试...\n'
                                       f'message: {message}')
            elif action_info['parsed_action']['action_type'] in ['scroll', 'swipe', 'drag']:
                thought = '此处为滑动操作'
                label = '符合预期'
                for _ in range(3):
                    try:
                        message = mllm.request_vlm(image=img_b,
                                                   user_query=single_image_prompts.page_des_prompt,
                                                   server_url=self.config.model.VLM_MODEL_URL,
                                                   model_name=self.config.model.VLM_MODEL_NAME)
                        parsed_res = json_utils.extract_json_from_string(message)
                        pageb_description = parsed_res['page_description']
                    except Exception as e:
                        logger.warning(f'ABPageValidator：API服务出现问题，重试...\n'
                                       f'message: {message}')
            else:
                raise ValueError(f"action type: {action_info['parsed_action']['action_type']} is illegal!")
            if idx == 0:
                for _ in range(3):
                    try:
                        message = mllm.request_vlm(user_query=single_image_prompts.page_des_prompt,
                                                   image=img_a_raw,
                                                   server_url=self.config.model.VLM_MODEL_URL,
                                                   model_name=self.config.model.VLM_MODEL_NAME)
                        parsed_res = json_utils.extract_json_from_string(message)
                        # print(thought)
                        pagea_description = parsed_res['page_description']

                        self.threading_lock.acquire()
                        ab_test_results[str(idx)] = {'thought': thought, 'label': label,
                                                     'action_des': None,
                                                     'pagea_description': pagea_description,
                                                     'pageb_description': pageb_description}
                        self.threading_lock.release()
                        return
                    except Exception as e:
                        logger.warning(f'ABPageValidator：API服务出现问题，重试...\n'
                                       f'message: {message}')
            self.threading_lock.acquire()
            ab_test_results[str(idx)] = {'thought': thought, 'label': label,
                                         'action_des': None,
                                         'pagea_description': None, 'pageb_description': pageb_description}
            self.threading_lock.release()
            return
        else:
            for _ in range(3):

                try:
                    first_page = True if idx == 0 else False

                    # 设置request_vlm参数
                    action_description = prompt_utils.make_action_description(action_info)
                    if 'start_box' in action_info['parsed_action'] and action_info['parsed_action']['start_box'] and \
                            action_info['parsed_action']['action_type'] in ['click', 'long_press']:
                        prompt1 = ab_test_prompts.deep_oracle_prompt1_w_vp.format(color=color)
                        prompt2 = ab_test_prompts.deep_oracle_prompt2_w_vp
                        prompt3 = ab_test_prompts.deep_oracle_prompt3_w_vp

                        if action_info['parsed_action']['action_type'] == 'long_press':
                            action_type = '长按'
                        else:
                            action_type = '点击'
                        prompt3 = prompt3.format(action_info=action_description, action_type=action_type, color=color)
                    else:
                        prompt1 = ab_test_prompts.deep_oracle_prompt1_wo_vp
                        prompt2 = ab_test_prompts.deep_oracle_prompt2_wo_vp
                        prompt3 = ab_test_prompts.deep_oracle_prompt3_wo_vp
                        prompt3 = prompt3.format(action_info=action_description)
                    ###
                    message = mllm.request_vlm_ab_test(img1_path=img_a,
                                                       img2_path=img_b,
                                                       prompt1=prompt1,
                                                       prompt2=prompt2,
                                                       prompt3=prompt3,
                                                       server_url=self.config.model.VLM_MODEL_URL,
                                                       model_name=self.config.model.VLM_MODEL_NAME)
                    parsed_res = json_utils.extract_json_from_string(message)
                    if not parsed_res:
                        parsed_res = json_utils.extract_thought_and_answer(message)
                    thought = parsed_res['Thought']
                    label = parsed_res['Answer']
                    action_des = parsed_res['ActionDescription'] if 'ActionDescription' in parsed_res else None
                    pagea_description = None
                    pageb_description = parsed_res['PageB_Content']
                    if first_page:
                        message = mllm.request_vlm(user_query=single_image_prompts.page_des_prompt,
                                                   image=img_a_raw,
                                                   server_url=self.config.model.VLM_MODEL_URL,
                                                   model_name=self.config.model.VLM_MODEL_NAME)
                        parsed_res = json_utils.extract_json_from_string(message)
                        pagea_description = parsed_res['page_description']

                    self.threading_lock.acquire()
                    ab_test_results[str(idx)] = {'thought': thought, 'label': label,
                                                 'action_des': action_des,
                                                 'pagea_description': pagea_description,
                                                 'pageb_description': pageb_description}
                    self.threading_lock.release()
                    return
                except Exception as e:
                    logger.warning(f'ABPageValidator：API服务出现问题，重试...\n'
                                   f'e: {e}\n'
                                   f'message: {message}')
            self.threading_lock.acquire()
            ab_test_results[str(idx)] = {'thought': 'API服务出现问题', 'label': '无法判定',
                                         'action_des': None,
                                         'pagea_description': None, 'pageb_description': None}
            self.threading_lock.release()
            return

    def _worker(self, image_pairs: list = None, ab_test_results: dict = None):

        while len(image_pairs) > 0:
            self.threading_lock.acquire()
            try:
                this_image_pair = image_pairs.pop()
            except Exception as e:
                self.threading_lock.release()
                return
            self.threading_lock.release()
            self._call_single_api(image_pair=this_image_pair, ab_test_results=ab_test_results)

    def validate_all_pairs(self, image_pairs: list[tuple[int, str, str, dict, None | str, str]]):
        """
        并行验证所有图像对

        参数:
            image_pairs: 所有待验证的图像对列表，如 [(a1, b1), (a2, b2), ...]

        返回:
            成功结果列表和失败结果列表
        """
        ab_test_results = {}

        threading_list = list()

        actual_worker_number = min(self.max_workers, len(image_pairs))
        for _ in range(actual_worker_number):
            threading_list.append(
                threading.Thread(target=self._worker, args=(image_pairs, ab_test_results), daemon=True)
            )
        for p in threading_list:
            p.start()

        for p in threading_list:
            p.join()

        sorted_ids = sorted(ab_test_results.keys(), key=lambda x: int(x))
        consecutive_waiting = []  # 存储连续等待加载的索引范围

        start_idx = None
        for i, img_id in enumerate(sorted_ids):
            thought = ab_test_results[img_id]['thought']
            if thought == '正常':
                if i - 1 >= 0:
                    if ab_test_results[sorted_ids[i - 1]]['label'] == '不符合预期':
                        ab_test_results[sorted_ids[i - 1]]['label'] = '符合预期'
                        ab_test_results[sorted_ids[i - 1]]['thought'] = '虽然下一张页面处于加载中，但是再下面一张页面加载出来了，所以符合预期。'

        return ab_test_results


# 示例用法
if __name__ == "__main__":
    # 配置
    API_URL = "https://your-api-domain.com/ab_pages_validate"  # 替换为实际API地址
    MAX_WORKERS = 15  # 根据API的QPS限制调整（如API允许每秒20次，则设为15较安全）
    RETRY_TIMES = 3

    # 待验证的图像对列表（示例）
    image_pairs_main = [
        ("images/a1.jpg", "images/b1.jpg"),
        ("images/a2.jpg", "images/b2.jpg"),
        # ... 更多图像对 ...
    ]

    # 初始化验证器并执行
    validator = ABPageValidator(API_URL, MAX_WORKERS, RETRY_TIMES)
    start_time = time.time()
    successes, fails = validator.validate_all_pairs(image_pairs_main)
    end_time = time.time()

    # 输出统计结果
    print(f"\n总耗时: {end_time - start_time:.2f}秒")
    print(f"成功验证: {len(successes)}/{len(image_pairs_main)}")
    print(f"验证失败: {len(fails)}/{len(image_pairs_main)}")

    # 可选：保存失败结果到文件
    if fails:
        with open("validation_fails.txt", "w") as f:
            for fail in fails:
                f.write(f"Pair: {fail['pair']} | Error: {fail['result']}\n")
        print("失败详情已保存到 validation_fails.txt")
