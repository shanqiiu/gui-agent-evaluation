import os
import json
import time

import requests


def request_mlops_llms(query_: str = None,
                       url_="http://mlops.huawei.com/mlops-service/api/v1/agentService/v1/chat/completions",
                       model_name_="DeepSeek-R1-Distill-Qwen-32B-20250122170201",
                       top_p=1e-3,
                       temperature=1e-3,
                       max_tokens=1000):
    payload = {
        "model": model_name_,
        "messages": [
            {
                "role": "user",
                "content": query_
            }
        ],

        "top_p": top_p,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    headers = {
        'Authorization': 'Bearer sk-eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJkZXBhcnRtZW50TmFtZSI6IuWPr-S_oea1i-ivleW3peeoi-WunumqjOWupCIsImFjY291bnRJZCI6IngwMDU4NDk5NSIsImtleVZlcnNpb24iOiIyLjAiLCJhY2NvdW50TmFtZSI6Inh1ZXhpZGkiLCJ0ZW5hbnRJZCI6ImYyOGNlNWNjZGU5MTM4ZTMyZTQ5YjYyZDVmZjk3MGFjIn0.hp1pBoLR_Pbtn7yqYU9izYeLREq7-lHxCnk8Zl3cxVU',
        "Content-Type": "application/json;charset=UTF-8"
    }

    response = requests.post(url_, json.dumps(payload), headers=headers, verify=False)
    print(response.text)
    if response.ok:
        result_json = response.json()
        # print(result_json)
        message = result_json['choices'][0]['message']['content']
        return message
    else:
        print(f"request qwen server error! response status: {response.status_code}")
        return None


if __name__ == '__main__':
    query = """你好！"""
    start_time = time.time()
    answer = request_mlops_llms(query_=query,
                                url_="http://mlops.huawei.com/mlops-service/api/v1/agentService/v1/chat/completions",
                                model_name_="gpt-oss-120b",
                                top_p=1.0,
                                temperature=0,
                                max_tokens=1000)

    print(answer)
    pass
