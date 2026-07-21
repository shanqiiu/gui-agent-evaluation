# GUI Agent 任务分解与规划评估优化技术方案

版本：v1.1  
更新日期：2026-07-20  
状态：优化设计方案，已补充 CES、PEEU、InfiGUI-R1 适用性评估，尚未实施  
适用范围：`gui-agent-evaluation` 新评估主链，不包含 legacy `src/oracle`

## 1. 文档目标

本文基于当前项目实现、知识库中的 GUI Agent 异常研究，以及 2025-2026 年层级规划、意图记忆、世界模型和回滚恢复相关工作，给出 `gui-agent-evaluation` 的下一阶段优化方案。

本项目的目标不是实现一个负责点击和输入的 GUI Agent，而是评估外部 GUI Agent 的真实执行轨迹。因此，先进 GUI Agent 推理架构在本项目中的对应关系是：

| GUI Agent 能力 | 本项目中的评估建模 |
|---|---|
| 自然语言目标理解 | 从 `instruction` 提取目标、约束和完成标准 |
| 层级任务分解 | 生成 Goal -> Subtask -> Observable State 任务图 |
| Planner / Actor 解耦 | 分离预期任务模型、实际意图轨迹和实际状态证据 |
| 子任务验证 | 使用 intent recall + screenshot/OCR/VLM 验证子目标是否达成 |
| 动态重规划 | 从实际轨迹中识别计划变更、补救路径和错误分支 |
| 回滚与恢复 | 评估偏差发生后是否回到可继续完成任务的稳定状态 |

优化目标是将当前“扁平 checkpoint 覆盖率评估”升级为：

> 基于结构化任务图、真实状态证据和恢复轨迹的层级规划评估。

## 2. 当前基础与核心缺口

### 2.1 已具备的工程基础

当前新主链已经具备：

```text
instruction
  -> LLM + RAG checkpoints
  -> agent purpose intent recall
  -> checkpoint-step alignment
  -> screenshot/OCR/VLM verification
  -> state sequence
  -> repeated action detection
  -> planning failure aggregation
```

对应模块为：

| 模块 | 当前职责 |
|---|---|
| `src/decomposer` | 自然语言生成路径无关的可观察 checkpoint |
| `src/preprocessor` | 生成 `payload.json`、动作序列和截图引用 |
| `src/verifier/alignment.py` | checkpoint 与实际意图、步骤和状态对齐 |
| `src/verifier/verifier.py` | 使用真实截图验证 checkpoint |
| `src/evaluator/state_evidence.py` | 聚合状态变化证据 |
| `src/evaluator/planning_failure.py` | 聚合缺失、执行阻塞和终止异常 |

当前“先意图召回、后执行验证”的设计是正确的，应继续保留。

### 2.2 当前扁平 checkpoint 的限制

现有 `_checkpoints` 只有：

```json
{
  "name": "目标页面已打开",
  "required": true,
  "preconditions": "入口可见",
  "expected_state": "页面标题和核心控件可见",
  "checkpoint_id": "cp_001"
}
```

该结构不能稳定表达：

1. checkpoint 之间的显式依赖关系。
2. 可交换顺序和并行分支。
3. 用户约束、禁止状态和不可逆操作。
4. 子任务的局部成功与整体目标成功之间的关系。
5. Agent 是否进行了合理重规划。
6. 失败后是成功补救、无效探索还是错误级联。

当前 alignment 使用基本单调顺序约束，适合线性任务，但会误伤存在合法分支、返回修改或并行填写的任务。

### 2.3 当前规划失效归因不足

当前规划失效主要依据 required checkpoint 是否召回、是否达成以及是否正确终止。主要缺口包括：

- 无法区分“从未计划”“计划正确但执行失败”“走错分支后恢复失败”。
- 尚未真正使用 `state_sequence` 判断错误状态和回滚状态。
- 无法检查依赖违反和阶段顺序错误。
- 缺少任务级、子任务级、动作级三层进展视图。
- 无法将首错步骤与后续错误级联关联起来。

## 3. 技术结论与设计原则

### 3.1 推荐的总体方案

当前最适合本项目的技术路线是：

```text
自然语言指令
  -> IntentSpec：目标、约束、全局完成标准
  -> TaskGraph：层级子任务、依赖、局部成功标准
  -> Checkpoint Projection：兼容当前链路的扁平检查点
  -> Intent Alignment：实际 Agent 是否尝试对应子任务
  -> State Verification：子任务是否被真实界面证据证明完成
  -> Graph-aware Evaluation：依赖、顺序、分支和终止评估
  -> Recovery Evaluation：偏差、补救、回滚和错误级联评估
```

