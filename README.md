# GUI Agent 执行轨迹评估

本项目用于评估 GUI Agent 的真实执行轨迹。当前默认链路是独立新基线，不再依赖 `src/oracle`；旧 Darwin 服务仅作为 legacy 参考保留。

## 当前主流程

```text
原始任务数据
  -> src.preprocessor.pipeline
  -> payload.json + 截图 + dedup/stategraph 产物
  -> src.evaluator.repeated_baseline
  -> ab_report
  -> state_sequence
  -> intent_matches
  -> checkpoint_alignments
  -> verification_report
  -> repeated_prediction
  -> baseline_result
```

核心设计是两阶段检查点判定：

1. 意图召回：用 `_checkpoints` 匹配实际 `agent_purpose`、动作文本、页面描述和聚合状态证据。
2. 执行验证：只对召回命中的候选步骤/状态使用真实截图和 VLM 验证。

如果意图召回失败，检查点会标记为 `unmatched_intent`，不会随机绑定到某个截图步骤。

## 快速开始

### 单任务预处理

```bash
python -m src.preprocessor.pipeline D:\path\to\raw_task_dir --output D:\path\to\preprocess_out
```

### 批量预处理

```bash
python -m src.preprocessor.pipeline --batch D:\path\to\raw_task_base_dir --output D:\path\to\preprocess_out
```

### 单任务运行基线

```bash
python -m src.evaluator.repeated_baseline D:\path\to\preprocess_out\task_uuid\payload.json --output-dir D:\path\to\baseline_out
```

### 批量运行基线

```bash
python -m src.evaluator.repeated_baseline --batch D:\path\to\preprocess_out --output-dir D:\path\to\baseline_out
```

`start.sh` 封装了同样流程：

```bash
MODE=single bash start.sh
MODE=batch bash start.sh
```

### Web 界面运行（推荐）

启动 Web 服务器，通过浏览器完成预处理和评估：

```bash
# 安装依赖
pip install fastapi python-multipart

# 启动服务器
python -m src.server.server
# 浏览器打开 http://localhost:8025
```

面板支持实时日志流式输出、运行参数配置、结果可视化。也提供独立静态面板（无需服务器）：

```bash
# 浏览器直接打开即可加载 batch_result.json
start src/evaluator/dashboard.html
```

## 环境配置

`src.evaluator.repeated_baseline` 会自动加载仓库根目录 `.env`。

```env
VLM_MODEL_URL=http://host/v1/chat/completions
VLM_MODEL_NAME=qwen3-vl-8b
VLM_API_KEY=...

LLM_MODEL_URL=http://host/v1/chat/completions
LLM_MODEL_NAME=qwen3-8b
LLM_API_KEY=...

TASK_GRAPH_ENABLED=0
```

规则：

- `VLM_*` 用于 AB 判定和检查点截图验证。
- `LLM_*` 用于 decomposer 和可选的意图重排。
- `TASK_GRAPH_ENABLED=1` 时，预处理阶段会生成 TaskGraph，并同步输出兼容 `_checkpoints`。
- 如果 `LLM_*` 未配置，基线会回退复用 `VLM_*` 做意图重排。
- 不要提交 `.env`。

## 预处理输出

每个任务目录输出：

```text
output/<task_uuid>/
- payload.json
- _deduped.json
- _stategraph.json
- catchDataTurnId*.jpg
- ...
```

`payload.json` 关键字段：

| 字段 | 含义 |
|---|---|
| `instruction` | 用户任务 |
| `step_level_instruction` | 可读检查点序列 |
| `_checkpoints` | 结构化检查点列表 |
| `_task_graph` | TaskGraph v1 结构；开启 `TASK_GRAPH_ENABLED=1` 时写出 |
| `_task_graph_schema_version` | `_task_graph` 的 schema 版本，当前为 `task_graph.v1` |
| `agent_purposes` / `_action_purposes` | Agent 每步自述意图 |
| `_ocr_pages` / `_ocr_page_index` | rawPage/OCR 证据 |
| `seq_info` | 实际动作和截图序列 |
| `_image_base_dir` | 截图路径解析基准目录 |

当 `TASK_GRAPH_ENABLED=1` 且图生成失败时，预处理链会回退到旧 checkpoint 拆解，并将其迁移为兼容 TaskGraph 写入 `_task_graph`。这保证旧 verifier 仍消费 `_checkpoints`，新链可读取图结构。

## 基线输出

