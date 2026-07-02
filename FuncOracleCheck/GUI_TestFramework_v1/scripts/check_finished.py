from utils import json_utils
import os

root_dir = '/home/zhehuan/Harmony_APP_TestFramework/benchmark'
cnt = 0
cnt_f = 0
for sub in os.listdir(root_dir):
    sub_dir = os.path.join(root_dir, sub)

    if os.path.exists(os.path.join(sub_dir, f'{sub.split("#")[0]}.json')):
        json_data = json_utils.load_json(os.path.join(sub_dir, f'{sub.split("#")[0]}.json'))
        if json_data[0]['valid_data'] :
            cnt += 1
        else:
            cnt_f += 1

print(cnt, cnt_f)