### 3.2 设计原则

1. **高层结构化，低层路径无关**：预先定义语义子目标，不预先生成坐标和完整点击序列。
2. **计划与执行证据解耦**：LLM 生成的是待验证假设，不能作为达成证据。
3. **任务图是主模型，checkpoint 是兼容投影**：逐步迁移，避免一次性重写主链。
4. **完成标准必须可观察**：优先截图、OCR、页面结构和状态变化证据。
5. **不确定性显式传播**：缺图、意图不清、VLM 低置信时输出 `uncertain`。
6. **先评估是否尝试，再评估是否完成**：继续保留 intent recall + execution verification 两阶段设计。
7. **首错归因优先于结果归因**：最终失败不应覆盖最早的规划或执行偏差。
8. **合法多路径不扣分**：不把与参考路径不同但满足依赖和后置条件的轨迹判为异常。

### 3.3 暂不推荐的方案

- 暂不全面引入传统 PDDL domain/operator 编写，维护成本和 App 适配成本过高。
- 不要求 LLM 生成完整低层动作计划，GUI 环境变化会使计划快速失效。
- 不直接引入 MCTS 作为默认评估算法；只有存在可靠 App 状态图时才有收益。
- 不使用 `agent_purpose` 作为真值，它只能作为意图召回信号。
- 不用单个 VLM 同时承担任务分解、步骤对齐、状态验证和最终裁决。

### 3.4 CES、PEEU 与 InfiGUI-R1 的适用性评估

外部意见将当前模块 A 类比为简化版 Coordinator，并建议依次引入 InfiGUI-R1 层级推理、PEEU hindsight experience 和 CES execution-feedback RL。该判断方向基本正确，但需要区分“在线执行 Agent”和“离线轨迹评估器”的系统边界。

| 研究方案 | 原始定位 | 对本项目的可迁移部分 | 当前优先级 |
|---|---|---|---|
| InfiGUI-R1 | 训练具备显式子目标规划和错误恢复能力的 GUI Actor/Reasoner | Goal -> Subtask -> Checkpoint 层级表示、错误恢复场景构造 | P0，高 |
| PEEU | 从自主探索轨迹反向合成严格对齐的高层规划训练数据 | 从人工确认的分解错误和成功轨迹构建离线 Experience Bank | P1，高 |
| CES | Coordinator、Executor、State Tracker 在线协作，并使用执行反馈 RL 训练高层调度模型 | Planner/trajectory/progress tracker 解耦、任务状态持续维护 | P1 概念迁移；RL 为 P3 |

需要修正的关键点：

1. 当前 `src/decomposer` 只在任务开始前生成预期任务模型，不是 CES 中执行期间持续重规划的在线 Coordinator。
2. InfiGUI-R1 的两层推理不能只靠提示词落地；如果下游仍只消费扁平列表，就无法评估依赖、分支、换序和恢复。
3. PEEU 的原始方法是根据探索轨迹进行 hindsight task relabeling 和训练数据合成，不是把所有失败结果直接写入 RAG。
4. 当前 VLM/verifier 尚未完成人工校准，不能直接作为 RL 唯一奖励，否则会将评估器偏差反向训练进 Decomposer。

因此，本项目应采用以下迁移方式：

```text
InfiGUI-R1
  -> 层级 TaskGraph + recovery scenario 标注

PEEU
  -> 人工确认后的 decomposition experience 数据飞轮

CES
  -> TaskGraph Decomposer + 外部 Agent 轨迹 + 离线 TaskProgressTracker
  -> 在线 execution-feedback RL 暂缓
```

## 4. 目标数据模型

### 4.1 TaskGraph 顶层结构

建议在 `payload.json` 新增 `_task_graph`，同时保留 `_checkpoints`：

```json
{
  "schema_version": "task_graph.v1",
  "goal": {
    "description": "打开目标设置并启用指定功能",
    "success_criteria": [
      "目标设置项显示为已启用"
    ]
  },
  "constraints": [
    {
      "constraint_id": "constraint_001",
      "type": "must_not",
      "description": "不得修改其他设置项",
      "observable_condition": "其他相关设置保持原值"
    }
  ],
  "subtasks": [],
  "edges": [],
  "metadata": {
    "source": "llm_rag",
    "model": "",
    "rag_hits": [],
    "quality_status": "ok"
  }
}
```

### 4.2 Subtask 结构

