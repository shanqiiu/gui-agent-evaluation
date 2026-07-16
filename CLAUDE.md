# GUI Agent Evaluation 项目说明

## 当前项目状态

默认评估路径是独立新基线，不是 `src/oracle`。

当前链路：

```text
src.preprocessor.pipeline
  -> payload.json
  -> src.evaluator.repeated_baseline
  -> ab_report
  -> state_sequence
  -> intent_matches
  -> checkpoint_alignments
  -> verification_report
  -> repeated_prediction
  -> baseline_result
```

`src/oracle` 只是 legacy Darwin 参考。除非明确要求兼容旧服务，否则不要把新的基线逻辑写到 `src/oracle` 下。

## 重要模块

| 模块 | 定位 |
|---|---|
| `src/preprocessor` | 原始任务解析和 payload 写入 |
| `src/decomposer` | LLM + RAG 检查点生成 |
| `src/common` | 图片水合、ABValidator、重复检测器 |
| `src/evaluator/repeated_baseline.py` | 主基线编排 |
| `src/evaluator/state_evidence.py` | 聚合状态和视觉/OCR 证据 |
| `src/verifier/alignment.py` | 意图召回和 checkpoint-step 对齐 |
| `src/verifier/verifier.py` | 截图/VLM 检查点验证 |
| `src/oracle` | legacy Darwin 服务 |

## 设计约束

- 通用模块不得写 App 或业务场景硬编码。
- 不要硬编码电商、搜索、筛选、商品、价格等固定意图。
- 不要把 checkpoint 均匀分配到步骤。
- VLM 调用必须使用真实截图 Base64，不要把文件路径当图片内容。
- `agent_purpose` 是意图信号，不是真值。
- 检查点判定分两阶段：先意图召回，再执行验证。
- 缺证据应输出 `uncertain` 或 `unmatched_intent`，不能静默判成功。
- `.env` 不要提交。

## 常用命令

单任务预处理：

```bash
python -m src.preprocessor.pipeline <task_uuid_dir> --output <preprocess_out>
```

批量预处理：

```bash
python -m src.preprocessor.pipeline --batch <raw_base_dir> --output <preprocess_out>
```

单任务运行基线：

```bash
python -m src.evaluator.repeated_baseline <payload.json> --output-dir <baseline_out>
```

批量运行基线：

```bash
python -m src.evaluator.repeated_baseline --batch <preprocess_out> --output-dir <baseline_out>
```

回归测试：

```bash
python -m pytest src\verifier src\evaluator src\common\test_common.py
```

## 环境变量

`src.evaluator.repeated_baseline` 会自动加载 `.env`。

```env
VLM_MODEL_URL=http://host/v1/chat/completions
VLM_MODEL_NAME=qwen3-vl-8b
VLM_API_KEY=...

LLM_MODEL_URL=http://host/v1/chat/completions
LLM_MODEL_NAME=qwen3-8b
LLM_API_KEY=...
```

如果没有配置 `LLM_*`，基线会回退复用 `VLM_*` 做意图重排。

## 文档

`docs/01-技术方案.md` 是当前唯一规范性文档。`docs/` 下专题文档已与当前基线同步；论文、资源和异常洞察文档只作为背景材料。
