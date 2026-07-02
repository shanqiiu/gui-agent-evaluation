from ..api_service import mllm
from ..api_service.prompts import ab_test_prompts, single_image_prompts
from utils import cv_utils, json_utils, prompt_utils


class HarmonyAPPSingleStepTest:
    def __init__(self, sample_dict: dict):

        """
            初始化HarmonyAppSingleStepTest类

            参数:
            sample_dict: 用户输入的图片对和动作信息
            example:
            {
                "seq_info": [{
                    "index": 0,
                    "image_relative_path": "", #base64
                    "planning_output": {
                        "parsed_action": {
                            "action_type": "CLICK",
                            "start_box": [94,2416],
                            "end_box": [],
                            "text": "",
                            "direction": ""}
                    }
                },
                    {
                        "index": 1,
                        "image_relative_path": ",
                    }
                ]
            }
        """
        self.sample_dict = sample_dict

    def run(self):
        action_info = self.sample_dict['seq_info'][0]['planning_output']
        img = cv_utils.convert_base64_to_cv2(base64_code=self.sample_dict['seq_info'][0]['image_relative_path'])
        img_w_vp, color = prompt_utils.make_visual_prompt(img, action_info['parsed_action'], save_hint="single_step")
        img2 = self.sample_dict['seq_info'][1]['image_relative_path']
        label = None
        thought = None

        if action_info['parsed_action']['action_type'] in ['clarify', 'done', 'finished']:
            thought = '此处没有操作故无需判定'
            label = '符合预期'
        elif action_info['parsed_action']['action_type'] in ['wait', 'do-nothing']:
            for _ in range(3):
                message = None
                try:
                    message = mllm.request_vlm(image=img2, user_query=single_image_prompts.wait_page_prompt)
                    parsed_res = json_utils.extract_json_from_string(message)
                    thought = parsed_res['Answer']
                    if thought in ['加载失败', '毛玻璃', '加载中']:
                        label = '不符合预期'
                    else:
                        label = '符合预期'
                except Exception as e:
                    print(f'HarmonyAPPSingleStepTest: run: API服务出现问题，重试...\n'
                          f'error: {e}\n'
                          f'message: {message}\n')
        elif action_info['parsed_action']['action_type'] in ['scroll', 'swipe', 'drag']:
            thought = '此处为滑动操作'
            label = '符合预期'

        else:

            for _ in range(3):
                message = None
                try:
                    img1_base64 = cv_utils.encode_image_to_base64(img_w_vp)
                    ### 设置request_vlm参数
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
                    message = mllm.request_vlm_ab_test(img1_path=img1_base64,
                                                       img2_path=img2,
                                                       prompt1=prompt1,
                                                       prompt2=prompt2,
                                                       prompt3=prompt3)
                    parsed_res = json_utils.extract_json_from_string(message)

                    thought = parsed_res['Thought']
                    label = parsed_res['Answer']
                    break
                except Exception as e:
                    print(f'HarmonyAPPSingleStepTest: run: API服务出现问题，重试...\n'
                          f'error: {e}\n'
                          f'message: {message}')

        result = {'判定结果': label, '判定依据': thought}
        return result


if __name__ == '__main__':
    json_data = json_utils.load_json(
        r'D:\GUI_TestFramework_v1\examples\0d18920e-1db0-4a46-a64d-17b59c1de6f1#1755847026352\data1.json')
    test_data = {'seq_info': []}
    test_data['seq_info'].append(json_data['seq_info'][0])
    test_data['seq_info'].append(json_data['seq_info'][1])
    newtest = HarmonyAPPSingleStepTest(test_data)
    print(newtest.run())
