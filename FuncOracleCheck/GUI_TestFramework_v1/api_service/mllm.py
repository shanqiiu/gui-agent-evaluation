import os
import time

os.environ["http_proxy"] = ""
os.environ["https_proxy"] = ""
os.environ["no_proxy"] = "localhost,127.0.0.1,.huawei.com"

import json
import requests

import sys

from GUI_TestFramework_v1.scripts import config
from GUI_TestFramework_v1.api_service.prompts import ab_test_prompts, sequence_split_prompts, single_image_prompts, \
    intention_predicate
from GUI_TestFramework_v1.api_service.mllm_data_collector.data_collector import log_mllm_interactions
from utils import cv_utils, json_utils, prompt_utils


if hasattr(config.Config(), 'mllm_data_collector'):
    LLM_LOG_DIR = config.Config().mllm_data_collector.llm_log_saved_dir
    VLM_LOG_DIR = config.Config().mllm_data_collector.vlm_log_saved_dir
    ENABLE_LOG = config.Config().mllm_data_collector.enable_log
else:
    LLM_LOG_DIR = None
    VLM_LOG_DIR = None
    ENABLE_LOG = False

# MLOPS API 认证 token，优先从环境变量读取
MLOPS_API_KEY = os.environ.get(
    "MLOPS_API_KEY",
    "sk-eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhY2NvdW50SWQiOiJqMDA5NTYyNDQiLCJhY2NvdW50TmFtZSI6ImppYW5nYm93ZWkiLCJkZXBhcnRtZW50TmFtZSI6InVua25vd24iLCJ0ZW5hbnRJZCI6ImU0YTQ0NTcxYTlmYzE0MTE1ZmViYmJhNWRhNzZhNmEzIiwia2V5VmVyc2lvbiI6IjIuMCJ9.08kKW8bkq4eU2LabqXb4c51ZJ5EGBQcELhovG_0HVrw"
)


def _mlops_headers():
    """返回 MLOPS 请求 headers，含 Authorization token。"""
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {MLOPS_API_KEY}",
    }

@log_mllm_interactions(log_dir=LLM_LOG_DIR, enable_log=ENABLE_LOG)
def request_llm(user_str=None,
                temperature=1e-2,
                top_k=1,
                top_p=0.2,
                max_new_tokens=6000,
                url_=None,
                model_name_=None,
                stop_words_: list = None):
    if url_ is None:
        url_ = config.Config().model.LLM_MODEL_URL
    if model_name_ is None:
        model_name_ = config.Config().model.LLM_MODEL_NAME
    for _ in range(3):
        try:
            if not stop_words_:
                payload = {
                    "model": model_name_,
                    "messages": [
                        {
                            "role": "user",
                            "content": user_str
                        }
                    ],
                    "top_k": top_k,
                    "top_p": top_p,
                    "temperature": temperature,
                    "n": 1,
                    "max_tokens": max_new_tokens,
                }
            else:
                payload = {
                    "model": model_name_,
                    "messages": [
                        {
                            "role": "user",
                            "content": user_str
                        }
                    ],
                    "top_k": top_k,
                    "top_p": top_p,
                    "temperature": temperature,
                    "n": 1,
                    "max_tokens": max_new_tokens,
                    "stream": False,
                    "stop": stop_words_
                }

            headers = _mlops_headers()
            response = requests.post(url_, json.dumps(payload), headers=headers, verify=False)
            if response.ok:
                result_json = response.json()
                message = result_json['choices'][0]['message']['content']
                return message
            else:
                print(f"request LLM server error! response status: {response.status_code}\n"
                      f"payload: {payload}\n"
                      f"response: {response.text}")
        except Exception as e:
            print(e)
    else:
        print(f"请求LLM服务3次均失败, 返回None.")
        return None


@log_mllm_interactions(log_dir=VLM_LOG_DIR, enable_log=ENABLE_LOG)
def request_vlm(user_query=None,
                server_url=None,
                image=None,
                temperature=1e-2,
                top_k=1,
                top_p=1e-2, n=1,
                model_name=None,
                max_tokens=6000,
                messages=None):
    if server_url is None:
        server_url = config.Config().model.VLM_MODEL_URL
    if model_name is None:
        model_name = config.Config().model.VLM_MODEL_NAME
    if not messages:
        image_base64 = image
        messages = [
            {
                'role': 'user',
                'content': [
                    {
                        'type': 'text',
                        'text': user_query
                    },
                    {
                        'type': 'image_url',
                        'image_url': {
                            'url': f"data:image/jpeg;base64,{image_base64}",
                        },
                    }
                ]
            }]

    payload = {
        "model": model_name,
        "messages": messages,
        "top_k": top_k,
        "top_p": top_p,
        "temperature": temperature,
        "n": n,
        "max_tokens": max_tokens,
        "stream": False
    }

    headers = _mlops_headers()
    response = requests.post(server_url, headers=headers, json=payload, verify=False)
    if response.ok:
        result_json = response.json()
        message = result_json['choices'][0]['message']['content']

    else:
        print(f"request VLM server error! response status: {response.status_code}")
        message = None
    return message


def request_llm_intention_predicate(temperature=1e-2,
                                    top_k=1,
                                    top_p=0.2,
                                    max_new_tokens=6000,
                                    url_=None,
                                    model_name_=None,
                                    stop_words_: list = None,
                                    intention: str = None,
                                    intention_history: dict = None):
    user_str = intention_predicate.prompt.format(intention_history=intention_history, intention=intention)
    return request_llm(user_str=user_str,
                       temperature=temperature,
                       top_k=top_k,
                       top_p=top_p,
                       max_new_tokens=max_new_tokens,
                       url_=url_,
                       model_name_=model_name_,
                       stop_words_=stop_words_)


def request_vlm_ab_test(img1_path=None,
                        img2_path=None,
                        prompt1=None,
                        prompt2=None,
                        prompt3=None,
                        temperature=1e-2,
                        top_k=1,
                        top_p=1e-2,
                        n=1,
                        server_url=None,
                        model_name=None,
                        max_tokens=6000):
    image1_base64 = img1_path
    image2_base64 = img2_path

    messages = [
        {
            "role": "system",
            "content": [{"type": "text", "text": "You are a helpful assistant."}]
        },
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt1},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image1_base64}"}},
                {"type": "text", "text": prompt2},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image2_base64}"}},
                {"type": "text", "text": prompt3}
            ]
        }
    ]

    return request_vlm(user_query=None,
                       image=None,
                       temperature=temperature,
                       top_k=top_k,
                       top_p=top_p, n=n,
                       server_url=server_url,
                       model_name=model_name,
                       max_tokens=max_tokens,
                       messages=messages)


if __name__ == '__main__':
    start_time = time.time()
    u_str = """1+1=?"""
    print(request_llm(user_str=u_str,
                      max_new_tokens=5000,
                      url_="http://10.90.86.76:8198/v1/chat/completions",
                      model_name_="gpt-oss-120b"))
    # print(request_vlm(user_query="图片中有什么内容？",
    #                   image=cv_utils.encode_image_to_base64(image=r"/home/zhehuan/DeepOracle/DeepOracle/810_data/multi_task/eval_data/eval_images/1d4d7d4c-2d98-470e-98bc-4fa2ce5135cf/370dce8c-6ac0-404a-b78e-a1f789cb9f46.jpeg"),
    #                   server_url="http://10.90.86.76:8055/v1/chat/completions",
    #                   model_name="Qwen2.5-VL-32B-Instruct-AWQ"))

    # print(f"time used: {time.time() - start_time}s")
    pass