```json
{
  "subtask_id": "st_002",
  "name": "目标设置页面已打开",
  "description": "进入包含目标设置项的页面",
  "required": true,
  "depends_on": ["st_001"],
  "preconditions": [
    "设置应用可用"
  ],
  "success_criteria": [
    "页面标题与目标设置分类一致",
    "目标设置项名称可见"
  ],
  "forbidden_states": [
    "进入无关设置分类"
  ],
  "risk_level": "low",
  "reversible": true,
  "allowed_reorder": false,
  "optional_group": "",
  "checkpoint_ids": ["cp_002"]
}
```

字段说明：

| 字段 | 用途 |
|---|---|
| `subtask_id` | 稳定标识，避免依赖数组位置 |
| `depends_on` | 构造 DAG，支持依赖和顺序检查 |
| `success_criteria` | 一个子任务可包含多个可观察完成条件 |
| `forbidden_states` | 识别目标偏离、错误页面和安全约束违反 |
| `risk_level` | 标记提交、删除、支付等高风险操作 |
| `reversible` | 用于分析失败后是否可以回滚 |
| `allowed_reorder` | 允许表单字段等任务以不同顺序完成 |
| `optional_group` | 表达可选分支或多选一路径 |
| `checkpoint_ids` | 连接现有 verifier 模型 |

### 4.3 Edge 结构

```json
{
  "from": "st_001",
  "to": "st_002",
  "type": "requires",
  "condition": "目标入口已经出现"
}
```

`type` 第一版只需要支持：

- `requires`：必须先完成前置子任务。
- `recommended`：推荐顺序，违反不直接判失败。
- `alternative`：可选分支，任一分支达成即可。

### 4.4 Checkpoint 向后兼容扩展

建议扩展 `src/verifier/models.py::Checkpoint`，新增字段均提供默认值：

```python
subtask_id: str = ""
depends_on: list[str] = field(default_factory=list)
success_criteria: list[str] = field(default_factory=list)
forbidden_states: list[str] = field(default_factory=list)
risk_level: str = "low"
reversible: bool = True
allowed_reorder: bool = False
```

兼容规则：

- 旧数据只有 `expected_state` 时，映射为单项 `success_criteria`。
- 新数据仍生成 `expected_state`，内容为 `success_criteria` 的可读合并文本。
- `_checkpoints` 继续供当前 alignment/verifier 使用。
- `_task_graph` 供新的 graph-aware evaluator 使用。

## 5. 目标评估架构

```text
                         +-----------------------+
instruction + App RAG -> | Hierarchical Decomposer|
                         +-----------+-----------+
                                     |
                          IntentSpec + TaskGraph
                                     |
                         +-----------v-----------+
                         | Schema/Quality Validator|
                         +-----------+-----------+
                                     |
                  +------------------+------------------+
                  |                                     |
          checkpoint projection                 graph constraints
                  |                                     |
       +----------v----------+               +----------v----------+
       | Intent/Step Alignment|               | Dependency Evaluator|
       +----------+----------+               +----------+----------+
                  |                                     |
       +----------v----------+               +----------v----------+
       | Screenshot Verifier |               | Branch/Order Analysis|
       +----------+----------+               +----------+----------+
                  |                                     |
                  +------------------+------------------+
                                     |
                         +-----------v-----------+
                         | Recovery/First-error   |
                         | Evaluation             |
                         +-----------+-----------+
                                     |
                         planning_evaluation.json
```

## 6. 模块级改造方案

### 6.1 `src/decomposer`

新增层级分解接口，保留现有 `decompose()`：

```python
task_graph = decomposer.decompose_graph(
    instruction=instruction,
    app_name=app_name,
    top_k=top_k,
)
checkpoints = project_checkpoints(task_graph)
```

建议职责拆分：

| 文件 | 新职责 |
|---|---|
| `decomposer.py` | LLM 调用和整体编排 |
| `models.py` | `IntentSpec`、`TaskGraph`、`Subtask` 数据模型 |
| `schema.py` | 结构校验和版本迁移 |
| `quality.py` | 图质量检查、重复状态和不可验证状态检测 |
| `projection.py` | TaskGraph 到 Checkpoint 的兼容投影 |

分解提示词应先要求模型识别：

1. 用户最终目标。
2. 显式与隐式约束。
3. 3-8 个语义子任务。
4. 每个子任务的可观察成功条件。
5. 子任务依赖和可交换关系。
6. 高风险或不可逆阶段。

不要要求模型输出具体点击方式。

### 6.2 `src/preprocessor`

`NormalizedTask` 增加：

```python
task_graph: dict[str, Any] = field(default_factory=dict)
```

`write_payload.py` 增加：

```json
{
  "_task_graph": {},
  "_checkpoints": [],
  "_task_graph_schema_version": "task_graph.v1"
}
```

