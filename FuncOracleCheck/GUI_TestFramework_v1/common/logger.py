# utils/logger.py（核心配置文件）
import os
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime

# 全局日志实例（确保只初始化一次）
_global_logger = None


def get_logger(
        name = 'default',
        log_dir="logs",
        level=logging.INFO,
        log_format=None
):
    """
    统一获取日志实例的接口，确保全局唯一
    :param name: 日志名称（不同模块可传不同name，便于定位日志来源）
    """
    global _global_logger

    # 1. 若已初始化，直接返回（避免重复添加处理器）
    if _global_logger is not None:
        return _global_logger

    # 2. 初始化日志实例
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False  # 关闭向上传播（避免root logger重复输出）

    # 3. 创建日志目录
    os.makedirs(log_dir, exist_ok=True)

    # 4. 定义日志格式（包含：时间、日志名、级别、模块、行号、消息）
    if log_format is None:
        log_format = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(module)s:%(lineno)d - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"  # 时间格式更清晰
        )

    # 5. 控制台处理器（实时查看）
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(log_format)
    logger.addHandler(console_handler)

    # 6. 文件处理器（持久化保存，按大小切割）
    log_filename = f"{name}_{datetime.now().strftime('%m_%d_%H_%M_%S')}.log"
    log_filepath = os.path.join(log_dir, log_filename)
    file_handler = RotatingFileHandler(
        log_filepath,
        encoding="utf-8"  # 支持中文日志
    )
    file_handler.setFormatter(log_format)
    logger.addHandler(file_handler)

    # 7. 赋值给全局变量，后续调用直接返回
    _global_logger = logger
    return logger


# 提供一个默认的全局日志实例（简化调用）
default_logger = get_logger()
