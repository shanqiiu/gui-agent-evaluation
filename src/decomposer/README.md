# Decomposer：LLM + RAG 检查点生成

该模块根据自然语言任务生成结构化 checkpoint。预处理管线会将结果写入 `payload.json` 的 `_checkpoints` 和 `step_level_instruction`。

一个 checkpoint 表示任务推进过程中不可缺少、路径无关且可以通过截图、OCR 或页面结构验证的关键子状态。它不表示某一次点击、输入或滑动操作。

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

`src/decomposer/app_knowledge/*.md` 是 App 任务拆解知识源。新增或修改 Markdown 后，需要重新执行摄入命令，已经持久化的 ChromaDB 不会自动更新。

当前包含的专用建模：

- `settings.md`：设置类页面流和关键控件。
- `taobao.md`：淘宝“再来一单/历史订单复购”任务，优先建模为历史订单入口、订单列表、目标订单定位、复购动作触发、订单确认页就绪，而不是普通商品搜索购买路径。

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
    app_name=None,
    top_k=5,
)
```

期望 checkpoint 结构：

```json
{
  "name": "目标页面已打开",
  "required": true,
  "preconditions": "首页可见",
  "expected_state": "目标页面标题和核心控件可见"
}
```

生成器会检查纯操作名称、复合阶段、缺失 `expected_state`、重复状态和数量超限。发现问题时自动调用一次 LLM 修正；修正后仍存在的问题写入 `_decomposer.quality_issues`。

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
- `_decomposer.quality_status` 记录粒度校验结果。
- `_decomposer.refinement_attempted` 表示是否执行过自动修正。

## RAG 说明

- RAG 知识用于提升 checkpoint 质量，但不是达成证据。
- RAG 未命中时，如果 LLM 已配置，应允许纯 LLM 分解。
- 空 checkpoint 列表是无效输出，应重试。
- 默认不限定 App；可通过 `RAG_APP_NAME` 指定知识库中的 App metadata。
