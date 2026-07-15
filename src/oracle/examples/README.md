# /check_e2e 示例与重复动作/规划失效判定

本目录提供 `POST /check_e2e` 的完整调用示例，含重复动作判定和规划失效判定的输出说明。

## 接口速览

> 前提：`uvicorn main:app --host 0.0.0.0 --port 20025` 已启动

```
POST http://localhost:20025/check_e2e
Content-Type: application/json
```

该接口对一条完整的 Agent 执行轨迹做两件事：
1. **达尔文 E2E 判定** — 调用 VLM/LLM 做意图、路径、Plan 覆盖、单步 AB 页面判定
2. **异常检测后处理** — 基于达尔文产物，自动追加重复动作和规划失效检测

最终返回的 `check_result` 是全部判定的聚合 JSON。

---

## 输入字段

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `instruction` | string | 是 | 用户任务意图，如 `"在抖音首页点击视频进入播放页，然后点赞并收藏"` |
| `step_level_instruction` | string | 是 | 步骤级计划，用 `→` 分隔，用于 Plan 覆盖检查 |
| `seq_info` | array | 是 | 轨迹序列，每个元素包含一张截图和该步的 Agent 动作 |

### seq_info 元素

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `index` | int | 是 | 步骤编号，从 0 开始 |
| `image_relative_path` | string | 是 | **Base64 编码的截图**（字段名有误导性，实际传图片数据而非路径）。第 i 张是第 i 步动作"执行前"的页面 |
| `planning_output.parsed_action.action_type` | string | 是 | `click` / `long_press` / `type` / `scroll` / `swipe` / `wait` / `finished` |
| `planning_output.parsed_action.start_box` | [x, y] | 是 | Agent 实际执行坐标（非预期坐标），非点击类填 `[]` |
| `planning_output.parsed_action.end_box` | [x, y] | 是 | 滑动/拖拽终点，非此类填 `[]` |
| `planning_output.parsed_action.text` | string | 是 | 动作描述文本或输入文本 |
| `planning_output.parsed_action.direction` | string | 是 | 滑动方向，如 `up`/`down`/`left`/`right`，非此类填空 |

---

## 重复动作判定输出

正常轨迹：

```json
{
  "重复动作判定结果": "normal",
  "重复动作判定依据": "未发现重复动作异常。",
  "repeated_action_result": {
    "label": "normal",
    "type": "repeated_action",
    "severity": "none",
    "confidence": 0.0,
    "ranges": [],
    "summary": "未发现重复动作异常。",
    "metrics": { "action_count": 4, "repeated_range_count": 0 }
  }
}
```

检测到重复动作：

```json
{
  "重复动作判定结果": "abnormal",
  "重复动作判定依据": "检测到1段重复动作异常；首段位于步骤1到步骤2，动作为click，目标为点击点赞按钮。",
  "repeated_action_result": {
    "label": "abnormal",
    "type": "repeated_action",
    "severity": "medium",
    "confidence": 0.91,
    "ranges": [
      {
        "start_step": 1,
        "end_step": 2,
        "action_type": "click",
        "target": "点击点赞按钮",
        "repeat_type": "repeated_action",
        "severity": "medium",
        "confidence": 0.91,
        "evidence": [
          "步骤1和步骤2动作等效",
          "目标控件/动作描述相似度0.87",
          "期间无新增检查点达成",
          "达尔文单步判定结果为无法判定"
        ]
      }
    ]
  }
}
```

### 严重度说明

| 严重度 | 含义 |
|--------|------|
| `low` | 重复 2 次，轻微效率浪费 |
| `medium` | 重复 2-3 次，造成步骤浪费 |
| `high` | 重复 ≥3 次或循环，可能导致任务失败 |

---

## 规划失效判定输出

```json
{
  "规划失效判定结果": "normal",
  "规划失效判定依据": "未发现规划失效异常；Plan 覆盖率为 1.00。",
  "planning_failure_result": {
    "label": "normal",
    "type": "planning_failure",
    "subtype": "none",
    "severity": "none",
    "confidence": 0.0,
    "completion_score": 1.0,
    "missing_checkpoints": [],
    "summary": "未发现规划失效异常；Plan 覆盖率为 1.00。"
  }
}
```

检测到规划失效时，`subtype` 为以下之一：

| subtype | 含义 |
|---------|------|
| `premature_termination` | 提前终止：部分完成就 `finished` |
| `missing_required_step` | 遗漏必要步骤 |
| `fail_to_terminate` | 未能终止：目标达成后继续操作 |
| `objective_or_plan_mismatch` | 目标或路径规划不一致 |

---

## 快速运行

```bash
# 前提：模型服务已配好（conf/run_benchmark_config.conf）
# 从仓库根目录启动 Darwin 判定服务
cd src/oracle
uvicorn main:app --host 0.0.0.0 --port 20025

# 另一个终端：运行测试脚本
python examples/run_e2e.py --image-dir screenshots/
```

如果没有真实截图，脚本会自动生成占位图（虽然模型判定结果会不准确，但可验证请求格式和异常检测的串联逻辑）。

---

## 判定逻辑摘要

**重复动作判定**三条件（同时满足才判定异常）：

```
1. 动作等效：同类型（click/long_press 互认）、坐标距离 < 80px 或目标语义相似
2. 页面无进展：检查点数量未增加、页面语义相似度 ≥ 0.88
3. 不在白名单：非"重试/加载失败/多选/删除/退格"场景
```

**规划失效判定**四类检测：

```
1. 遗漏必要步骤：Plan 覆盖 < 100%，有未达成的 checkpoints
2. 提前终止：最后动作为 finished，但 completion_score < 阈值
3. 未能终止：Plan 已全部覆盖，但继续执行 ≥2 个非终止动作
4. 目标不一致：整体意图判定为 nok 或路径不一致
```
