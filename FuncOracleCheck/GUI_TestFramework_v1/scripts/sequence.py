import os
from typing import List, Tuple, Any

from GUI_TestFramework_v1.api_service import mllm
from GUI_TestFramework_v1.api_service.prompts import ab_test_prompts, sequence_split_prompts, single_image_prompts, intention_predicate

from utils import cv_utils, json_utils, prompt_utils
from utils.step_split import parse_steps
from GUI_TestFramework_v1.api_service.prompts import single_image_prompts
from GUI_TestFramework_v1.common.logger import default_logger as logger
from .config import Config
from .rsync_multi_threads_ab_validator import ABPageValidator


class HarmonyAppTest:
    def __init__(
            self,
            config: Config
    ):

        """
            初始化HarmonyAppTest类

            config: 测评框架参数设置
        """
        sample_dict = {}
        self.config = config
        # 初始化属性
        assert self.config.project.PREDICATE_MODE in ['test', 'production'], "判定模式必须从['test', 'production']中选择一个"
        if self.config.project.PREDICATE_MODE == 'test':
            assert os.path.exists(config.data.DATA_DIR), '数据所在文件夹不存在，退出判定'
            data_dir = config.data.DATA_DIR
            json_name = os.path.basename(data_dir).split('#')[0]
            json_path = os.path.join(data_dir, f'{json_name}.json')
            assert os.path.exists(json_path), '数据所在文件夹缺少必要的json文件，退出判定'
            sample_dict = json_utils.load_json(json_path)
            if config.data.SAVE_RESULT:
                os.makedirs(config.data.OUTPUT_DIR, exist_ok=True)
        if config.project.PREDICATE_MODE == 'production':
            assert config.data.METADATA, '待测样本json不能为空'
            assert all(item in config.data.METADATA for item in ['instruction', 'step_level_instruction', 'seq_info']), \
                '待测样本json格式错误，缺少必要字段'
            sample_dict = config.data.METADATA

        if isinstance(sample_dict, list):  # json格式化处理
            sample_dict = sample_dict[0]
        self.json_data = sample_dict

        intention_steps = parse_steps(self.json_data['step_level_instruction'])
        self.intention_sequence = {}
        self.intention = self.json_data['instruction']

        self.step_validation = []  # 如果序列中存在中途结束操作，会对序列进行拆分，以每一个结束操作为终点拆分成子序列，验证时对每个子序列单独验证
        self.page_sequence = {'0': 0}  # 记录每个子序列的页面起点
        # 初始化第一条子序列的验证结果，一条序列中至少包含一条子序列
        self.step_validation.append({'sequence_id': 0,
                                     'sequence_start_page_id': 0,
                                     'llm_step_validation': {},
                                     'vlm_step_validation': {},
                                     'intention_validation': {'label': 'ok', 'wrong_reason': ''}})
        # 分隔序列
        sequence_id = 0
        if len(self.json_data['seq_info']) > 1:
            for page in self.json_data['seq_info'][:-1]:
                if page['planning_output']['parsed_action']['action_type'] in ['done', 'finished']:
                    self.page_sequence[str(sequence_id + 1)] = int(page['index']) + 1
                    self.step_validation.append({'sequence_id': sequence_id + 1,
                                                 'sequence_start_page_id': int(page['index']) + 1,
                                                 'llm_step_validation': {},
                                                 'vlm_step_validation': {},
                                                 'intention_validation': {'label': 'ok', 'wrong_reason': ''}})
                    sequence_id += 1
        self.page_sequence[str(sequence_id + 1)] = len(self.json_data['seq_info'])
        self.intention_validation = ['ok'] * len(self.page_sequence)

        step_idx = 1
        for step in intention_steps:
            if all(keyword not in step.lower() for keyword in ['金刚', 'feed', '信息流']):
                self.intention_sequence[f'step_{str(step_idx)}'] = step
                for step_validation_child_sequence in self.step_validation:
                    step_validation_child_sequence['llm_step_validation'][f'step_{str(step_idx)}'] = {'label': 'pok',
                                                                                                  'page_id': -1,
                                                                                                  'wrong_reason': ''}
                    step_validation_child_sequence['vlm_step_validation'][f'step_{str(step_idx)}'] = {'label': 'pok',
                                                                                                      'page_id': -1,
                                                                                                      'wrong_reason': ''}
                step_idx += 1

        self.ab_test_results = {}
        self.action_des = {}
        self.page_des = {}
        self.page_vp_color = {}
        self.result = self._result_format()

    # 对每条子序列进行判定
    def child_sequence_router(self):
        for sequence_idx, sequence_page_start_id in self.page_sequence.items():
            if int(sequence_idx) == len(self.page_sequence) - 1:
                break
            elif self.page_sequence[str(int(sequence_idx) + 1)] - sequence_page_start_id > 1:
                child_page_des = {}
                for page_idx in range(sequence_page_start_id, self.page_sequence[str(int(sequence_idx) + 1)]):
                    child_page_des[str(page_idx)] = self.page_des[str(page_idx)]
                child_page_des_wo_wait, child_action_des_wo_wait, child_id_map = self._remove_wait_action(
                    child_page_des, sequence_page_start_id)
                if self.config.project.SLIDING_MODE in ['MIX', 'VLM']:
                    self._sequence_sliding_window_image(sequence_id=int(sequence_idx), page_des=child_page_des_wo_wait,
                                                        action_des=child_action_des_wo_wait, id_map=child_id_map)
                if self.config.project.SLIDING_MODE in ['MIX', 'LLM']:
                    self._sequence_sliding_window(sequence_id=int(sequence_idx), page_des=child_page_des_wo_wait,
                                                  action_des=child_action_des_wo_wait, id_map=child_id_map)
                intention_answer, intention_thought = self._sequence_predicate(page_des=child_page_des_wo_wait,
                                                                               action_des=child_action_des_wo_wait,
                                                                               id_map=child_id_map,
                                                                             intention=self.intention)
                intention_label = 'ok' if intention_answer == 'ok' else 'nok'
                self.intention_validation[int(sequence_idx)] = intention_label
                self.step_validation[int(sequence_idx)]['intention_validation']['label'] = intention_label
                self.step_validation[int(sequence_idx)]['intention_validation']['wrong_reason'] = intention_thought
                # if intention_label == 'nok':
                # self.step_validation[int(sequence_idx)]['intention_validation']['wrong_reason'] = '操作意图没有被满足'
            else:
                self.single_image_processing(sequence_id=int(sequence_idx))

    # 判定实际操作序列中每步跳转结果
    def ab_pages_validate(self):
        action_sequences = self.json_data['seq_info']
        ab_pairs: List[Tuple[int, Any, Any, Any, Any, Any]] = []

        for idx in range(len(action_sequences) - 1):
            if self.config.project.PREDICATE_MODE == 'test':
                img1_path = self.config.data.DATA_DIR + os.sep + 'images' + os.sep + action_sequences[idx][
                    "image_relative_path"]
                img1 = cv_utils.open_image_in_cv2(image_path=img1_path)
                img1_base64 = cv_utils.encode_image_to_base64(img1)
                img2_path = self.config.data.DATA_DIR + os.sep + 'images' + os.sep + action_sequences[idx + 1][
                    "image_relative_path"]
                img2_base64 = cv_utils.encode_image_to_base64(img2_path)
            else:
                img1_base64 = action_sequences[idx]["image_relative_path"]
                img1 = cv_utils.convert_base64_to_cv2(base64_code=action_sequences[idx]["image_relative_path"])
                img2_base64 = action_sequences[idx + 1]["image_relative_path"]
            action_info = action_sequences[idx]['planning_output']
            img1_w_visual_prompt, color = prompt_utils.make_visual_prompt(img1, action_info['parsed_action'], save_hint=f"ab_{idx}")
            img1_vp_base64 = cv_utils.encode_image_to_base64(img1_w_visual_prompt)
            self.page_vp_color[f'{idx}'] = color
            ab_pairs.append((idx, img1_vp_base64, img2_base64, action_info, img1_base64, color))

        validator = ABPageValidator(config=self.config)
        print('1')
        ab_test_results = validator.validate_all_pairs(ab_pairs)
        print(ab_test_results)
        sorted_items = sorted(ab_test_results.items(), key=lambda x: int(x[0]))
        self.ab_test_results = dict(sorted_items)

        for idx, item in self.ab_test_results.items():
            if item['action_des']:
                self.action_des[str(idx)] = item['action_des']
            else:
                self.action_des[str(idx)] = prompt_utils.make_action_description(
                    action_sequences[int(idx)]['planning_output'])
            if idx == '0':
                self.page_des['0'] = item['pagea_description']
            self.page_des[str(int(idx) + 1)] = item['pageb_description']

    # 去掉操作序列中的动作为等待的截图
    def _remove_wait_action(self, child_page_des: dict, sequence_page_start_id: int):
        id_map = {}

        start_id = 0
        end_id = sequence_page_start_id
        page_des_wo_wait = {}
        action_des_wo_wait = {}
        while end_id < sequence_page_start_id + len(child_page_des) - 1:
            page_des_wo_wait[str(start_id)] = self.page_des[str(end_id)]
            action_des_wo_wait[str(start_id)] = self.action_des[str(end_id)]
            id_map[str(start_id)] = str(end_id)

            if self.json_data['seq_info'][end_id]['planning_output']['parsed_action']['action_type'] in [
                'clarify', 'done', 'finished', 'wait', 'do-nothing']:
                while end_id < sequence_page_start_id + len(child_page_des) - 1 and \
                        self.json_data['seq_info'][end_id]['planning_output']['parsed_action']['action_type'] in ['clarify', 'done', 'finished', 'wait', 'do-nothing']:
                    end_id += 1
                start_id += 1
                page_des_wo_wait[str(start_id)] = self.page_des[str(end_id)]
                if end_id != sequence_page_start_id + len(child_page_des) - 1:
                    action_des_wo_wait[str(start_id)] = self.action_des[str(end_id)]
                id_map[str(start_id)] = str(end_id)
            start_id += 1
            end_id += 1

        if end_id == sequence_page_start_id + len(child_page_des) - 1:
            page_des_wo_wait[str(start_id)] = self.page_des[str(end_id)]
            id_map[str(start_id)] = str(end_id)

        return page_des_wo_wait, action_des_wo_wait, id_map

    # 使用LLM滑动窗口判定步骤完备性
    def _sequence_sliding_window(self, sequence_id: int, page_des: dict, action_des: dict, id_map: dict):
        step_window_start = 0
        for idx, step in self.intention_sequence.items():
            step_sequence = {}
            for i in range(step_window_start, len(page_des)):
                step_sequence[str(i)] = {'page_description': page_des[str(i)]}
                llm_answer = self._intention_predicate(step, step_sequence)
                if llm_answer == 'ok':
                    self.step_validation[sequence_id]['llm_step_validation'][idx]['label'] = 'ok'
                    self.step_validation[sequence_id]['llm_step_validation'][idx]['page_id'] = int(id_map[str(i)])
                    step_window_start = i
                    break
                elif i != len(page_des) - 1:
                    step_sequence[str(i)]['action_description'] = action_des[str(i)]
                else:
                    self.step_validation[sequence_id]['llm_step_validation'][idx]['label'] = 'nok'
                    self.step_validation[sequence_id]['llm_step_validation'][idx]['page_id'] = -1
                    self.step_validation[sequence_id]['llm_step_validation'][idx]['wrong_reason'] = '意图执行步骤未覆盖'

    # 使用VLM滑动窗口判定步骤完备性
    def _sequence_sliding_window_image(self, sequence_id: int, page_des: dict, action_des: dict,
                                       id_map: dict):
        step_window_start = 0
        for idx, step in self.intention_sequence.items():
            window_page_des = {}
            window_action_des = {}
            window_page_des[str(step_window_start)] = page_des[str(step_window_start)]
            image_label, thought = self._single_step_validation(step_id=idx,
                                                                img_idx=int(id_map[str(step_window_start)]))

            if image_label:
                self.step_validation[sequence_id]['vlm_step_validation'][idx]['label'] = 'ok'
                self.step_validation[sequence_id]['vlm_step_validation'][idx]['wrong_reason'] = thought
                self.step_validation[sequence_id]['vlm_step_validation'][idx]['page_id'] = int(
                    id_map[str(step_window_start)])
            else:
                id_start = step_window_start
                for i in range(step_window_start, len(page_des) - 1):
                    window_action_des[str(i)] = action_des[str(i)]
                    window_page_des[str(i + 1)] = page_des[str(i + 1)]
                    image_label, thought = self._sequence_predicate(window_page_des, window_action_des,
                                                                    id_map, step,
                                                                    id_start, step_flag=True)
                    if image_label == 'ok':
                        self.step_validation[sequence_id]['vlm_step_validation'][idx]['label'] = 'ok'
                        self.step_validation[sequence_id]['vlm_step_validation'][idx]['page_id'] = int(
                            id_map[str(i + 1)])
                        self.step_validation[sequence_id]['vlm_step_validation'][idx]['wrong_reason'] = thought
                        step_window_start = i
                        break
                    if i == len(page_des) - 2 and self.step_validation[sequence_id]['vlm_step_validation'][idx]['label'] == 'pok':
                        self.step_validation[sequence_id]['vlm_step_validation'][idx]['label'] = 'nok'
                        self.step_validation[sequence_id]['vlm_step_validation'][idx]['page_id'] = -1
                        self.step_validation[sequence_id]['vlm_step_validation'][idx]['wrong_reason'] = thought

    # 使用LLM判断意图是否完备
    def _intention_predicate(self, intention, intention_history):
        for _ in range(3):
            try:
                message = mllm.request_llm_intention_predicate(intention=intention,
                                                               intention_history=intention_history,
                                                               url_=self.config.model.LLM_MODEL_URL,
                                                               model_name_=self.config.model.LLM_MODEL_NAME)
                parsed_res = json_utils.extract_json_from_string(message)
                label = parsed_res['answer']
                if label == '达成意图':
                    answer = 'ok'
                else:
                    answer = 'nok'
                return answer
            except Exception as e:
                logger.info(f'API 请求错误，重试...\n'
                            f'e: {e}\n'
                            f'message: {message}')
            return '无法判定'

    # 用VLM判断意图是否完备
    def _sequence_predicate(self, page_des: dict, action_des: dict, id_map: dict, intention: str, id_start: int = 0,
                            step_flag: bool = False):
        intention_history = {}
        page_id = len(page_des) - 1 + id_start
        if self.config.project.PREDICATE_MODE == 'test':
            img2_path = self.config.data.DATA_DIR + os.sep + 'images' + os.sep + \
                        self.json_data['seq_info'][int(id_map[str(page_id)])]['image_relative_path']
            img2_base64 = cv_utils.encode_image_to_base64(img2_path)
        else:
            img2_base64 = self.json_data['seq_info'][int(id_map[str(page_id)])]['image_relative_path']
        img2_des = page_des[str(page_id)]
        page_id -= 1
        while page_id > id_start:
            if (self.json_data['seq_info'][int(id_map[str(page_id)])]['planning_output']['parsed_action'][
                'action_type'] not in
                    ['clarify', 'done', 'finished', 'wait', 'do-nothing']):
                break
            page_id -= 1
        if self.config.project.PREDICATE_MODE == 'test':
            img1_path = self.config.data.DATA_DIR + os.sep + 'images' + os.sep + \
                        self.json_data['seq_info'][int(id_map[str(page_id)])]["image_relative_path"]
            img1 = cv_utils.open_image_in_cv2(image_path=img1_path)
        else:
            img1_base64 = self.json_data['seq_info'][int(id_map[str(page_id)])]["image_relative_path"]
            img1 = cv_utils.convert_base64_to_cv2(base64_code=img1_base64)

        img1_vp, _ = prompt_utils.make_visual_prompt(
            img1,
            self.json_data['seq_info'][int(id_map[str(page_id)])]['planning_output']['parsed_action'],
            save_hint=f"sliding_{page_id}"
        )
        img1_vp_base64 = cv_utils.encode_image_to_base64(img1_vp)
        img1_des = page_des[str(page_id)]
        vp_color = self.page_vp_color[id_map[str(page_id)]]
        action_description = prompt_utils.make_action_description(
            self.json_data['seq_info'][int(id_map[str(page_id)])]['planning_output'])
        if page_id > id_start:
            for i in range(id_start, page_id):
                intention_history[str(i - id_start)] = {'图片描述': page_des[str(i)],
                                                        '在该图片上的操作动作描述': action_des[str(i)]}

        for _ in range(3):
            try:
                if not step_flag:
                    prompt2 = ab_test_prompts.intention_judge_prompt2.format(action_info=action_description,
                                                                             color=vp_color)
                    prompt3 = ab_test_prompts.intention_judge_prompt3.format(page_des=img2_des)
                    if intention_history:
                        prompt1 = ab_test_prompts.intention_judge_prompt1.format(intention=intention,
                                                                                 intention_history=intention_history,
                                                                                 page_des=img1_des, color=vp_color)

                    else:
                        prompt1 = ab_test_prompts.intention_judge_no_history_prompt1.format(intention=intention,
                                                                                            page_des=img1_des,
                                                                                            color=vp_color)
                else:
                    prompt2 = ab_test_prompts.step_judge_prompt2.format(action_info=action_description,
                                                                        color=vp_color)
                    prompt3 = ab_test_prompts.step_judge_prompt3.format(page_des=img2_des)
                    if intention_history:
                        prompt1 = ab_test_prompts.step_judge_prompt1.format(intention=intention,
                                                                            intention_history=intention_history,
                                                                            page_des=img1_des, color=vp_color)

                    else:
                        prompt1 = ab_test_prompts.step_judge_no_history_prompt1.format(intention=intention,
                                                                                       page_des=img1_des,
                                                                                       color=vp_color)
                message = mllm.request_vlm_ab_test(img1_path=img1_vp_base64,
                                                   img2_path=img2_base64,
                                                   prompt1=prompt1,
                                                   prompt2=prompt2,
                                                   prompt3=prompt3,
                                                   server_url=self.config.model.VLM_MODEL_URL,
                                                   model_name=self.config.model.VLM_MODEL_NAME)
                parsed_res = json_utils.extract_json_from_string(message)

                label = parsed_res['answer']
                thought = parsed_res['thought']
                expected_action = parsed_res['expected_action']
                if label == '达成意图' and expected_action == '执行':
                    answer = 'ok'
                else:
                    answer = 'nok'
                return answer, thought
            except Exception as e:
                logger.info(f'_sequence_predicate: API 请求错误，重试...\n'
                            f'e: {e}\n'
                            f'message: {message}')
            return '无法判定', None

    # 初始化返回结果
    def _result_format(self):
        result = {
            'llm_intention_step': {
            },
            'vlm_intention_step': {
            },
            'intention': {
                'label': 'ok',
                'page_id': [-1],
                'wrong_reason': '',
            },
            'llm_intention_step_identity': {
                'label': 'ok',
                'wrong_steps': [],
                'bug_steps': []
            },
            'vlm_intention_step_identity': {
                'label': 'ok',
                'wrong_steps': [],
                'bug_steps': []
            },
        }

        for idx, step in self.intention_sequence.items():
            sliding_mode = ['llm_intention_step', 'vlm_intention_step']
            for mode in sliding_mode:
                result[mode][idx] = {'step': step,
                                             'label': 'pok',
                                             'page_id': [-1],
                                             'wrong_reason': '',
                                             'wrong_pages': []}

        return result

    # 处理没有图片的序列
    def no_image_processing(self):
        self.result['intention']['label'] = 'nok'
        self.result['intention']['wrong_reason'] = '操作意图没有被满足'

        self.result['intention_step_identity']['label'] = 'nok'

        for intention_idx, intention_step in self.intention_sequence.items():
            self.result['llm_intention_step'][intention_idx]['label'] = 'nok'
            self.result['vlm_intention_step'][intention_idx]['label'] = 'nok'
            self.result['intention_step'][intention_idx]['wrong_reason'] = '意图执行步骤未覆盖'
            self.result['intention_step_identity']['wrong_steps'].append(intention_step)
        raise ValueError('图片序列长度为0，该意图执行失败')

    def _single_step_validation(self, intention_validate: bool = False, step_id: str = None, img_idx: int = 0):
        if self.config.project.PREDICATE_MODE == 'test':
            img = self.config.data.DATA_DIR + os.sep + 'images' + os.sep + self.json_data['seq_info'][img_idx][
                'image_relative_path']
            img_base64 = cv_utils.encode_image_to_base64(img)
        else:
            img_base64 = self.json_data['seq_info'][img_idx]['image_relative_path']
        if not intention_validate:
            query = single_image_prompts.prompt1.format(intention=self.intention_sequence[step_id])
        else:
            query = single_image_prompts.prompt1.format(intention=self.intention)
        for _ in range(3):
            try:
                response = mllm.request_vlm(user_query=query,
                                            image=img_base64,
                                            server_url=self.config.model.VLM_MODEL_URL,
                                            model_name=self.config.model.VLM_MODEL_NAME)
                parsed_res = json_utils.extract_json_from_string(response)
                label = parsed_res['Answer']
                thought = parsed_res['Thought']
                if label == '已被满足':
                    return True, thought
                else:
                    return False, thought
            except:
                logger.info(f'HarmonyAppTest: _single_step_validation: API服务出现问题，重试...\n'
                            f'response: {response}')

    # 处理只有单张图片的序列
    def single_image_processing(self, sequence_id: int):
        sliding_mode_result_dict = {'LLM': ['llm'], 'VLM': ['vlm'],
                                    'MIX': ['vlm', 'llm']}
        image_label, thought = self._single_step_validation(intention_validate=True,
                                                            img_idx=self.page_sequence[str(sequence_id)])
        if not image_label:  # 判断意图是否满足
            self.step_validation[sequence_id]['intention_validation']['label'] = 'nok'
            self.step_validation[sequence_id]['intention_validation']['wrong_reason'] = thought
        else:
            self.step_validation[sequence_id]['intention_validation']['label'] = 'ok'
            self.step_validation[sequence_id]['intention_validation']['wrong_reason'] = thought
            # self.step_validation[sequence_id]['intention_validation']['page_id'] = self.page_sequence[str(sequence_id)]
            # self.result['intention']['page_id'] = self.page_sequence[str(sequence_id)]

        for idx, intention_step in self.intention_sequence.items():
            image_step_label, thought = self._single_step_validation(step_id=idx)
            for result_dict in sliding_mode_result_dict[self.config.project.SLIDING_MODE]:
                if image_step_label:
                    self.step_validation[sequence_id][f'{result_dict}_step_validation'][idx]['label'] = 'ok'
                    self.step_validation[sequence_id][f'{result_dict}_step_validation'][idx]['page_id'] = self.page_sequence[
                        str(sequence_id)]
                    self.step_validation[sequence_id][f'{result_dict}_step_validation'][idx]['wrong_reason'] = thought
                else:
                    for rest_idx, intention_step in self.intention_sequence.items():
                        if int(rest_idx.split('_')[-1]) >= int(idx.split('_')[-1]):
                            self.step_validation[sequence_id][f'{result_dict}_step_validation'][idx]['label'] = 'nok'
                            self.step_validation[sequence_id][f'{result_dict}_step_validation'][idx]['wrong_reason'] = '意图执行步骤未覆盖'

        if len(self.step_validation) == 1:
            for result_dict in sliding_mode_result_dict[self.config.project.SLIDING_MODE]:
                for step_idx, step_label in self.step_validation[0][f'{result_dict}_step_validation'].items():
                        self.result[f'{result_dict}_intention_step'][step_idx]['label'] = step_label['label']
                        self.result[f'{result_dict}_intention_step'][step_idx]['page_id'] = step_label['page_id']
                        self.result[f'{result_dict}_intention_step'][step_idx]['wrong_reason'] = step_label['wrong_reason']
                        if step_label['label'] == 'nok':
                            self.result[f'{result_dict}_intention_step_identity']['wrong_steps'].append(self.intention_sequence[step_idx])

            self.result['intention']['label'] = self.step_validation[0]['intention_validation']['label']
            self.result['intention']['page_id'] = [0] if self.result['intention']['label'] == 'ok' else [-1]
            self.result['intention']['wrong_reason'] = self.step_validation[0]['intention_validation']['wrong_reason']

            for result_dict in sliding_mode_result_dict[self.config.project.SLIDING_MODE]:
                if len(self.result[f'{result_dict}_intention_step_identity']['wrong_steps']) > 0:
                    self.result[f'{result_dict}_intention_step_identity']['label'] = 'nok'

            if self.config.project.PREDICATE_MODE == 'test':
                json_utils.dump_json(self.result, os.path.join(self.config.data.OUTPUT_DIR,
                                                               f'{os.path.basename(self.config.data.DATA_DIR)}.json'))

    # 输出最终判定结果，包含每个意图执行步骤和操作意图
    def test_result(self):
        sliding_mode_result_dict = {'LLM': ['llm'], 'VLM': ['vlm'],
                                    'MIX': ['vlm', 'llm']}
        self.result['ab_pages_result'] = self.ab_test_results

        wrong_steps = []
        bug_steps = []

        for step_idx, step in self.intention_sequence.items():
            for result_dict in sliding_mode_result_dict[self.config.project.SLIDING_MODE]:
                if self.step_validation[0][f'{result_dict}_step_validation'][step_idx]['label'] == 'nok':
                    self.result[f'{result_dict}_intention_step'][step_idx]['page_id'] = \
                        self.step_validation[0][f'{result_dict}_step_validation'][step_idx]['page_id']
                    self.result[f'{result_dict}_intention_step'][step_idx]['label'] = self.step_validation[0][f'{result_dict}_step_validation'][step_idx][
                        'label']
                    self.result[f'{result_dict}_intention_step'][step_idx]['wrong_reason'] = \
                        self.step_validation[0][f'{result_dict}_step_validation'][step_idx]['wrong_reason']
                    wrong_steps.append(step)
                if self.step_validation[0][f'{result_dict}_step_validation'][step_idx]['label'] == 'ok':
                    self.result[f'{result_dict}_intention_step'][step_idx]['page_id'] = \
                        self.step_validation[0][f'{result_dict}_step_validation'][step_idx]['page_id']
                    step_id = int(step_idx.split('_')[-1])
                    window_start = 0
                    window_end = self.result[f'{result_dict}_intention_step'][step_idx]['page_id']
                    while step_id > 1:
                        last_step_page_id = self.step_validation[0][f'{result_dict}_step_validation'][f'step_{str(step_id - 1)}'][
                            'page_id']
                        if last_step_page_id != -1:
                            window_start = last_step_page_id
                            break
                        step_id -= 1

                    if window_end - window_start > 1:
                        for page_idx, page_label in self.ab_test_results.items():
                            if (window_end - 1) > int(page_idx) >= window_start and page_label['label'] != '符合预期':
                                self.result[f'{result_dict}_intention_step'][step_idx]['wrong_pages'].append(page_idx)
                    if len(self.result[f'{result_dict}_intention_step'][step_idx]['wrong_pages']) == 0:
                        self.result[f'{result_dict}_intention_step'][step_idx]['label'] = 'ok'
                        self.result[f'{result_dict}_intention_step'][step_idx]['wrong_reason'] = \
                            self.step_validation[0][f'{result_dict}_step_validation'][step_idx]['wrong_reason']
                    else:
                        self.result[f'{result_dict}_intention_step'][step_idx]['wrong_reason'] = '功能bug'
                        bug_steps.append(step)

                if len(wrong_steps) > 0:
                    self.result[f'{result_dict}_intention_step_identity']['label'] = 'nok'
                    self.result[f'{result_dict}_intention_step_identity']['wrong_steps'] = wrong_steps
                elif len(bug_steps) > 0:
                    self.result[f'{result_dict}_intention_step_identity']['label'] = 'pok'
                    self.result[f'{result_dict}_intention_step_identity']['bug_steps'] = bug_steps

            self.result['intention']['label'] = self.step_validation[0]['intention_validation']['label']
            self.result['intention']['wrong_reason'] = self.step_validation[0]['intention_validation']['wrong_reason']

        if self.config.project.PREDICATE_MODE == 'test':
            json_utils.dump_json(self.result, os.path.join(self.config.data.OUTPUT_DIR,
                                                           f'{os.path.basename(self.config.data.DATA_DIR)}.json'))


    def _step_result_format_align(self, result_dict: str, align_result: dict):
        align_result['缺失的功能'] = self.result[f'{result_dict}_intention_step_identity']['wrong_steps']
        pok_steps = []

        cnt_covered_steps = 0
        for step, info in self.result[f'{result_dict}_intention_step'].items():
            if info['label'] == 'pok':
                pok_steps.append(info['step'])
            if info['page_id'] != (-1,) and info['page_id'] != -1:
                cnt_covered_steps += 1
        align_result['存在问题的功能'] = pok_steps

        align_result['Plan步骤数'] = len(self.result[f'{result_dict}_intention_step'])
        align_result['执行覆盖Plan步骤数'] = cnt_covered_steps
        align_result['已覆盖Plan'] = []
        align_result['未覆盖Plan'] = []
        for step, info in self.result[f'{result_dict}_intention_step'].items():
            if info['label'] == 'nok':
                align_result['未覆盖Plan'].append(
                    {'Plan步骤名': info['step'], "执行结果评估依据": "没有对应的执行步骤覆盖此Plan步骤"})
            if info['label'] == 'ok':
                align_result['已覆盖Plan'].append(
                    {'Plan步骤名': info['step'], "覆盖Plan步骤的执行步骤序号": info['page_id'], '整体通过情况': '通过',
                     "结果分类": "成功",
                     '存在bug的执行步骤': {}})
            if info['label'] == 'pok':
                align_result['已覆盖Plan'].append(
                    {'Plan步骤名': info['step'], "覆盖Plan步骤的执行步骤序号": info['page_id'], '整体通过情况': '通过',
                     "结果分类": "存在功能bug",
                     '存在bug的执行步骤': info['wrong_steps']})

        return align_result


    # 对齐用户接口
    def result_format_align(self):
        sliding_mode_result_dict = {'LLM': ['llm'], 'VLM': ['vlm'],
                                    'MIX': ['vlm', 'llm']}
        align_result = dict()
        align_result['整体意图测试结果'] = self.result['intention']['label']
        align_result['整体意图测试结果判断依据'] = self.result['intention']['wrong_reason'] if self.result['intention']['label'] == 'nok' else '执行成功'

        if self.config.project.SLIDING_MODE == 'LLM':
            align_result['路径一致性测试结果'] = self.result['llm_intention_step_identity']['label']
        if self.config.project.SLIDING_MODE == 'VLM':
            align_result['路径一致性测试结果'] = self.result['vlm_intention_step_identity']['label']
        if self.config.project.SLIDING_MODE == 'MIX':
            if self.result['llm_intention_step_identity']['label'] == 'nok':
                if self.result['vlm_intention_step_identity']['label'] == 'nok':
                    align_result['路径一致性测试结果'] = 'nok'
                else:
                    align_result['路径一致性测试结果'] = 'ok'
            else:
                align_result['路径一致性测试结果'] = 'ok'

        if self.config.project.SLIDING_MODE in ['VLM', 'LLM']:
            result_dict = sliding_mode_result_dict[self.config.project.SLIDING_MODE][0]
            self._step_result_format_align(result_dict=result_dict, align_result=align_result)
        else: #混合模式
            for step_idx, llm_result in self.result['llm_intention_step'].items():
                if llm_result['label'] == 'nok':
                    if self.result['vlm_intention_step'][step_idx]['label'] != 'nok':
                        llm_result['label'] = 'ok'
            self._step_result_format_align(result_dict='llm', align_result=align_result)

        return align_result


if __name__ == '__main__':
    json_data = json_utils.load_json(
        r'D:\FuncOracleCheck\GUI_TestFramework_v1\examples\0d18920e-1db0-4a46-a64d-17b59c1de6f1#1755847026352\data1.json')

    newtest = HarmonyAppTest(config=Config())
    if len(json_data['seq_info']) == 1:
        newtest.single_image_processing(sequence_id=0)
        logger.info(newtest.result_format_align())
    else:
        newtest.ab_pages_validate()
        newtest.child_sequence_router()
        newtest.test_result()
        logger.info(newtest.result_format_align())
