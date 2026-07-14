"""src/preprocessor — 数据预处理管线

统一入口: pipeline.py (preprocess → 3x write)
数据解析: preprocessor.py + clearres_parser.py
输出生成: write_payload.py / write_dedup.py / write_stategraph.py
工具脚本: send_payload.py
"""

from .models import NormalizedTask, NormalizedStep
from .clearres_parser import parse_clearres, parse_clearres_light

__all__ = [
    "NormalizedTask",
    "NormalizedStep",
    "parse_clearres",
    "parse_clearres_light",
]
