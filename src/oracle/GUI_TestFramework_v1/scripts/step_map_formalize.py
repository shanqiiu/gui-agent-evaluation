from utils import json_utils
import os
from uuid import uuid4
import re

def reformat(txt):
    lines = txt.split('\n')

    # 存储所有提取的步骤
    all_steps = []

    for line in lines:
        # 去除序号（匹配开头的数字和中文符号“、”）
        step_part = re.sub(r'^\d+[、.]\s*', '', line)
        # 按#分割当前行的步骤
        sub_steps = step_part.split('#')
        # 添加到总列表
        all_steps.extend(sub_steps)
    return all_steps


root_dir = '/home/zhehuan/Harmony_APP_TestFramework/benchmark'
cnt = 0
for sub in os.listdir(root_dir):
    sub_dir = os.path.join(root_dir, sub)

    if os.path.exists(os.path.join(sub_dir, f'{sub.split("#")[0]}.json')):
        json_data = json_utils.load_json(os.path.join(sub_dir, f'{sub.split("#")[0]}.json'))
        if '->' not in json_data[0]['step_level_instruction']:
            result = reformat(json_data[0]['step_level_instruction'])
            json_data[0]['step_level_instruction'] = '->'.join(result)
            json_data[0]['step_maps'].clear()
            for step in result:
                step_map = {
                    'step_text_id': str(uuid4()),
                    'step_text': step,
                    'step_map_images':[],
                    'step_verify': False,
                }
                json_data[0]['step_maps'].append(step_map)
            print(sub)
            cnt += 1
            json_utils.dump_json(json_data, os.path.join(sub_dir, f'{sub.split("#")[0]}.json'))


print(cnt)