`step_level_instruction` 继续输出线性可读摘要，但不得作为图结构的唯一存储形式。对于分支任务，可使用主路径摘要并在 `_task_graph` 保存完整关系。

### 6.3 `src/verifier/alignment.py`

当前全局单调匹配应升级为依赖感知匹配：

1. 先按 task graph 拓扑层级分组。
2. 同一依赖层的 `allowed_reorder=true` 子任务允许任意顺序。
3. 只有 `requires` 边参与硬顺序限制。
4. `alternative` 分支一旦有一条被高置信达成，其余分支不计缺失。
5. 每个 subtask 可召回连续 purpose span 和多个候选状态。
6. 对返回修改场景，允许同一 subtask 出现多次尝试，保留首次尝试、最终成功和尝试次数。

建议新增：

```python
SubtaskAlignment(
    subtask_id="st_002",
    attempted=True,
    attempt_spans=[[3, 5], [9, 10]],
    final_span=[9, 10],
    dependency_status="satisfied",
    confidence=0.84,
)
```

### 6.4 `src/verifier/verifier.py`

从“一个 checkpoint 一次判断”扩展为“一个 subtask 多证据聚合”：

- 一个 success criterion 对应一个证据判断。
- 子任务 required criteria 全部达成才判定 `achieved`。
- 部分达成输出 `partial`，不要直接归为 `not_achieved`。
- forbidden state 命中时单独输出，不与普通失败混合。
- 相同截图和相近 criterion 共享 VLM 调用结果，减少成本。

建议状态集合：

```text
achieved | partial | not_achieved | forbidden | uncertain | not_attempted
```

### 6.5 `src/evaluator/planning_failure.py`

将当前 checkpoint 完成率聚合升级为任务图评估。建议新增子类型：

| 子类型 | 定义 |
|---|---|
| `goal_misunderstanding` | 实际意图长期不指向用户最终目标 |
| `missing_required_subtask` | required subtask 从未被尝试 |
| `dependency_violation` | 未满足前置状态就进入后继子任务 |
| `wrong_branch` | 进入与目标无关或 forbidden 的分支 |
| `execution_blocked` | 意图正确，但界面状态没有实现预期变化 |
| `replanning_failure` | 错误被观察到后仍沿错误计划继续执行 |
| `recovery_failure` | 尝试补救但未回到可推进状态 |
| `premature_termination` | 必要子任务未完成即结束 |
| `fail_to_terminate` | 全局完成后仍持续执行 |

第一版保持现有 subtype 输出兼容，可增加：

```json
{
  "subtype": "missing_required_checkpoint",
  "subtype_v2": "missing_required_subtask"
}
```

### 6.6 新增离线任务进度跟踪器

建议新增 `src/evaluator/task_progress.py`。它对应 CES State Tracker 的评估侧实现，但不参与外部 Agent 的在线决策，而是根据完整轨迹重建每一步的任务进度。

输入：

- task graph
- state sequence
- subtask alignments
- checkpoint/subtask verification results
- action purpose spans
- AB 和 OCR 变化证据

建议输出：

```python
TaskProgressSnapshot(
    step_index=8,
    active_subtask_ids=["st_003"],
    achieved_subtask_ids=["st_001", "st_002"],
    blocked_subtask_ids=[],
    available_subtask_ids=["st_003", "st_004"],
    current_branch="branch_a",
    progress_score=0.5,
    state_summary="目标表单已打开，必填字段尚未全部完成",
)
```

核心职责：

1. 根据实际达成步骤更新 subtask 状态，而不是根据 Agent 自述更新。
2. 维护依赖已经满足、当前可执行和被阻塞的子任务集合。
3. 识别进度丢失、错误分支、返回修改和重新进入目标路径。
4. 为首错归因、提前终止、未能终止和恢复评估提供统一时间线。

这项能力应优先于 RL，因为当前 `state_sequence` 已具备大部分输入信号，但尚未形成任务级状态维护。

### 6.7 新增恢复评估模块

建议新增 `src/evaluator/recovery.py`，输入：

- task graph
- subtask alignments
- verification results
- state sequence
- repeated action result
- AB/state change evidence

核心事件模型：

```python
RecoveryEvent(
    trigger_step=7,
    trigger_type="wrong_branch",
    detected_step=8,
    recovery_start_step=9,
    recovered_step=12,
    recovery_status="successful",
    rollback_state_id="state_003",
    extra_action_count=4,
)
```

恢复结果分为：

- `no_deviation`：没有明显偏差。
- `self_corrected`：偏差后成功恢复，映射 remedial deviation。
- `unrecovered`：有恢复尝试但未成功。
- `cascading`：错误持续传播并影响后续多个子任务。
- `uncertain`：证据不足。

