# GUI Agent 人工标注契约与 TaskGraph Schema

版本：v1.0
更新日期：2026-07-20
状态：P0-A 实现契约

## 1. 目标与边界

本契约定义远程 GUI Agent 原始轨迹如何映射为 TaskGraph 和人工标注数据。真实轨迹因保密要求保留在远程服务器，本地仓库只保存：

- schema 实现；
- 字段说明；
- 不包含真实业务信息的合成测试数据；
- 对远程证据的不透明引用。

TaskGraph 模块不读取 `utg.json`、`clearRes.gzip`、截图、UI 树或服务器目录。原始数据解析仍由 `src/preprocessor` 负责，schema 模块只消费结构化标注对象。

## 2. 原始数据映射

依据 `data/data.md`，远程任务至少包含用户指令、UTG 节点与边、步骤数据、截图、UI 树、clearRes、actionPurpose 和应用信息。

| 标注字段 | 推荐远程来源 | 映射规则 |
|---|---|---|
| `task_id` | 任务 UUID 目录 | 使用稳定任务标识，不使用本地绝对路径 |
| `instruction` | node title 或 clearRes | 保留原始任务文本，由远程标注工具读取 |
| `app.app_name` | `targetAppName` 或 OpenApp | 使用目标 App 名称 |
| `app.package_name` | `packageName` 或 UI 树 `BundleName` | 缺失时允许空字符串 |
| `app.app_version` | clearRes App 信息 | 缺失时允许空字符串 |
| `source.step_count` | 预处理后的可执行步骤 | 不包含 home、end、播报和纯思考节点 |
| `source.artifact_types` | 远程任务文件清单 | 只记录类型，不复制文件内容 |
| `EvidenceReference.step_index` | `NormalizedStep.step_index` | 使用新链 0-based 动作序号 |
| `EvidenceReference.source_step_id` | UTG `stepId` | 用于回查原始步骤 |
| `artifact_ref` | 远程证据索引 | 使用不透明标识，不使用服务器绝对路径或带凭据 URL |

标注 step span 统一使用预处理后的动作序号。UTG 原始 `stepId` 只作为回查引用，不能与 0-based `step_index` 混用。

## 3. 本地保密约束

以下内容不得进入仓库、测试 fixture、日志或提交记录：

- 真实截图、UI 树、OCR 全文和 phone log；
- 完整 `utg.json`、clearRes、oriRes 或 corpusResult；
- 远程服务器地址、挂载路径、访问令牌和带签名 URL；
- 可识别真实用户、设备或业务数据的任务文本；
- ODID、session ID、账号、订单、联系人等标识信息。

`task_annotation.v1` 默认拒绝未知字段，因此把 `raw_utg`、`screenshots` 等原始内容直接加入标注 JSON 会产生 `unknown_field` 错误。

## 4. TaskGraph 契约

顶层版本固定为 `task_graph.v1`，主要字段为：

| 字段 | 类型 | 含义 |
|---|---|---|
| `goal` | object | 最终目标和可观察成功条件 |
| `constraints` | array | `must`、`must_not` 或 `prefer` 约束 |
| `subtasks` | array | 默认 3-8 个语义 Subtask；仅 `checkpoint_migration` 兼容图允许 1-8 个 |
| `edges` | array | `requires` 或 `recommended` 依赖 |
| `alternative_groups` | array | 多路径任务中满足指定数量即可的候选 Subtask |
| `metadata` | object | 生成来源、模型、RAG 命中和质量状态 |

`metadata.source` 当前约定：

- `llm_rag`：由 Decomposer 直接生成的标准 TaskGraph，必须满足 3-8 个语义 Subtask。
- `checkpoint_migration`：由旧 `_checkpoints` 兼容迁移得到的过渡 TaskGraph，只用于迁移和双轨输出，允许 1-8 个 Subtask，不做填充式扩容。

