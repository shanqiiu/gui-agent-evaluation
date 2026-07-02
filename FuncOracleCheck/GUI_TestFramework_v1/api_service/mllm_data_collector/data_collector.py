import os
import uuid
from functools import wraps
from typing import Callable

from utils import json_utils


def log_mllm_interactions(log_dir: str = None, enable_log: bool = False):
    """带参数的装饰器，记录LLM/VLM请求的输入和输出到指定目录"""

    def decorator(func: Callable):
        @wraps(func)  # 保留原函数的名称和元信息
        def wrapper(*args, **kwargs):

            if log_dir and enable_log:
                # 确保日志目录存在
                os.makedirs(log_dir, exist_ok=True)

            # 记录输入
            input_data = {"args": args, "kwargs": kwargs}

            # 调用原函数并获取输出
            output_data = func(*args, **kwargs)

            # 准备日志条目
            log_entry = {
                "function": func.__name__,  # 增加函数名记录
                "input": input_data,
                "output": output_data
            }

            if log_dir and enable_log:
                # 日志文件路径（使用函数名作为文件名区分不同函数）
                log_file_path = os.path.join(log_dir, f"{func.__name__}_{str(uuid.uuid4())}_log.json")
                json_utils.dump_json(data_=log_entry, tar_=log_file_path, ensure_ascii=False, indent_=2)

            # 返回原函数的输出
            return output_data

        return wrapper

    return decorator


if __name__ == '__main__':
    pass
