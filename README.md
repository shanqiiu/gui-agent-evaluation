# GUI Agent 执行轨迹自动判定

> 构建针对 AI 智能体的自动化测试评估系统，实现对多模态 GUI Agent 任务执行合理性、结果正确性、执行效率的自动判定。

## 核心能力

- **执行轨迹合理性判定**：基于操作前后截图，检测 Agent 操作是否出现异常，覆盖重复动作和规划失效等轨迹异常
- **结果正确性判定**：综合关键检查点和达尔文功能判定结果，评估任务是否达成
- **执行效率判定**：通过实际动作坐标、控件语义和 Plan 进展检测重复操作和无效操作

## 快速开始

### 1. 启动判定服务

```bash
cd FuncOracleCheck
pip install -r requirements.txt
# 配置 conf/run_benchmark_config.conf 中的模型地址
uvicorn main:app --host 0.0.0.0 --port 20025
```

### 2. 预处理 Agent 原始数据

```bash
# 从 utg.json + catchDataTurnId*/ 截图重组为扁平目录（文件按 catchDataTurnId 命名）
python data/process_gui_end_to_end.py <原始数据目录> reorg_output/
```

### 3. 转换为判定格式并发送

```bash
# 批量转换 → 保存 payload + 发送判定 + 保存结果
# 支持断点续跑：已存在的 payload 自动跳过
python data/convert_to_check_e2e.py --batch reorg_output/ \
    --processed --send http://localhost:20025

# 输出目录:
#   payloads/{uuid}.json              ← 可复用的请求体（存路径而非 base64）
#   payloads/results/{uuid}_result.json  ← 判定结果
```

### 4. 复用已保存的 payload

```bash
# 方式1: curl 直接发（需先用 send_payload.py 的 --hydrate 转换）
python data/send_payload.py payloads/<uuid>.json --hydrate -o hydrated.json
curl -X POST http://localhost:20025/check_e2e -H "Content-Type: application/json" -d @hydrated.json

# 方式2: send_payload 直接发
python data/send_payload.py payloads/ --send http://localhost:20025
```

## 数据管线

```
Agent 原始数据                     预处理                      转换                       判定服务
┌──────────────────┐    ┌─────────────────────┐    ┌─────────────────────┐    ┌──────────────┐
│ utg.json         │    │ process_gui_        │    │ convert_to_         │    │ POST         │
│ nodes → stepData │    │ end_to_end.py       │    │ check_e2e.py        │    │ /check_e2e   │
│   → directives   │    │                     │    │                     │    │              │
│                  │───▶│ catchDataTurnIdN.jpg │───▶│ parse_node_         │───▶│ Darwin VLM   │
│ catchDataTurnId*/│    │ (按 turn ID 命名)    │    │ directives()        │    │   AB判定     │
│   *.jpg          │    │                     │    │ step_action_to_     │    │   意图判定    │
│                  │    │                     │    │ text()              │    │   Plan覆盖   │
│ 节点截图      │    │                     │    │ resolve_image_      │    │              │
│ 元素文本      │    │                     │    │ from_url()          │    │ 重复动作判定  │
│ 操作坐标      │    │                     │    │                     │    │ 规划失效判定  │
└──────────────────┘    └─────────────────────┘    └─────────────────────┘    └──────────────┘
```

### 转换映射

| utg.json 来源 | /check_e2e 字段 |
|---|---|
| `node.raw_item.directives` JSON 解析 | `parsed_action.action_type`（edit→type, preCheckDone→do-nothing） |
| `params.points` / `node.bounds` 中心 | `parsed_action.start_box` / `end_box` |
| `params.node.text` | `parsed_action.text`（如 "点击隐私和安全"） |
| `params.node.content` / `setText` | `parsed_action.content` |
| `stepData.action_type` 解析 | `parsed_action.direction` |
| `node.image` REST URL → 本地文件 | `image_relative_path`（发送时转 base64） |
| `node.image` REST URL | `_image_source`（溯源地址） |
| 节点遍历 + `raw_item.directives` 过滤 | 自动跳过思考/反射步骤 |

### 截图三级兜底

1. 用自己节点的 `node.image` → 读本地文件
2. 文件不存在 → 用前一个节点的截图（`last_loaded` 追踪）
3. 仍为空 → `image_relative_path = ""`

## 判定结果字段说明

| 字段 | 来源模块 | 含义 |
|------|---------|------|
| **Darwin E2E 判定**（VLM+LLM） | | |
| `整体意图测试结果` | 序列意图判定 | 整个任务目标是否达成 |
| `路径一致性测试结果` | 意图步骤匹配 | 实际执行路径与 Plan 是否一致 |
| `Plan步骤数` / `执行覆盖Plan步骤数` | `step_level_instruction` 分解 | Plan 步骤总数/达成数 |
| `缺失的功能` / `存在问题的功能` | 步骤覆盖率 | 未匹配到页面的步骤 / 有 bug 的步骤 |
| **重复动作判定**（规则，寄生达尔文） | | |
| `重复动作判定结果` | `repeated_action_detector` | `normal`=无重复, `abnormal`=有重复 |
| `repeated_action_result.ranges` | 检测器输出 | 重复区间起止步、动作类型、证据 |
| **规划失效判定**（规则，寄生达尔文+重复结果） | | |
| `规划失效判定结果` | `planning_failure_detector` | `normal`=无失效, 四种子类型 |
| `planning_failure_result.completion_score` | Plan 覆盖计算 | covered/total |
| `planning_failure_result.subtype` | 检测器分类 | `missing_required_step` / `premature_termination` / `fail_to_terminate` / `objective_or_plan_mismatch` |

