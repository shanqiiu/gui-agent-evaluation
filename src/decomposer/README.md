# Decomposer：LLM + RAG 检查点生成

该模块根据自然语言任务生成结构化 checkpoint。预处理管线会将结果写入 `payload.json` 的 `_checkpoints` 和 `step_level_instruction`。

## 当前定位

Decomposer 不是 verifier。它只提出“预期应该验证什么”。实际是否达成由后续模块判断：

1. `match_checkpoint_intents`
2. `align_checkpoints_to_steps`
3. `CheckpointVerifier`

## 环境变量

```env
LLM_MODEL_URL=http://host/v1/chat/completions
LLM_MODEL_NAME=qwen3-8b
LLM_API_KEY=...
```

如果 baseline 阶段没有配置 `LLM_*`，`src.evaluator.repeated_baseline` 可以回退复用 `VLM_*` 做意图重排。但 decomposer 自身在启用分解时仍需要 LLM 配置。

## 知识库摄入

```bash
python src/decomposer/knowledge_store.py --ingest src/decomposer/app_knowledge/
```

## 程序化调用

```python
from src.decomposer import Decomposer

d = Decomposer(
    model_url="http://host/v1/chat/completions",
    model_name="qwen3-8b",
    api_key="",
)

checkpoints = d.decompose(
    instruction="打开目标设置页面",
    app_name="settings",
    top_k=5,
)
```

期望 checkpoint 结构：

```json
{
  "name": "打开目标页面",
  "required": true,
  "preconditions": "首页可见",
  "expected_state": "目标页面标题和核心控件可见"
}
```

## 预处理集成

使用：

```bash
python -m src.preprocessor.pipeline <task_dir> --output <out_dir>
python -m src.preprocessor.pipeline --batch <raw_base_dir> --output <out_dir>
```

分解成功时：

- `_checkpoints` 保存结构化 checkpoint。
- `step_level_instruction` 保存可读的 `name->name` 序列。
- `_decomposer` 记录 attempted/status/model/config 等元数据。

## RAG 说明

- RAG 知识用于提升 checkpoint 质量，但不是达成证据。
- RAG 未命中时，如果 LLM 已配置，应允许纯 LLM 分解。
- 空 checkpoint 列表是无效输出，应重试。
