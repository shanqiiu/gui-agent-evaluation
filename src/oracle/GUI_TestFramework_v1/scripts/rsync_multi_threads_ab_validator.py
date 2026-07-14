import threading
import time

from .config import Config
from GUI_TestFramework_v1.api_service import mllm
from GUI_TestFramework_v1.api_service.prompts import single_image_prompts, ab_test_prompts
from GUI_TestFramework_v1.common.logger import default_logger as logger
from utils import json_utils, prompt_utils


class ABPageValidator:
    def __init__(self, config: Config = None, max_workers: int = 5, retry_times: int = 3):
        self.config = config
        self.max_workers = max_workers
        self.retry_times = retry_times
        self.threading_lock = threading.Lock()

    def _write_result(self,
                      idx: int,
                      ab_test_results: dict,
                      thought: str,
                      label: str,
                      action_des: str = None,
                      pagea_description: str = None,
                      pageb_description: str = None):
        with self.threading_lock:
            ab_test_results[str(idx)] = {
                'thought': thought,
                'label': label,
                'action_des': action_des,
                'pagea_description': pagea_description,
                'pageb_description': pageb_description,
            }

    def _request_page_description(self, image: str, prompt: str = None) -> str | None:
        prompt = prompt or single_image_prompts.page_des_prompt
        message = None
        for _ in range(self.retry_times):
            try:
                message = mllm.request_vlm(
                    image=image,
                    user_query=prompt,
                    server_url=self.config.model.VLM_MODEL_URL,
                    model_name=self.config.model.VLM_MODEL_NAME,
                )
                parsed_res = json_utils.extract_json_from_string(message)
                if parsed_res and parsed_res.get('page_description'):
                    return parsed_res['page_description']
            except Exception as e:
                logger.warning(f'ABPageValidator：页面描述API服务出现问题，重试...\n'
                               f'e: {e}\n'
                               f'message: {message}')
        return None

    def _call_single_api(self, image_pair: tuple[int, str, str, dict, None | str, str],
                         ab_test_results: dict = None):
        idx, img_a, img_b, action_info, img_a_raw, color = image_pair
        action_type = action_info['parsed_action']['action_type']
        pagea_description = None
        pageb_description = None
        action_des = None
        thought = 'API服务出现问题'
        label = '无法判定'

        if action_type not in ['click', 'long_press', 'type', 'set_text']:
            if action_type in ['clarify', 'done', 'finished']:
                thought = '此处没有操作故无需判定'
                label = '符合预期'
                pageb_description = self._request_page_description(img_b)
            elif action_type in ['wait', 'do-nothing']:
                message = None
                for _ in range(self.retry_times):
                    try:
                        message = mllm.request_vlm(
                            image=img_b,
                            user_query=single_image_prompts.wait_page_prompt,
                            server_url=self.config.model.VLM_MODEL_URL,
                            model_name=self.config.model.VLM_MODEL_NAME,
                        )
                        parsed_res = json_utils.extract_json_from_string(message)
                        if not parsed_res:
                            raise ValueError('模型返回为空或不是可解析JSON')
                        thought = parsed_res.get('Answer', '无法判定')
                        pageb_description = parsed_res.get('page_description')
                        label = '不符合预期' if thought in ['加载失败', '毛玻璃', '加载中'] else '符合预期'
                        break
                    except Exception as e:
                        logger.warning(f'ABPageValidator：API服务出现问题，重试...\n'
                                       f'e: {e}\n'
                                       f'message: {message}')
            elif action_type in ['scroll', 'swipe', 'drag']:
                thought = '此处为滑动操作'
                label = '符合预期'
                pageb_description = self._request_page_description(img_b)
            else:
                thought = f'action type: {action_type} is illegal!'
                label = '无法判定'

            if idx == 0:
                pagea_description = self._request_page_description(img_a_raw)
            self._write_result(idx, ab_test_results, thought, label, None, pagea_description, pageb_description)
            return

        for _ in range(self.retry_times):
            message = None
            try:
                first_page = idx == 0
                action_description = prompt_utils.make_action_description(action_info)
                if 'start_box' in action_info['parsed_action'] and action_info['parsed_action']['start_box'] and \
                        action_type in ['click', 'long_press']:
                    prompt1 = ab_test_prompts.deep_oracle_prompt1_w_vp.format(color=color)
                    prompt2 = ab_test_prompts.deep_oracle_prompt2_w_vp
                    prompt3 = ab_test_prompts.deep_oracle_prompt3_w_vp
                    prompt3 = prompt3.format(
                        action_info=action_description,
                        action_type='长按' if action_type == 'long_press' else '点击',
                        color=color,
                    )
                else:
                    prompt1 = ab_test_prompts.deep_oracle_prompt1_wo_vp
                    prompt2 = ab_test_prompts.deep_oracle_prompt2_wo_vp
                    prompt3 = ab_test_prompts.deep_oracle_prompt3_wo_vp.format(action_info=action_description)

                message = mllm.request_vlm_ab_test(
                    img1_path=img_a,
                    img2_path=img_b,
                    prompt1=prompt1,
                    prompt2=prompt2,
                    prompt3=prompt3,
                    server_url=self.config.model.VLM_MODEL_URL,
                    model_name=self.config.model.VLM_MODEL_NAME,
                )
                parsed_res = json_utils.extract_json_from_string(message)
                if not parsed_res:
                    parsed_res = json_utils.extract_thought_and_answer(message)
                if not parsed_res:
                    raise ValueError('模型返回为空或不是可解析JSON')

                thought = parsed_res.get('Thought') or parsed_res.get('thought') or '无法判定'
                label = parsed_res.get('Answer') or parsed_res.get('answer') or '无法判定'
                action_des = parsed_res.get('ActionDescription')
                pageb_description = parsed_res.get('PageB_Content') or parsed_res.get('pageb_description')
                if first_page:
                    pagea_description = self._request_page_description(img_a_raw)

                self._write_result(idx, ab_test_results, thought, label, action_des, pagea_description, pageb_description)
                return
            except Exception as e:
                logger.warning(f'ABPageValidator：API服务出现问题，重试...\n'
                               f'e: {e}\n'
                               f'message: {message}')

        if idx == 0:
            pagea_description = self._request_page_description(img_a_raw)
        self._write_result(idx, ab_test_results, thought, label, action_des, pagea_description, pageb_description)

    def _worker(self, image_pairs: list = None, ab_test_results: dict = None):
        while len(image_pairs) > 0:
            with self.threading_lock:
                try:
                    this_image_pair = image_pairs.pop()
                except Exception:
                    return
            self._call_single_api(image_pair=this_image_pair, ab_test_results=ab_test_results)

    def validate_all_pairs(self, image_pairs: list[tuple[int, str, str, dict, None | str, str]]):
        ab_test_results = {}
        threading_list = []

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
        for i, img_id in enumerate(sorted_ids):
            thought = ab_test_results[img_id]['thought']
            if thought == '正常' and i - 1 >= 0:
                if ab_test_results[sorted_ids[i - 1]]['label'] == '不符合预期':
                    ab_test_results[sorted_ids[i - 1]]['label'] = '符合预期'
                    ab_test_results[sorted_ids[i - 1]]['thought'] = '虽然下一张页面处于加载中，但是再下面一张页面加载出来了，所以符合预期。'

        return ab_test_results


if __name__ == "__main__":
    start_time = time.time()
    print("ABPageValidator module loaded")
    print(f"time used: {time.time() - start_time:.2f}s")