### 三者执行顺序

```
Darwin E2E 判定（VLM+LLM）
  ├─ AB 页面跳转判定 → 每步是否符合预期
  ├─ 意图判定 → 整体任务是否达成
  └─ Plan 分解与覆盖 → step_level_instruction → 检查点达成状态
       ↓
重复动作检测（纯规则，读 Darwin 的 AB 标签 + 检查点覆盖）
  └─ 比对相邻步骤的动作/目标/页面进展 → 是否重复
       ↓
规划失效检测（纯规则，读 Darwin + 重复动作结果）
  └─ 分析 Plan 覆盖 + 终止时机 → 是否规划出错
```

## 达尔文判定集成

`FuncOracleCheck/` 是集成的达尔文功能判定模块：

| 端点 | 说明 |
|------|------|
| `POST /check_single_funck` | 单步功能判定（前后两张截图对比） |
| `POST /check_e2e` | E2E 序列判定，返回整体意图、路径一致性、Plan 覆盖、**重复动作**和**规划失效**判定 |
| `POST /upload_funcheck_task` | 提交异步队列任务 |
| `POST /get_check_result` | 查询异步任务结果 |

详见 [E2E 调用示例](./FuncOracleCheck/examples/README.md)。

## 文档索引

| 文档 | 内容 |
|------|------|
| [技术方案](./docs/01-技术方案.md) | 四层架构、差分偏差三分类、检查点体系 |
| [论文调研](./docs/02-论文调研.md) | VeriGUI、TrajAD、GUI-SHEPHERD 等 17 篇 |
| [相关资源](./docs/03-相关资源.md) | GitHub 项目、数据集、工具链 |
| [架构设计](./docs/04-架构设计.md) | 架构图、数据流、模块交互 |
| [重复动作判定方案](./docs/重复动作异常判定技术方案.md) | 动作等效、目标等效、无进展三条件模型 |
| [规划失效判定方案](./docs/规划失效异常判定技术方案.md) | 五类规划失效 + 首错归因 |
| [纯文本轻量判定方案](./docs/纯文本轻量判定方案.md) | 不依赖 VLM 的备选降级方案 |
| [数据格式说明](./data/data.md) | utg.json 数据结构、字段速查 |
| [进展汇总](./docs/进展汇总.md) | 工作进展与当前状态 |
| [E2E 调用示例](./FuncOracleCheck/examples/README.md) | /check_e2e 接口说明、场景测试 |

## 项目结构

```text
gui-agent-evaluation/
├── README.md
├── docs/                              # 设计文档
│   ├── 01-技术方案.md
│   ├── 02-论文调研.md
│   ├── 03-相关资源.md
│   ├── 04-架构设计.md
│   ├── 重复动作异常判定技术方案.md
│   ├── 规划失效异常判定技术方案.md
│   └── 进展汇总.md
├── data/                              # 数据处理管线
│   ├── data.md                        # utg.json 数据格式说明
│   ├── process_gui_end_to_end.py      # 原始数据预处理（截图重组 + turn ID 命名）
│   ├── convert_to_check_e2e.py        # utg.json → /check_e2e payload 转换器
│   ├── send_payload.py                # 已保存 payload 重发工具
│   └── test_convert_to_check_e2e.py   # 核心逻辑测试（10 项）
└── FuncOracleCheck/                   # 判定服务
    ├── main.py                        # FastAPI 服务入口 (port 20025)
    ├── oracle_service.py              # 判定统一封装 + 检测器挂载
    ├── repeated_action_detector.py    # 重复动作检测器（规则）
    ├── planning_failure_detector.py   # 规划失效检测器（规则）
    ├── framework.py                   # 单样本 CLI 调试
    ├── framework_batch_eval.py        # 批量 benchmark
    ├── quick_test.py                  # API 快速测试脚本
    ├── examples/                      # 调用示例与文档
    │   ├── README.md
    │   ├── run_e2e.py
    │   └── sample_payload_base.json
    ├── tests/                         # 单元测试
    ├── app/models.py                  # Pydantic 数据模型（含 content 字段）
    ├── oracle/                        # 功能 oracle 核心
    ├── GUI_TestFramework_v1/          # MLLM/VLM 判定框架
    ├── utils/                         # 图像/JSON/布局工具 + visual_prompt_debug
    ├── library/logger.py              # 日志配置（logs/info.log 按天滚动）
    └── conf/                          # 运行配置
```