这可以作为后续接入 `src/trajectory/differential_judger.py` 的统一中间层。

## 7. 核心算法设计

### 7.1 层级任务分解

推荐使用“两阶段生成 + 确定性校验”，而不是多 Agent 自由讨论：

```text
LLM 生成 TaskGraph
  -> 本地 schema 与图算法校验
  -> 发现问题时携带 issues 调用一次 LLM 修正
  -> 再次本地校验
  -> 输出 ok / warning / invalid
```

本地必须检查：

- subtask ID 唯一。
- 所有依赖目标存在。
- `requires` 图无环。
- required subtask 至少一个。
- 每个 required subtask 至少有一个 success criterion。
- success criterion 可通过 GUI 证据验证。
- 不允许纯动作名称充当子任务。
- 不允许两个 subtask 语义重复。
- alternative group 至少有两个候选分支。
- 全局 goal 至少能被一个终点 subtask 覆盖。

### 7.2 图感知覆盖率

现有简单完成率继续保留，新增长程指标：

```text
required_subtask_coverage
= 达成的 required subtask 权重之和 / required subtask 总权重
```

权重第一版建议：

- 普通 required subtask：1.0
- 全局终态 subtask：2.0
- 高风险提交/确认 subtask：1.5
- optional subtask：不进入 required coverage

权重应配置化，并在人工标注集上校准。

### 7.3 依赖与顺序判定

对每条 `requires(A, B)`：

```text
如果 B 首次有效尝试发生在 A 达成之前：
  - B 未产生状态推进：记录 dependency_warning
  - B 进入错误或 forbidden 状态：dependency_violation
  - B 最终在 A 完成后成功：记为 self_corrected，不直接判任务失败
```

不要仅凭动作时间顺序判断，必须结合 A 的实际达成步骤。

### 7.4 首错归因

首错候选按以下优先级归因：

```text
目标误解
  > 必要子任务遗漏
  > 依赖违反/错误分支
  > 正确计划下的执行失败
  > 错误后的重规划失败
  > 终止异常
```

首错步骤定义为“最早出现高置信异常证据且后续未立即消除影响的步骤”，而不是最终失败步骤。

### 7.5 恢复能力评分

建议输出独立恢复指标，不直接混入任务完成率：

```text
recovery_score =
  1.0  成功恢复且没有影响后续 required subtask
  0.7  成功恢复但产生明显额外动作
  0.3  有正确恢复意图但未恢复到稳定状态
  0.0  无恢复或错误继续级联
```

最终报告同时展示：

- task success
- planning correctness
- execution correctness
- recovery capability
- efficiency

## 8. RAG 与知识表示优化

当前 Markdown 文档检索可继续使用，但建议将 App 知识逐步结构化为：

```yaml
app: settings
states:
  - state_id: privacy_page
    observable_signals:
      - title contains "隐私"
      - target setting item visible
transitions:
  - from: settings_home
    to: privacy_page
    intent: enter_privacy_settings
skills:
  - skill_id: locate_setting_item
    goal_pattern: find and open a named setting
```

RAG 在本项目中只用于：

- 补充 App 页面关系。
- 提供功能入口和状态别名。
- 提供可观察完成条件。
- 提供常见合法替代路径。

RAG 内容不能直接作为任务已完成的证据。

### 8.1 Decomposition Experience Bank

参考 PEEU 的 hindsight experience 思路，建议在正式 RAG 之外建立独立的分解经验库。经验库用于保存“原始分解、真实结果、首错归因和人工修正”之间的对应关系。

```json
{
  "experience_id": "exp_0001",
  "instruction": "提交报销申请",
  "app_domain": "expense",
  "generated_task_graph": {},
  "corrected_task_graph": {},
  "trajectory_outcome": "failed",
  "first_error_type": "missing_required_subtask",
  "first_error_step": 7,
  "decomposition_issue": "遗漏提交前确认和金额校验",
  "recommended_pattern": "高风险提交必须包含输入校验和最终确认状态",
  "evidence_sources": ["human_annotation", "verification_report"],
  "validation_status": "human_verified"
}
```

数据进入正式检索库前必须经过：

```text
失败或低质量样本
  -> 首错归因
  -> 判断是否属于任务分解问题
  -> 人工修正 TaskGraph
  -> 提取候选模板/反模式
  -> 离线审核
  -> A/B 评估
  -> 晋升为正式 RAG 知识
```

禁止将以下信号未经确认直接写入 RAG：

- 单次 VLM `not_achieved` 结果。
- Agent 没有执行但分解本身正确的样本。
- Grounding、环境中断或应用缺陷导致的失败。
- verifier 低置信或截图缺失样本。

