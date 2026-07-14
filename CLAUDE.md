# GUI Agent 执行轨迹自动判定系统

## 项目简介

自动化评估系统，针对多模态 GUI Agent（如手机操作助手）的任务执行进行合理性、正确性、效率三维度自动判定。通过 VLM 截图语义对齐、LLM+RAG 检查点分解、操作意图向量化等技术，实现对 Agent 执行轨迹的系统化评估。

## 项目状态

**当前处于活跃开发阶段**。判定服务管线（Darwin VLM + 数据转换）已完整跑通，模块 A（RAG 任务分解引擎）已完成并集成到数据管线中。模块 B/C/D/E 尚未启动。

- 核心判定能力通过集成达尔文实验室的 `src/oracle/` 实现
- 数据管线（utg.json → payload → 判定）完整，含 10 项核心逻辑测试
- `src/decomposer/` 模块 A 已完成（LLM + ChromaDB RAG）

## 目录结构

```
gui-agent-evaluation/
├── README.md                     # 项目概览与文档索引
├── CLAUDE.md                     # Sisyphus 项目指令
├── docs/                         # 设计文档
│   ├── 01-技术方案.md             # 核心技术设计：四层架构、差分偏差三分类、检查点体系
│   ├── 02-论文调研.md             # 相关学术论文：VeriGUI、TrajAD、GUI-SHEPHERD 等
│   ├── 03-相关资源.md             # GitHub 项目、数据集、工具链
│   ├── 04-架构设计.md             # 系统架构图、数据流、模块交互
│   ├── 重复动作异常判定技术方案.md  # 动作等效/目标等效/无进展三条件模型
│   ├── 规划失效异常判定技术方案.md  # 五类规划失效 + 首错归因
│   └── 进展汇总.md                # 工作进展与当前状态
├── src/                          # 源码模块
│   ├── preprocessor/            # ✅ 数据预处理管线
│   │   ├── pipeline.py           # 编排入口
│   │   ├── preprocessor.py       # 统一解析器
│   │   ├── write_payload.py      # → payload.json
│   │   ├── write_dedup.py        # → _deduped.json
│   │   ├── write_stategraph.py   # → _stategraph.json
│   │   └── ...
│   ├── oracle/                  # ✅ 达尔文判定服务 (ex FuncOracleCheck)
│   ├── decomposer/              # ✅ 模块A: 任务分解引擎
│   ├── state_extractor/         # ✅ 轨迹状态提取
│   ├── verifier/                # ❌ 模块B: 检查点验证器（待实现）
│   ├── efficiency/              # ❌ 模块C: 效率分析器（待实现）
│   ├── trajectory/              # ❌ 模块D: 轨迹差分判定器（待实现）
│   ├── evaluator/               # ❌ 模块E: 综合评估器（待实现）
│   └── common/                  # ❌ 公共工具（待实现）
├── data/                        # 数据文件
│   └── data.md                   # utg.json 数据格式说明
│   ├── convert_to_check_e2e.py   # utg.json → payload 转换器
│   ├── send_payload.py           # 已保存 payload 重发工具
│   └── test_convert_to_check_e2e.py  # 10 项核心逻辑测试
├── scripts/                      # 命令行脚本（待创建）
├── configs/                      # 配置文件（待创建）
└── outputs/                      # 评估报告输出（待创建）
```

## 技术栈（规划）

- **Python**: 3.10+
- **VLM**: Qwen3.5-VL-7B（截图语义对齐）
- **LLM**: Qwen3-8B / GPT-4o（任务分解、Judge）
- **Embedding**: text-embedding-3-large / BGE-M3（操作意图向量化）
- **RAG**: ChromaDB / LanceDB（App 私有知识）
- **推理框架**: vLLM / SGLang
- **包管理**: uv

## 常用命令

```bash
# 依赖安装
uv sync

# 运行测试
pytest tests/ -v --tb=short

# 代码检查与格式化
ruff check src/ scripts/
ruff format src/ scripts/

# 类型检查
pyright src/
```

## 开发规范

- **类型注解**: 所有公开函数必须添加类型注解
- **代码风格**: PEP 8，使用 Ruff 检查
- **文档字符串**: Google 风格 docstring
- **测试**: 新增功能须附带 Pytest 用例，目标覆盖率 80%+
- **提交信息**: `[类型] 简要描述`，类型包括 `feat`, `fix`, `refactor`, `test`, `docs`

## 核心架构

### 四层架构
1. **L1 任务输入 & 知识支撑** — 自然语言指令 + RAG 知识库
2. **L2 任务子状态 & 约束分解** — 目标/属性/操作/状态流转约束
3. **L3 关键检查点判定** — 阶段级检查 + 单步级检查 + 效率判定
4. **L4 综合评估** — 加权聚合输出结构化报告

### 五大功能模块
- **模块A 任务分解引擎**: 自然语言 → LLM+RAG → 结构化检查点列表
- **模块B 检查点验证器**: 截图对 + 检查点描述 → VLM → 达成/未达成/不确定
- **模块C 效率分析器**: 操作序列 → 向量化 → 重复/无效/循环检测
- **模块D 轨迹差分判定器**: 完整轨迹 → 三分类（无影响/补救性/级联偏差）
- **模块E 综合评估器**: 聚合 B/C/D → 加权总分 + 结构化报告

### 差分偏差三分类
| 类型 | 定义 | 处理 |
|------|------|------|
| 无影响偏差 | 不同路径但结果一致 | 不扣分 |
| 补救性偏差 | 早期次优但后续纠正 | 降分但接受 |
| 级联偏差 | 小错误被持续放大 | 判定失败，标记首错步骤 |

## 环境配置

创建 `.env` 文件（已包含在 `.gitignore` 中）：

```env
# Decomposer — LLM+RAG 任务分解
LLM_MODEL_URL=http://localhost:8000/v1/chat/completions
LLM_MODEL_NAME=qwen3-8b
LLM_API_KEY=                        # 可选
```

Darwin 判定服务的模型配置在 `src/oracle/conf/run_benchmark_config.conf`，API Key 通过 `MLOPS_API_KEY` 环境变量传入。
