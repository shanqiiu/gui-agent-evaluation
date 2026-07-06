import os
import time

os.environ["http_proxy"] = ""
os.environ["https_proxy"] = ""
os.environ["no_proxy"] = "localhost,127.0.0.1,.huawei.com"

import requests

from GUI_TestFramework_v1.scripts import config
from GUI_TestFramework_v1.api_service.prompts import intention_predicate
from GUI_TestFramework_v1.api_service.mllm_data_collector.data_collector import log_mllm_interactions


if hasattr(config.Config(), "mllm_data_collector"):
    LLM_LOG_DIR = config.Config().mllm_data_collector.llm_log_saved_dir
    VLM_LOG_DIR = config.Config().mllm_data_collector.vlm_log_saved_dir
    ENABLE_LOG = config.Config().mllm_data_collector.enable_log
else:
    LLM_LOG_DIR = None
    VLM_LOG_DIR = None
    ENABLE_LOG = False


class ModelResponseError(RuntimeError):
    pass


def _resolve_api_key(explicit_key: str = None, env_name: str = None) -> str:
    if explicit_key:
        return explicit_key
    if env_name:
        return os.environ.get(env_name, "")
    return ""


def _headers(api_key: str = None):
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _request_timeout() -> int:
    return config.Config().model.REQUEST_TIMEOUT


def _include_top_k() -> bool:
    return config.Config().model.INCLUDE_TOP_K


def _add_sampling_params(payload: dict, top_k: int = None, top_p: float = None, temperature: float = None):
    if top_p is not None:
        payload["top_p"] = top_p
    if temperature is not None:
        payload["temperature"] = temperature
    if top_k is not None and _include_top_k():
        payload["top_k"] = top_k


def _truncate(value, limit: int = 1000) -> str:
    text = str(value)
    if len(text) > limit:
        return text[:limit] + "..."
    return text


def _extract_message_content(result_json, endpoint_name: str, server_url: str):
    if not isinstance(result_json, dict):
        raise ModelResponseError(
            f"{endpoint_name} returned non-object JSON from {server_url}: {_truncate(result_json)}"
        )

    choices = result_json.get("choices")
    if choices:
        first_choice = choices[0]
        if isinstance(first_choice, dict):
            message = first_choice.get("message")
            if isinstance(message, dict) and "content" in message:
                return message["content"]
            if "text" in first_choice:
                return first_choice["text"]

    for key in ("content", "text", "response", "message", "answer"):
        value = result_json.get(key)
        if isinstance(value, str):
            return value

    error = result_json.get("error") or result_json.get("detail")
    if error:
        raise ModelResponseError(
            f"{endpoint_name} returned error JSON from {server_url}: {_truncate(error)}"
        )

    raise ModelResponseError(
        f"{endpoint_name} response missing choices/content from {server_url}; "
        f"keys={list(result_json.keys())}; body={_truncate(result_json)}"
    )


@log_mllm_interactions(log_dir=LLM_LOG_DIR, enable_log=ENABLE_LOG)
def request_llm(user_str=None,
                temperature=1e-2,
                top_k=1,
                top_p=0.2,
                max_new_tokens=6000,
                url_=None,
                model_name_=None,
                stop_words_: list = None):
    model_cfg = config.Config().model
    if url_ is None:
        url_ = model_cfg.LLM_MODEL_URL
    if model_name_ is None:
        model_name_ = model_cfg.LLM_MODEL_NAME

    api_key = _resolve_api_key(model_cfg.LLM_API_KEY, model_cfg.LLM_API_KEY_ENV)
    headers = _headers(api_key)

    for _ in range(3):
        try:
            payload = {
                "model": model_name_,
                "messages": [
                    {
                        "role": "user",
                        "content": user_str,
                    }
                ],
                "n": 1,
                "max_tokens": max_new_tokens,
            }
            _add_sampling_params(payload, top_k=top_k, top_p=top_p, temperature=temperature)
            if stop_words_:
                payload["stream"] = False
                payload["stop"] = stop_words_

            response = requests.post(url_, json=payload, headers=headers, verify=False, timeout=_request_timeout())
            if response.ok:
                return _extract_message_content(response.json(), "LLM", url_)
            print(f"request LLM server error! response status: {response.status_code}\n"
                  f"payload: {_truncate(payload)}\n"
                  f"response: {_truncate(response.text)}")
        except Exception as e:
            print(f"request LLM server error: {e}")
    print("请求LLM服务3次均失败, 返回None.")
    return None


@log_mllm_interactions(log_dir=VLM_LOG_DIR, enable_log=ENABLE_LOG)
def request_vlm(user_query=None,
                server_url=None,
                image=None,
                temperature=1e-2,
                top_k=1,
                top_p=1e-2,
                n=1,
                model_name=None,
                max_tokens=6000,
                messages=None):
    model_cfg = config.Config().model
    if server_url is None:
        server_url = model_cfg.VLM_MODEL_URL
    if model_name is None:
        model_name = model_cfg.VLM_MODEL_NAME
    if not messages:
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": user_query,
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{image}",
                        },
                    },
                ],
            }
        ]

    payload = {
        "model": model_name,
        "messages": messages,
        "n": n,
        "max_tokens": max_tokens,
        "stream": False,
    }
    _add_sampling_params(payload, top_k=top_k, top_p=top_p, temperature=temperature)

    api_key = _resolve_api_key(model_cfg.VLM_API_KEY, model_cfg.VLM_API_KEY_ENV)
    try:
        response = requests.post(
            server_url,
            headers=_headers(api_key),
            json=payload,
            verify=False,
            timeout=_request_timeout(),
        )
        if response.ok:
            return _extract_message_content(response.json(), "VLM", server_url)

        print(f"request VLM server error! response status: {response.status_code}\n"
              f"response: {_truncate(response.text)}")
    except Exception as e:
        print(f"request VLM server error: {e}")
    return None


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
    messages = [
        {
            "role": "system",
            "content": [{"type": "text", "text": "You are a helpful assistant."}],
        },
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt1},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img1_path}"}},
                {"type": "text", "text": prompt2},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img2_path}"}},
                {"type": "text", "text": prompt3},
            ],
        },
    ]

    return request_vlm(user_query=None,
                       image=None,
                       temperature=temperature,
                       top_k=top_k,
                       top_p=top_p,
                       n=n,
                       server_url=server_url,
                       model_name=model_name,
                       max_tokens=max_tokens,
                       messages=messages)


if __name__ == "__main__":
    start_time = time.time()
    print(request_llm(user_str="1+1=?", max_new_tokens=5000))
    print(f"time used: {time.time() - start_time}s")