| 文件 | 含义 |
|---|---|
| `ab_report.json` | AB 页面/动作验证结果 |
| `intent_matches.json` | 检查点意图召回候选 |
| `checkpoint_alignments.json` | 候选到执行步骤的对齐结果 |
| `verification_report.json` | 检查点截图/VLM 达成报告 |
| `state_sequence.json` | 状态、OCR 和视觉证据 |
| `repeated_prediction.json` | 重复操作基线结果 |
| `planning_failure_result.json` | 规划失效聚合结果 |
| `anomaly_events.json` | 统一异常事件（7 类 taxonomy） |
| `baseline_result.json` | 全量汇总结果 |

批跑额外输出：

| 文件 | 含义 |
|---|---|
| `batch_result.json` | 批跑汇总（total/ok/error + 每任务 label/anomaly_count） |

### 异常事件（7 类 taxonomy）

`anomaly_events.json` 输出统一事件列表，覆盖 7 类顶层异常：

| Category | 检测来源 |
|---|---|
| `loop` | repeated detector → `state_action_loop` |
| `repeated_action` | repeated detector → consecutive/wait/swipe repeats |
| `grounding_error` | AB 验证 + 视觉/OCR 证据（`wrong_tap_target`, `wrong_input_location`, `wrong_scroll_direction`） |
| `planning_failure` | planning failure aggregator（`missing_required_checkpoint`, `execution_blocked`, `fail_to_terminate`） |
| `hallucination` | agent 意图 vs OCR/页面描述（`non_existent_element`, `wrong_page_understanding`, `fabricated_capability`） |
| `abnormal_interruption_response` | clarify 事件 + state 关键词扫描（captcha/login/permission/crash/network） |
| `premature_termination` | planning failure → 提升为顶层事件 |

## Benchmark 对比

离线 benchmark 只读取已有产物，不触发 LLM/VLM 调用：

```bash
python -m src.evaluator.benchmark D:\path\to\benchmark_samples --output D:\path\to\benchmark_result.json --feature-flag TASK_GRAPH_ENABLED=1
```

每个样本目录可包含 `task_annotation.json`、`payload.json`、`baseline_result.json`、`planning_evaluation.json` 和 `legacy_result.json`。报告会输出样本数、解析失败数、schema 不兼容数、v1/v2 差异和模型调用统计。

## 模块状态

| 模块 | 定位 |
|---|---|
| `src/preprocessor` | 当前数据预处理入口 |
| `src/decomposer` | LLM + RAG 检查点 / TaskGraph 生成 |
| `src/common` | 图片水合、ABValidator、重复检测器 |
| `src/evaluator` | 当前基线编排入口、异常检测（grounding / hallucination / planning_failure）、状态/视觉证据聚合 |
| `src/verifier` | 意图召回、检查点对齐、VLM 验证 |
| `src/server` | **Web 服务器** — FastAPI + SSE 实时日志、面板触发预处理和评估 |
| `src/oracle` | legacy Darwin 服务，不是默认基线路径 |
| `src/state_extractor` | legacy/prototype 状态提取器；新基线使用 `src/evaluator/state_evidence.py` |
| `src/evaluator/dashboard.html` | 独立静态批跑结果可视化面板（无需服务器） |

## 测试

主要回归命令（排除依赖 chromadb 的 decomposer 测试）：

```bash
python -m pytest src\verifier src\evaluator src\common\test_common.py src\efficiency src\trajectory --ignore=src\evaluator\test_benchmark.py -q
```

## 文档索引

| 文档 | 用途 |
|---|---|
| `docs/01-技术方案.md` | 当前唯一规范性技术方案 |
| `docs/04-当前进展与开发计划.md` | 当前唯一可执行 TODO 清单 |
| `docs/05-GUI_Agent执行评估总体方案.md` | 方案介绍与评审用总览 |
| `docs/06-GUI_Agent任务分解与规划评估优化技术方案.md` | TaskGraph 优化设计 |
| `docs/06-当前项目进展分析.md` | 当前工程进展与成熟度分析 |
| `docs/07-人工标注契约与TaskGraph-Schema.md` | TaskGraph 与远程人工标注数据契约 |
| `docs/重复动作异常判定技术方案.md` | 重复操作专题方案 |
| `docs/规划失效异常判定技术方案.md` | 规划失效专题方案 |
| `docs/GUI_Agent_异常Case_技术洞察.md` | 异常 taxonomy 和研究洞察 |
| `docs/02-论文调研.md` | 研究背景，不作为实现规范 |
| `docs/03-相关资源.md` | 资源索引，不作为实现规范 |
| `DESIGN.md` | Web 界面的 Supabaze 设计系统规范 |
