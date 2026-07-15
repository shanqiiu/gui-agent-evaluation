"""src/trajectory — 轨迹差分判定器（模块D）

三分类判定模型：
    no_impact  — 无影响偏差：不同路径，结果一致
    remedial   — 补救性偏差：早期次优，后续修正
    cascading  — 级联偏差：小错放大，导致失败
"""

from .models import (
    DeviationPoint,
    TrajectoryDeviation,
    DifferentialJudgerConfig,
)
from .differential_judger import DifferentialJudger, judge_trajectory

__all__ = [
    "DeviationPoint",
    "TrajectoryDeviation",
    "DifferentialJudgerConfig",
    "DifferentialJudger",
    "judge_trajectory",
]