经验库应支持 `candidate -> human_verified -> production` 生命周期，避免错误经验持续污染后续分解。

## 9. 输出设计

建议新增 `planning_evaluation.json`：

```json
{
  "schema_version": "planning_evaluation.v2",
  "task_uuid": "case-001",
  "goal_status": "failed",
  "required_subtask_coverage": 0.67,
  "planning_label": "abnormal",
  "primary_subtype": "replanning_failure",
  "first_error_step": 7,
  "subtask_results": [],
  "dependency_results": [],
  "recovery_events": [],
  "constraint_violations": [],
  "confidence": {
    "rule": 0.91,
    "model": 0.76,
    "fused": 0.84
  },
  "evidence": []
}
```

`baseline_result.json` 只保存摘要和引用，`full/debug` 模式再写完整中间报告。

## 10. 分阶段实施计划

### P0：TaskGraph schema 与兼容投影

目标：不改变现有评估结果的前提下，引入新数据模型。

- [ ] 新增 `src/decomposer/models.py` 和 `schema.py`。
- [ ] 实现 `decompose_graph()`。
- [ ] 实现 TaskGraph DAG 校验。
- [ ] 实现 `project_checkpoints(task_graph)`。
- [ ] 在 `payload.json` 写入 `_task_graph` 和 schema version。
- [ ] 保持 `_checkpoints`、`step_level_instruction` 和现有测试兼容。
- [ ] 增加旧 checkpoint 到 TaskGraph 的迁移函数。

验收条件：

- 现有基线测试全部通过。
- 老 payload 可以继续运行。
- 新 payload 同时包含 `_task_graph` 和 `_checkpoints`。
- DAG 非法、依赖缺失和不可验证终态可以被本地校验发现。

### P1：图感知对齐与规划失效

目标：让任务依赖真正进入评估逻辑。

- [ ] 新增 `SubtaskAlignment`。
- [ ] 支持 allowed reorder 和 alternative branch。
- [ ] verifier 支持多 criterion 聚合与 `partial`。
- [ ] planning failure 消费 task graph 和 state sequence。
- [ ] 实现 dependency violation、wrong branch 和 goal misunderstanding。
- [ ] 输出 `planning_evaluation.json`。
- [ ] 合并或废弃重复的 planning failure 实现。

验收条件：

- 合法换序任务不会被误判。
- 依赖违反能定位到首个违规子任务和步骤。
- 能区分 not attempted 与 attempted but blocked。
- alternative 分支只要求一条合法路径达成。

### P1：人工标注评测闭环

目标：在继续增加规则前建立定量依据。

- [ ] 建立 100-300 条跨 App 标注集。
- [ ] 标注 TaskGraph、subtask span、完成状态、首错步骤、恢复结果、异常顶层标签、subtype 和证据引用。
- [ ] 新增 `src/evaluator/benchmark.py`。
- [ ] 输出分解、对齐、验证、规划失效和恢复指标。
- [ ] 按任务长度、App、1.2 顶层异常类型和 subtype 分桶。

### P1：按 1.2 七类异常补齐 taxonomy

目标：异常事件的顶层分类与 `docs/GUI_Agent_异常Case_技术洞察.md` 1.2 保持一致。

- [ ] 循环/死循环：复用 state sequence、页面签名、动作循环和无进展证据。
- [ ] 重复动作：复用现有 repeated detector，并输出统一事件。
- [ ] Grounding 错误：结合动作目标、坐标、页面变化和 OCR/UI 证据。
- [ ] 规划失效：由 TaskGraph/TaskProgress 驱动，不只依赖 flat checkpoint。
- [ ] Hallucination：对比 agent 描述、action purpose、页面描述和 OCR/UI 证据。
- [ ] 异常中断响应：覆盖验证码、登录、权限弹窗、Crash、网络加载等中断状态。
- [ ] 提前终止：从 planning failure 子类型提升为顶层事件。

执行阻塞、恢复失败、错误级联、效率、证据完整度和高风险操作只作为 subtype、recovery outcome、impact、report metric 或 risk attribute，不作为新的顶层异常分类。

### P1：任务进度跟踪与经验数据飞轮

- [ ] 新增 `src/evaluator/task_progress.py`。
- [ ] 输出逐步骤 TaskProgressSnapshot。
- [ ] 识别 active/available/blocked/achieved subtask。
- [ ] 建立 Decomposition Experience Bank schema。
- [ ] 保存 generated/corrected TaskGraph 对。
- [ ] 从人工确认的首错样本提取候选规则和任务模板。
- [ ] 建立 candidate、human_verified、production 生命周期。
- [ ] 对 Experience Bank 检索前后运行固定集 A/B 评估。

