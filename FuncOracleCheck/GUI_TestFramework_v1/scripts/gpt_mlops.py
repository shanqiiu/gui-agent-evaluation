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
        choices = result_json.get("choices") if isinstance(result_json, dict) else None
        if choices:
            first_choice = choices[0]
            if isinstance(first_choice, dict):
                message = first_choice.get("message")
                if isinstance(message, dict) and "content" in message:
                    return message["content"]
                if "text" in first_choice:
                    return first_choice["text"]
        for key in ("content", "text", "response", "message", "answer"):
            value = result_json.get(key) if isinstance(result_json, dict) else None
            if isinstance(value, str):
                return value
        print(f"request qwen server response missing choices/content: {result_json}")
        return None

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
