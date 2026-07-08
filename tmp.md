{
  "整体意图测试结果": "ok",
  "整体意图测试结果判断依据": "执行成功",
  "路径一致性测试结果": "ok",
  "缺失的功能": [],
  "存在问题的功能": [],
  "Plan步骤数": 1,
  "执行覆盖Plan步骤数": 1,
  "已覆盖Plan": [
    {
      "Plan步骤名": "输入文本→点击定时开关机→等待/检查",
      "覆盖Plan步骤的执行步骤序号": 2,
      "整体通过情况": "通过",
      "结果分类": "成功",
      "存在bug的执行步骤": {}
    }
  ],
  "未覆盖Plan": [],
  "重复动作判定结果": "normal",
  "重复动作判定依据": "未发现重复动作异常。",
  "repeated_action_result": {
    "label": "normal",
    "type": "repeated_action",
    "severity": "none",
    "confidence": 0.0,
    "ranges": [],
    "summary": "未发现重复动作异常。",
    "metrics": {
      "action_count": 4,
      "repeated_range_count": 0
    }
  },
  "规划失效判定结果": "normal",
  "规划失效判定依据": "未发现规划失效异常；Plan 覆盖率为 1.00。",
  "planning_failure_result": {
    "label": "normal",
    "type": "planning_failure",
    "subtype": "none",
    "severity": "none",
    "confidence": 0.0,
    "first_error_step": -1,
    "completion_score": 1.0,
    "total_plan": 1,
    "covered_plan": 1,
    "missing_checkpoints": [],
    "bug_steps": [],
    "related_anomalies": [],
    "evidence": [],
    "events": [],
    "summary": "未发现规划失效异常；Plan 覆盖率为 1.00。"
  }
}