### P2：恢复与错误级联

- [ ] 新增 `src/evaluator/recovery.py`。
- [ ] 识别错误后重定位、返回、替代路径和重新尝试。
- [ ] 接入 `src/trajectory/differential_judger.py`。
- [ ] 输出 `no_deviation/remedial/cascading`。
- [ ] 增加恢复成本、恢复时延和恢复成功率。

### P2：知识图和世界模型增强

仅在数据证明有收益时实施：

- [ ] 将高频 App Markdown 知识转换为状态/转换/技能图。
- [ ] 使用真实轨迹补全合法替代路径。
- [ ] 对不可逆操作增加有限的 next-state 风险判断。
- [ ] 不在第一阶段训练独立世界模型。

### P3：专用 Decomposer 训练与执行反馈 RL

只有在 TaskGraph 标注、人工指标、稳定 verifier 和在线执行环境全部具备后再实施：

- [ ] 使用 corrected TaskGraph 进行 SFT。
- [ ] 构造优劣分解对，优先尝试 DPO/Preference Learning。
- [ ] 训练独立 decomposition reward model，并校准其与人工判断的一致性。
- [ ] 若项目扩展为在线 Agent harness，再引入 CES 式 Coordinator/State Tracker 联合训练。
- [ ] Executor 保持冻结或独立版本化，避免高低层同时变化导致奖励不可归因。

执行反馈奖励不得只使用 Darwin/VLM 单一结果，至少应组合：

- 人工 TaskGraph 或任务模板一致性。
- 确定性任务终态或环境 reward。
- required subtask recall 和 dependency correctness。
- 冗余、环路和图复杂度惩罚。
- 独立 verifier 结果及人工抽检结果。

推荐训练演进顺序：

```text
Prompt + Schema
  -> corrected TaskGraph SFT
  -> DPO / Preference Learning
  -> Reward Model
  -> execution-feedback RL
```

## 11. 评测指标

### 11.1 Decomposer

| 指标 | 定义 |
|---|---|
| Goal Accuracy | 最终目标识别正确率 |
| Required Subtask Recall | 人工必要子任务被召回比例 |
| Subtask Precision | 生成子任务中合理且必要的比例 |
| Dependency F1 | 依赖边识别 F1 |
| Constraint Recall | 用户约束召回率 |
| Verifiability Rate | 有明确可观察成功条件的子任务比例 |
| Redundancy Rate | 重复或无必要子任务比例 |

### 11.2 Alignment 与 Verification

| 指标 | 定义 |
|---|---|
| Attempt Recall | 实际尝试的子任务被正确召回比例 |
| Span IoU / Boundary Error | 子任务步骤区间对齐质量 |
| Status Macro-F1 | achieved/partial/failed/uncertain 分类 F1 |
| Forbidden-state Precision | 禁止状态命中准确率 |
| Uncertain Calibration | 不确定输出与真实错误率的关系 |

### 11.3 Planning 与 Recovery

| 指标 | 定义 |
|---|---|
| Planning Failure Macro-F1 | 各规划失效 subtype 的 Macro-F1 |
| First-error Accuracy | 首错类型准确率 |
| First-error Step MAE | 预测首错步骤与标注步骤的平均误差 |
| Recovery Detection F1 | 是否发生恢复及结果判定 F1 |
| Cascading Detection F1 | 错误级联识别 F1 |

### 11.4 系统指标

- 每任务 LLM/VLM 调用数。
- 每任务 token、延迟和成本。
- 缓存命中率。
- 图片、OCR 和 action purpose 缺失率。
- 不同输出模式的文件数和存储量。

## 12. 测试方案

### 12.1 单元测试

- TaskGraph JSON 解析和 schema version。
- DAG 环检测、未知依赖和 alternative group 校验。
- TaskGraph 到 checkpoint 投影。
- 旧 checkpoint 到 TaskGraph 迁移。
- allowed reorder 和 dependency violation。
- 多次尝试与最终成功选择。
- partial、forbidden 和 uncertain 聚合。
- recovery event 和 cascading 计算。

### 12.2 场景测试

至少覆盖：

1. 纯线性设置任务。
2. 表单字段可交换顺序任务。
3. 两条替代路径均合法的任务。
4. 走错页面后返回并成功完成。
5. 走错页面后持续探索并失败。
6. 正确意图但点击未生效。
7. 必要子任务未尝试即结束。
8. 任务已完成但持续重复操作。
9. 高风险提交前缺少必要确认。
10. 截图或 OCR 缺失导致证据不足。

### 12.3 回归策略

