import os
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
                "content": query_,
            }
        ],
        "top_p": top_p,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    headers = {"Content-Type": "application/json;charset=UTF-8"}
    api_key = os.environ.get("MLOPS_API_KEY", "")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    response = requests.post(url_, json=payload, headers=headers, verify=False, timeout=120)
    print(response.text)
    if response.ok:
        result_json = response.json()
        return result_json["choices"][0]["message"]["content"]

    print(f"request qwen server error! response status: {response.status_code}")
    return None


if __name__ == "__main__":
    query = """你好！"""
    start_time = time.time()
    answer = request_mlops_llms(query_=query,
                                url_="http://mlops.huawei.com/mlops-service/api/v1/agentService/v1/chat/completions",
                                model_name_="gpt-oss-120b",
                                top_p=1.0,
                                temperature=0,
                                max_tokens=1000)

    print(answer)
    print(f"time used: {time.time() - start_time}s")
