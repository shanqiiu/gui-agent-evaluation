"""
@Project : utils_1.py
@File    : models
@Author  : weicai c30064476
@Date    : 2024/12/10 10:34
"""
from typing import Dict, Any, List, Tuple, Union, Optional
from pydantic import BaseModel


class PageInfoModel(BaseModel):
    index: int
    orgimg: str
    tagimg: str
    perception: Union[Dict[str, Any] | None] = None


class TargetModel(BaseModel):
    nodeLabel: str
    widgetName: str
    position: str


class ActionModel(BaseModel):
    index: int
    actionName: str
    action: str
    target: TargetModel


class AIAssistedScenarioDeterminationModel(BaseModel):
    modifiedIntention: str
    checkpointList: list[str]
    pageInfoList: List[PageInfoModel]
    actionList: List[ActionModel]


class BatchItem(BaseModel):
    task_list: list[dict[str, Any]]


class ActionInfo(BaseModel):
    layoutPath: str = None
    screenshotPath: str = None
    img: str
    layout: str
    operType: Optional[str] = None
    startBox: Optional[list] = []
    endBox: Optional[list] = []
    text: Optional[str] = None
    direction: Optional[str] = None

class ActionList(BaseModel):
    actionList: list[ActionInfo]


class ParsedAction(BaseModel):
    action_type: str
    start_box: list
    end_box: list
    text: str
    direction: str
    content: str = ""

class PlanningOutput(BaseModel):
    parsed_action: ParsedAction



class SeqInfo(BaseModel):
    index: int
    image_relative_path: str
    planning_output: PlanningOutput


class DataInfo(BaseModel):
    instruction: str
    step_level_instruction: str
    seq_info: List[SeqInfo]