- P0 阶段要求现有测试结果不下降。
- 新功能默认通过 feature flag 开启，例如 `TASK_GRAPH_ENABLED=1`。
- 同一批样本并行输出 v1 和 v2 结果，进行差异分析。
- 未建立人工指标前，不删除 `_checkpoints` 和旧 planning subtype。

## 13. 风险与控制

| 风险 | 控制措施 |
|---|---|
| LLM 生成伪依赖 | 本地图校验 + 人工标注校准 + 低置信降级 |
| 图结构过度复杂 | 限制 3-8 个语义子任务，禁止动作级节点 |
| 合法多路径误判 | allowed reorder、alternative branch 和后置条件优先 |
| VLM 成本继续上升 | criterion 合并、截图哈希缓存和候选召回后验证 |
| 新旧结果不可比 | schema version、兼容投影和双轨输出 |
| RAG 知识过时 | 记录来源和版本，不把 RAG 当执行证据 |
| 固定置信度失真 | 区分规则、模型和融合置信度，并用标注集校准 |

## 14. 推荐落地顺序

```text
人工评测 schema
  -> TaskGraph 数据模型
  -> checkpoint 兼容投影
  -> 离线 TaskProgressTracker
  -> 图感知 alignment
  -> 多条件 verifier
  -> graph-aware planning failure
  -> Decomposition Experience Bank
  -> recovery / cascading
  -> App 状态图与有限 world-model 增强
  -> 专用 Decomposer 训练与 execution-feedback RL
```

优先级判断：

1. **最先做 TaskGraph schema 和标注规范**，否则后续无法量化。
2. **第二步改 decomposer 和 compatibility projection**，保持主链可运行。
3. **第三步让 alignment/planning failure 消费依赖关系**，形成实际收益。
4. **第四步建立人工审核的 Experience Bank**，形成可控的数据飞轮。
5. **最后实现恢复、知识图、世界模型和 RL 增强**，避免提前扩大复杂度。

## 15. 参考依据

### 项目内文档

- `docs/01-技术方案.md`
- `docs/04-当前进展与开发计划.md`
- `docs/05-GUI_Agent执行评估总体方案.md`
- `docs/规划失效异常判定技术方案.md`
- `docs/GUI_Agent_异常Case_技术洞察.md`

### 外部研究

1. K²-Agent: Co-Evolving Know-What and Know-How for Hierarchical Mobile Device Control  
   https://arxiv.org/abs/2603.00676
2. IntentCUA: Learning Intent-level Representations for Skill Abstraction and Multi-Agent Planning in Computer-Use Agents  
   https://arxiv.org/abs/2602.17049
3. Why Do LLM-based Web Agents Fail? A Hierarchical Planning Perspective  
   https://arxiv.org/abs/2603.14248
4. Executable Agentic Memory for GUI Agent  
   https://arxiv.org/abs/2605.12294
5. BEAP-Agent: Backtrackable Execution and Adaptive Planning for GUI Agents  
   https://arxiv.org/abs/2601.21352
6. MobileDreamer: Generative Sketch World Model for GUI Agent  
   https://arxiv.org/abs/2601.04035
7. Demo2Tutorial: From Human Experience to Multimodal Software Tutorials  
   https://arxiv.org/abs/2606.03951
8. ActionEngine: From Reactive to Programmatic GUI Agents via State Machine Memory  
   https://arxiv.org/abs/2602.20502
9. InfiGUI-R1: Advancing Multimodal GUI Agents from Reactive Actors to Deliberative Reasoners  
   https://arxiv.org/abs/2504.14239
10. Empowering GUI Agents via Autonomous Experience Exploration and Hindsight Experience Utilization for Task Planning (PEEU)  
    https://arxiv.org/abs/2606.27330
11. Training High-Level Schedulers with Execution-Feedback Reinforcement Learning for Long-Horizon GUI Automation (CES)  
    https://arxiv.org/abs/2511.22235

## 16. 最终决策

`gui-agent-evaluation` 下一阶段不应简单替换更大的 LLM/VLM，也不应直接实现完整 GUI Planner。最有价值的升级是：

> 将当前 `_checkpoints` 从扁平状态列表提升为 TaskGraph 的兼容投影，以离线 TaskProgressTracker 重建任务进展，并通过人工审核的 Experience Bank 建立持续优化的数据闭环；CES 式执行反馈 RL 仅作为具备可靠奖励和在线环境后的长期方向。

该路线吸收了 InfiGUI-R1 的层级子目标、PEEU 的 hindsight experience 和 CES 的状态跟踪思想，能复用当前全部核心模块，同时避免在评估指标和奖励信号尚未稳定时过早引入 RL。
