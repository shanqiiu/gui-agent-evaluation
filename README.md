# GUI Agent 执行轨迹自动判定

> 项目定位：构建针对 AI 智能体的自动化测试评估系统，实现对多模态 GUI Agent 任务执行合理性、结果正确性、执行效率的自动判定。

## 核心能力

- **执行轨迹合理性判定**：基于操作前后截图，检测 Agent 操作是否出现异常，覆盖重复动作和规划失效等轨迹异常
- **结果正确性判定**：综合关键检查点和达尔文功能判定结果，评估任务是否达成
- **执行效率判定**：通过实际动作坐标、控件语义和 Plan 进展检测重复操作和无效操作

## 达尔文判定集成

`FuncOracleCheck/` 是当前项目集成的达尔文功能判定模块，提供：

- 单步判定：`POST /check_single_funck`
- E2E 序列判定：`POST /check_e2e`，返回整体意图、路径一致性、Plan 覆盖、重复动作和规划失效判定结果
- 队列式功能检查：`/upload_funcheck_task`、`/get_check_result`、`/get_check_batch_result`

模块内部通过 `oracle_service.py` 收敛 API 与 CLI 的公共判定逻辑，避免入口重复维护。

## 文档索引

| 文档 | 内容 |
|------|------|
| [技术方案](./docs/01-技术方案.md) | 核心技术设计：四层架构、差分偏差三分类、检查点体系 |
| [论文调研](./docs/02-论文调研.md) | 相关学术论文汇总：VeriGUI、TrajAD、GUI-SHEPHERD、V-Droid 等 |
| [相关资源](./docs/03-相关资源.md) | GitHub 项目、数据集、工具链、团队追踪 |
| [架构设计](./docs/04-架构设计.md) | 整体架构图、数据流、模块交互 |

## 项目结构

```text
gui-agent-evaluation/
├── README.md
├── docs/
│   ├── 01-技术方案.md
│   ├── 02-论文调研.md
│   ├── 03-相关资源.md
│   └── 04-架构设计.md
└── FuncOracleCheck/
    ├── main.py                    # FastAPI 服务入口
    ├── oracle_service.py          # 达尔文判定统一封装
    ├── framework.py               # 单样本 CLI 调试
    ├── framework_batch_eval.py    # 批量 benchmark
    ├── requirements.txt           # 统一依赖清单
    ├── app/                       # API 数据模型
    ├── oracle/                    # 功能 oracle 核心逻辑
    ├── GUI_TestFramework_v1/      # MLLM/VLM 判定框架
    ├── external_apis/             # 外部服务适配
    ├── utils/                     # 通用工具
    └── conf/                      # 运行配置
```