每个成功条件使用 `VerificationCriterion`：

```json
{
  "criterion_id": "vc_st_001_01",
  "description": "目标状态在页面中可见",
  "evidence_types": ["screenshot", "ocr"],
  "required": true
}
```

允许的证据类型为：

- `screenshot`
- `ocr`
- `ui_tree`
- `action_log`
- `system_state`

## 5. 人工标注契约

顶层版本固定为 `task_annotation.v1`，至少包含：

- 任务与 App 信息；
- 远程轨迹来源引用；
- 人工确认的 TaskGraph；
- 每个 Subtask 的状态和尝试 span；
- 证据引用；
- 首错步骤和类型；
- 是否恢复、恢复区间和恢复结果；
- 标注人、修订版本和备注。

Subtask 状态集合：

```text
achieved | partial | failed | uncertain | not_attempted
```

恢复结果集合：

```text
none | successful | failed | uncertain
```

每个 TaskGraph Subtask 必须有且只有一条 `SubtaskAnnotation`。`achieved`、`partial` 和 `failed` 必须提供至少一个尝试 span；`not_attempted` 不得提供尝试 span。

## 6. 确定性校验

`src/decomposer/schema.py` 当前校验：

- schema version 和未知字段；
- 必填字段和 JSON 类型；
- 默认 3-8 个语义 Subtask；仅 `metadata.source == "checkpoint_migration"` 时放宽到 1-8；
- 操作级名称、复合状态和重复状态；
- 成功条件是否声明可用证据类型；
- ID 唯一性和引用完整性；
- `depends_on` 与 `requires` edge 一致性；
- 未知依赖、自依赖、重复 edge 和 DAG 环；
- alternative group 成员和数量约束；
- 标注 span、step index、证据、首错和恢复引用；
- 每个 Subtask 是否有完整人工标签。

独立 root Subtask 可以表示合法换序或并行前置状态，不应仅因图不连通被判为错误。未知依赖和环才表示依赖关系无法求值。

## 7. 兼容输出与迁移

P0-B 后，预处理链可以在保留旧 payload 兼容性的同时输出 TaskGraph：

- 关闭 `TASK_GRAPH_ENABLED` 时，沿用旧 checkpoint 拆解流程，不生成 `_task_graph`。
- 开启 `TASK_GRAPH_ENABLED=1` 时，优先生成并校验 TaskGraph，再投影出兼容 `_checkpoints`。
- 若生成的 TaskGraph 未通过确定性校验，链路会回退到旧 checkpoint 拆解，并通过迁移函数生成 `metadata.source = "checkpoint_migration"` 的兼容 TaskGraph。
- payload 双轨写出 `_task_graph`、`_task_graph_schema_version`、`_checkpoints` 和原有 `step_level_instruction`，以保证旧 verifier 和新图结构可同时消费。

## 8. 公共 Interface

```python
from src.decomposer import (
    decode_task_annotation,
    decode_task_graph,
    dumps_task_annotation,
    dumps_task_graph,
    loads_task_annotation,
    loads_task_graph,
    validate_task_annotation,
    validate_task_graph,
)
```

- `decode_*`：严格解析 mapping，不合法时抛出 `TaskGraphSchemaError`。
- `loads_*`：严格解析 JSON 文本。
- `validate_*`：返回全部 `ValidationIssue(code, path, message)`。
- `dumps_*`：校验后输出稳定 JSON。
- dataclass 定义位于 `src/decomposer/models.py`。

## 9. 远程开发与标注流程

```text
远程原始任务
  -> 现有 preprocessor 生成 NormalizedTask/payload
  -> 远程标注工具构造 task_annotation.v1
  -> schema 严格校验
  -> 远程保存标注和证据
  -> 本地只接收脱敏指标或经审批的结构化样本
```

本地自动化测试使用 `src/decomposer/test_schema.py` 中的纯合成 fixture，不依赖真实远程数据。
