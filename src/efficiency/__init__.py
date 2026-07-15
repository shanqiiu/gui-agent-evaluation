"""src/efficiency — 效率分析器（模块C）

四维效率度量:
    ineffective_rate     — 无效操作比例
    exploratory_overhead — 探索性开销
    navigation_redundancy — 导航冗余
    scroll_efficiency    — 滑动效率

复合评分: efficient / moderate / inefficient
"""

from .models import (
    EfficiencyConfig,
    EfficiencyReport,
    IneffectiveAction,
    ExplorationCluster,
    NavigationLoop,
)
from .analyzer import EfficiencyAnalyzer, analyze_efficiency

__all__ = [
    "EfficiencyConfig",
    "EfficiencyReport",
    "IneffectiveAction",
    "ExplorationCluster",
    "NavigationLoop",
    "EfficiencyAnalyzer",
    "analyze_efficiency",
]
