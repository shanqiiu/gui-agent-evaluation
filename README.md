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
# 从 utg.json + catchDataTurnId*/ 截图重组为扁平目录
python data/process_gui_end_to_end.py <原始数据目录> reorg_output/
```

### 3. 转换为判定格式并发送

```bash
# 批量转换 → 保存 payload + 发送判定 + 保存结果
python data/convert_to_check_e2e.py --batch reorg_output/ \
    --processed --send http://localhost:20025

# 输出目录:
#   payloads/{uuid}.json          ← 可复用的请求体
#   payloads/results/{uuid}_result.json  ← 判定结果
```

### 4. 复用已保存的 payload

```bash
# 无需重新转换，直接用 curl 重跑判定
curl -X POST http://localhost:20025/check_e2e \
  -H "Content-Type: application/json" \
  -d @payloads/<uuid>.json
```

## 达尔文判定集成

`FuncOracleCheck/` 是集成的达尔文功能判定模块：

| 端点 | 说明 |
|------|------|
| `POST /check_single_funck` | 单步功能判定（前后两张截图对比） |
| `POST /check_e2e` | E2E 序列判定，返回整体意图、路径一致性、Plan 覆盖、**重复动作**和**规划失效**判定 |
| `POST /upload_funcheck_task` | 提交异步队列任务 |
| `POST /get_check_result` | 查询异步任务结果 |

重复动作和规划失效检测器在达尔文 E2E 判定后自动追加，无需额外调用。详见 [examples/README.md](./FuncOracleCheck/examples/README.md)。

## 文档索引

| 文档 | 内容 |
|------|------|
| [技术方案](./docs/01-技术方案.md) | 四层架构、差分偏差三分类、检查点体系 |
| [论文调研](./docs/02-论文调研.md) | VeriGUI、TrajAD、GUI-SHEPHERD 等 17 篇 |
| [相关资源](./docs/03-相关资源.md) | GitHub 项目、数据集、工具链 |
| [架构设计](./docs/04-架构设计.md) | 架构图、数据流、模块交互 |
| [重复动作判定方案](./docs/重复动作异常判定技术方案.md) | 动作等效、目标等效、无进展三条件模型 |
| [规划失效判定方案](./docs/规划失效异常判定技术方案.md) | 五类规划失效 + 首错归因 |
| [数据格式说明](./data/data.md) | utg.json 数据结构、字段速查 |
| [E2E 调用示例](./FuncOracleCheck/examples/README.md) | /check_e2e 接口说明、场景测试 |

## 项目结构

```text
gui-agent-evaluation/
├── README.md
├── docs/                         # 设计文档
│   ├── 01-技术方案.md
│   ├── 02-论文调研.md
│   ├── 03-相关资源.md
│   ├── 04-架构设计.md
│   ├── 重复动作异常判定技术方案.md
│   ├── 规划失效异常判定技术方案.md
│   └── 进展汇总.md
├── data/                         # 数据处理管线
│   ├── data.md                   # utg.json 数据格式说明
│   ├── process_gui_end_to_end.py # 原始数据预处理（重组截图）
│   ├── convert_to_check_e2e.py   # utg.json → /check_e2e payload
│   └── test_convert_to_check_e2e.py
└── FuncOracleCheck/              # 判定服务
    ├── main.py                   # FastAPI 服务入口 (port 20025)
    ├── oracle_service.py         # 判定统一封装 + 检测器挂载
    ├── repeated_action_detector.py   # 重复动作检测器
    ├── planning_failure_detector.py  # 规划失效检测器
    ├── framework.py              # 单样本 CLI 调试
    ├── framework_batch_eval.py   # 批量 benchmark
    ├── quick_test.py             # API 快速测试脚本
    ├── examples/                 # 调用示例与文档
    │   ├── README.md
    │   ├── run_e2e.py
    │   └── sample_payload_base.json
    ├── tests/                    # 单元测试
    ├── app/                      # Pydantic 数据模型
    ├── oracle/                   # 功能 oracle 核心
    ├── GUI_TestFramework_v1/     # MLLM/VLM 判定框架
    ├── utils/                    # 图像/JSON/布局工具
    └── conf/                     # 运行配置
```

## 数据流

```
Agent 原始数据                    预处理                转换                    判定服务
┌──────────────┐    ┌──────────────────────┐    ┌──────────────────┐    ┌──────────────┐
│ utg.json     │    │ process_gui_         │    │ convert_to_      │    │ POST         │
│ catchData    │───▶│ end_to_end.py        │───▶│ check_e2e.py     │───▶│ /check_e2e   │
│ TurnId*/     │    │                      │    │                  │    │              │
│   *.jpg      │    │ → 0.jpg, 1.jpg, ...  │    │ → payload JSON   │    │ → 重复动作判定 │
└──────────────┘    │ → _processed.json    │    │ → base64 截图     │    │ → 规划失效判定 │
                    └──────────────────────┘    │ → 保存复用        │    └──────────────┘
                                                └──────────────────┘
```
