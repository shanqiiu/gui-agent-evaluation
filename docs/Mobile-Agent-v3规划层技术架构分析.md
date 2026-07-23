# Mobile-Agent-v3 规划层技术架构分析

> 技术分析文档 | 2026-07-20  
> 源码版本：Mobile-Agent-v3 (open-source release)  
> 对应论文：[Mobile-Agent-v3: Fundamental Agents for GUI Automation](https://arxiv.org/abs/2508.15144)

---

## 一、整体架构：Multi-Agent 协作框架

Mobile-Agent-v3 采用 **Multi-Agent 协作架构**，将 GUI 自动化任务拆解为由四个专职 Agent 组成的闭环协作系统：

```
                    ┌──────────────┐
                    │  用户指令     │
                    │  (自然语言)   │
                    └──────┬───────┘
                           │
                           ▼
               ┌─────────────────────┐
               │   Manager（规划层）   │  ← 制定/修订高层计划
               │   子目标拆解 & 动态规划 │
               └─────────┬───────────┘
                         │ plan, current_subgoal
                         ▼
               ┌─────────────────────┐
               │  Executor（执行层）   │  ← 子目标 → 原子动作映射
               │   原子动作决策        │
               └─────────┬───────────┘
                         │ 动作执行
                         ▼
               ┌─────────────────────┐
               │ ActionReflector      │  ← 前后截图对比，判定成败
               │ （反思/验证层）        │
               └─────────┬───────────┘
                         │ outcome: A/B/C
              ┌──────────┴──────────┐
              │ 失败累计 ≥ 阈值       │ 成功：继续执行下一子目标
              ▼                     │
    Manager 介入，修订计划            │
              │                     │
              └──────────┬──────────┘
                         │
                         ▼
              ┌─────────────────────┐
              │  Notetaker（记忆层）  │  ← 关键信息持久化（可选）
              └─────────────────────┘
```

**核心调度逻辑**（`run_mobileagentv3.py:55-306`）：

```python
for step in range(max_step):
    # 1. 错误升级检测：连续失败是否达到阈值？
    if consecutive_failures >= err_to_manager_thresh:
        info_pool.error_flag_plan = True

    # 2. 规划阶段（单次格式错误可跳过）
    if not skip_manager:
        prompt_planning = manager.get_prompt(info_pool)
        output_planning = vllm.predict_mm(prompt_planning, [screenshot])
        parsed = manager.parse_response(output_planning)
        info_pool.plan = parsed['plan']
        info_pool.completed_plan = parsed['completed_subgoal']

    # 3. 执行阶段
    prompt_action = executor.get_prompt(info_pool)
    output_action = vllm.predict_mm(prompt_action, [screenshot])
    action = executor.parse_response(output_action)
    controller.execute(action)  # click/swipe/type/system_button

    # 4. 反思阶段（前后截图对比）
    prompt_reflect = action_reflector.get_prompt(info_pool)
    output_reflect = vllm.predict_mm(prompt_reflect, [before_screenshot, after_screenshot])
    outcome = action_reflector.parse_response(output_reflect)['outcome']  # A/B/C

    # 5. 记忆阶段（可选）
    if outcome == "A" and if_notetaker:
        important_notes = notetaker.predict(...)
```

---

## 二、规划层（Manager）核心机制

Manager 是整个系统的"大脑"，其核心能力不是简单的「指令 → 步骤」映射，而是**基于视觉感知的增量式动态规划**：每一步都重新审视「当前屏幕状态 + 历史执行轨迹 + 原始用户目标」，决定是继续执行、微调策略还是彻底修改高层计划。

### 2.1 共享状态容器：InfoPool

所有 Agent 通过 `InfoPool`（`mobile_agent_e.py:7-46`）共享上下文，这是一个 `@dataclass` 定义的扁平化状态容器：

```
InfoPool 结构：
├── 用户输入
│   ├── instruction: str          # 用户原始自然语言指令
│   ├── additional_knowledge_manager: str   # 规划层领域知识注入
│   └── additional_knowledge_executor: str  # 执行层领域知识注入
│
├── 工作记忆（增量追加）
│   ├── action_history: list      # 已执行动作序列
│   ├── summary_history: list     # 动作描述序列
│   ├── action_outcomes: list     # 动作结果序列 (A/B/C)
│   └── error_descriptions: list  # 错误描述序列
│
├── 规划状态
│   ├── plan: str                 # 当前完整计划（编号子目标列表）
│   ├── completed_plan: str       # 已完成的子目标汇总
│   ├── current_subgoal: str      # 当前聚焦的子目标
│   └── progress_status: str      # 进度状态描述
│
├── 上一步快照
│   ├── last_action: str          # 最近动作
│   ├── last_summary: str         # 最近动作描述
│   └── last_action_thought: str  # 最近动作推理
│
├── 错误升级
│   ├── error_flag_plan: bool     # 是否触发规划层介入
│   └── err_to_manager_thresh: int  # 升级阈值（默认 2）
│
└── 长期记忆
    └── important_notes: str      # Notetaker 记录的关键信息
```

**关键设计原则**：InfoPool 是所有 Agent 的**唯一真相源（Single Source of Truth）**。Agent 之间不直接通信，全部通过 InfoPool 的读写完成信息传递，避免了多智能体系统中常见的状态不一致问题。

### 2.2 规划的两个阶段

Manager 的 `get_prompt()` 方法实现了**两阶段动态规划**，通过 `info_pool.plan == ""` 判断当前处于哪个阶段：

#### 阶段一：首次规划（Step 0）

当用户指令首次进入系统时，Manager 执行**一次性指令拆解**。此时它看到的是一次手机截图（初始界面）加上用户的原始自然语言指令。

**Prompt 结构**（`mobile_agent_e.py:69-93`）：

```
┌─────────────────────────────────────────────┐
│ System: 你是操作 Android 手机的代理，       │
│         负责跟踪进度并制定高层计划           │
├─────────────────────────────────────────────┤
│ ### User Request ###                        │
│ {用户原始指令，如 "帮我在 Chrome 中搜索      │
│  今天的天气并告诉我结果"}                    │
├─────────────────────────────────────────────┤
│ ### Guidelines ###                          │
│ ├── General: 使用搜索功能快速定位文件或条目  │
│ └── Task-specific: {领域先验知识注入}        │
│     例：".html 文件可能包含画布/游戏元素，   │
│           完成前不要打开其他应用"             │
├─────────────────────────────────────────────┤
│ 指令: 制定高层计划。如果请求复杂，拆解为     │
│       子目标。截图显示手机初始状态。          │
│       如果请求需要答案，将 answer 作为        │
│       计划最后一步。                         │
├─────────────────────────────────────────────┤
│ 输出格式:                                   │
│ ### Thought ###                             │
│ {关于计划和子目标的详细推理}                 │
│                                             │
│ ### Plan ###                                │
│ 1. first subgoal                            │
│ 2. second subgoal                           │
│ ...                                         │
└─────────────────────────────────────────────┘
```

**拆解示例**（基于 prompt 结构推断的典型输出）：

```
### Thought ###
用户想要获取今天天气信息。需要：(1) 打开 Chrome 浏览器，
(2) 在搜索栏输入查询，(3) 阅读结果，(4) 用 answer 返回。
当前屏幕是桌面，需要先找到 Chrome 图标。

### Plan ###
1. Open Chrome browser
2. Navigate to Google search and type "weather today"
3. Read the weather forecast from search results
4. Perform the `answer` action to tell the user the weather
```

**关键设计点**：

1. **视觉感知驱动**：拆解时附带初始截图，模型基于真实界面状态规划，而非纯文本推理。例如，如果 Chrome 图标不在桌面首屏，Manager 可能将 "swipe to find Chrome" 作为第一子目标。
2. **领域知识注入**：通过 `additional_knowledge_manager` 向规划层注入任务特定的约束和启发式规则，避免通用模型在不熟悉的应用场景中做出错误假设。
3. **终止条件显式化**：明确要求将 `answer` 作为最后一步，确保模型理解"需要产生可交付结果"而非"无限探索"。

#### 阶段二：动态修订（Step ≥ 1）

后续步骤中，Manager 接收**完整的历史执行上下文**，判断是否需要修订计划。这是整个系统中最精妙的设计。

**Prompt 结构**（`mobile_agent_e.py:95-143`）：

```
┌─────────────────────────────────────────────┐
│ ### Historical Operations ###               │
│ {已完成的子目标列表（增量追加，不删除历史）} │
│ 例：                                         │
│ 1. Open Chrome browser                      │
│ 2. Navigated to google.com, typed "weather"  │
├─────────────────────────────────────────────┤
│ ### Plan ###                                │
│ {上一轮或原始计划}                           │
│ 1. Open Chrome browser                      │
│ 2. Navigate to Google search and type ...    │
│ 3. Read the weather forecast                 │
│ 4. Perform the `answer` action               │
├─────────────────────────────────────────────┤
│ ### Last Action ###                         │
│ {最近一次动作: {"action": "click", ...}}     │
│ ### Last Action Description ###              │
│ {最近一次动作描述}                           │
├─────────────────────────────────────────────┤
│ ### Important Notes ###                     │
│ {Notetaker 记录的关键信息，如搜索到的天气值} │
├─────────────────────────────────────────────┤
│ ### Guidelines ###                          │
│ {同阶段一}                                  │
├─────────────────────────────────────────────┤
│ [条件触发] ### Potentially Stuck! ###        │
│ {当 error_flag_plan=True 时注入}             │
│ - Attempt: Action: {...} | Outcome: Failed   │
│   | Feedback: Clicked wrong icon             │
│ - Attempt: Action: {...} | Outcome: Failed   │
│   | Feedback: No change detected             │
├─────────────────────────────────────────────┤
│ 指令: 仔细评估当前状态和截图。                │
│ 1. 检查计划是否需要修订                      │
│ 2. 判断用户请求是否已完全完成                 │
│ 3. 如果被错误困住，思考是否需要修改整体计划   │
│ 4. 第一个子目标如果已完成，请更新计划         │
│ 5. 不要重复已完成的内容                       │
├─────────────────────────────────────────────┤
│ 输出格式（首次规划后为三部分）:              │
│ ### Thought ###                             │
│ {修订计划的推理}                             │
│                                             │
│ ### Historical Operations ###               │
│ {增量追加最近完成的子目标}                    │
│                                             │
│ ### Plan ###                                │
│ {更新或复制现有计划}                         │
└─────────────────────────────────────────────┘
```

**动态修订的三个决策路径**：

| 状态判断 | Manager 决策 | 触发条件 |
|---------|------------|---------|
| **正常推进** | 将第一子目标标记为完成，移至 Historical Operations，plan 前移 | ActionReflector 返回 A |
| **错误修正** | 不修改计划，仅更新 thought 指导 Executor 换策略重试 | 单次 B/C 但未达阈值 |
| **计划重构** | 彻底修改 plan，可能回退、跳步或完全重规划 | `error_flag_plan=True`（连续 2+ 次失败） |

---

## 三、错误升级机制（Error Escalation）

这是整个框架中**最关键的鲁棒性保障机制**，解决了「局部执行失败如何触发全局策略调整」的核心问题。

### 3.1 双阈值决策逻辑

```python
# run_mobileagentv3.py:82-98

err_to_manager_thresh = 2  # 可配置

# 阈值检查：最近 k 步是否全部失败
latest_outcomes = info_pool.action_outcomes[-err_to_manager_thresh:]
if count(outcome in ["B", "C"] for outcome in latest_outcomes) == err_to_manager_thresh:
    info_pool.error_flag_plan = True  # 升级标志

# 快速重试：单次 invalid 格式错误不升级
if not info_pool.error_flag_plan and last_action == 'invalid':
    skip_manager = True  # 跳过 Manager，Executor 直接重试
```

### 3.2 三层错误响应策略

```
层级 1：Executor 自愈（skip_manager=True）
  └── 条件：单次 invalid 格式错误
  └── 行为：跳过 Manager，Executor 自行修正格式重试
  └── 开销：零（不调用 LLM）

层级 2：Manager 指导修正（默认路径）
  └── 条件：1-2 次失败但未全部失败
  └── 行为：Manager 接收失败反馈，在 thought 中指导 Executor 换策略
  └── 开销：1 次 LLM 调用

层级 3：全局计划重构（error_flag_plan=True）
  └── 条件：连续 err_to_manager_thresh 次全部失败（B 或 C）
  └── 行为：Manager 收到 ### Potentially Stuck! ### 区块，彻底重规划
  └── 开销：1 次 LLM 调用 + 可能的策略大转向
  └── 注入信息：
      - Attempt: Action: {act} | Description: {summ}
        | Outcome: Failed | Feedback: {err_des}
      （重复 err_to_manager_thresh 次）
```

### 3.3 Outcome 的三态分类

ActionReflector 通过对比「动作前截图」和「动作后截图」，输出精确的三态判定：

| Outcome | 含义 | 对规划层的影响 |
|---------|------|-------------|
| **A** | 成功/部分成功。动作结果符合预期 | 推进 progress_status，累计计入 Historical Operations |
| **B** | 失败。进入了错误页面，需要回退 | 累计失败计数，可能需要回退动作 |
| **C** | 失败。动作没有产生任何变化 | 累计失败计数，可能需要换策略重试 |

---

## 四、子任务拆解的语义粒度与格式演化

### 4.1 Android 版本（`mobile_v3`）

采用**扁平编号列表**格式，子目标之间是顺序依赖关系：

```
Plan 格式：
1. Open Chrome browser
2. Navigate to google.com
3. Search for "weather today"
4. Read the weather forecast
5. Perform the `answer` action
```

**特点**：
- 每个子目标是高层语义描述，不包含具体执行细节
- "完成"判定通过 `completed_subgoal` 字段增量追踪
- Executor 通过截取 plan 前 4 个子目标作为 `### Current Subgoal ###`，隐式聚焦最近未完成项

### 4.2 OSWorld 版本（`os_world_v3`）

采用**结构化字典格式**，显式分离「做什么」和「怎么做」：

```
Plan 格式：
1. {'name': 'Open Chrome browser',
    'info': 'Click on the Chrome icon on the desktop taskbar'}
2. {'name': 'Navigate to google.com',
    'info': 'Click the address bar, type www.google.com, press Enter'}
3. ...
```

**增加字段**：
- `name`：高层意图（"What to do"）
- `info`：执行细节（"How to do"），为 Executor 提供精确指导
- `current_subgoal`：显式的当前聚焦子目标

**这个格式演化的意义**：将规划（What）和执行（How）在语义层面解耦，减少了 Executor 因误解高层意图而产生的错误。规划层负责"要达成什么"，并在 `info` 中给出可操作的上下文提示，执行层负责"具体怎么操作"。

---

## 五、规划层与下游 Agent 的接口契约

### 5.1 Manager → Executor 的信息传递

```
Manager.parse_response() 输出:
{
    "thought": "推理过程",
    "completed_subgoal": "已完成的子目标列表",
    "plan": "当前计划（编号列表）"
}
       │
       ▼ InfoPool 写入
info_pool.plan            → Executor.prompt 的 ### Overall Plan ###
info_pool.completed_plan  → Executor.prompt 的 ### Progress Status ###
info_pool.progress_status → Executor.prompt（ActionReflector 更新）
```

Executor 的 prompt（`mobile_agent_e.py:189-266`）中，`### Current Subgoal ###` 通过正则截取 plan 的前 4 个子目标构建：

```python
current_goal = info_pool.plan
current_goal = re.split(r'(?<=\d)\. ', current_goal)
truncated_current_goal = ". ".join(current_goal[:4]) + '.'
```

这是一种**隐式焦点机制**：始终让 Executor 聚焦于最近未完成的子目标，避免上下文过长导致的注意力稀释。

### 5.2 ActionReflector → Manager 的反馈回路

```
ActionReflector.parse_response() 输出:
{
    "outcome": "A" | "B" | "C",
    "error_description": "失败原因描述"
}
       │
       ▼ InfoPool 写入
info_pool.action_outcomes   → 触发 error_flag_plan 判定
info_pool.error_descriptions → 注入 Manager 的 Potentially Stuck 区块
info_pool.progress_status    → 进度描述，供下轮规划参考
```

### 5.3 Notetaker → Manager 的记忆增强

```
Notetaker.parse_response() 输出:
{
    "important_notes": "关键信息记录"
}
       │
       ▼ InfoPool 写入
info_pool.important_notes → Manager.prompt 的 ### Important Notes ###
```

Notetaker 仅在动作成功（outcome="A"）时被调用，避免将错误状态下的噪声信息写入长期记忆。

---

## 六、原子动作空间

Executor 可发出的**6 种原子动作**（`mobile_agent_e.py:158-183`），定义了规划层策略的"执行边界"：

| 动作 | 参数 | 说明 |
|------|------|------|
| `click` | `coordinate: [x, y]` | 点击屏幕坐标 |
| `swipe` | `coordinate: [x1,y1]`, `coordinate2: [x2,y2]` | 滑动/滚动 |
| `type` | `text: str` | 输入文本（需先激活输入框） |
| `system_button` | `button: "Back"\|"Home"` | 系统级按钮 |
| `long_press` | `coordinate: [x, y]` | 长按 |
| `answer` | `text: str` | 输出答案，任务终止 |

**规划层不关心具体坐标**——它输出的是高层子目标。坐标决策完全由 Executor 承担。这保证了规划层的跨设备和跨分辨率泛化能力。

---

## 七、核心设计模式总结

| 设计模式 | 实现方式 | 解决的问题 |
|---------|---------|-----------|
| **Plan-then-Execute** | Manager 制定高层计划 → Executor 映射为原子动作 | 将复杂任务分解为可管理的子目标 |
| **Re-planning on Failure** | 连续失败触发 Plan Revision | 局部错误不会导致全局失败 |
| **Skip-on-Invalid** | 单次格式错误跳过 Manager | 避免对 LLM 格式抖动的过度反应 |
| **Structured Output Parsing** | `### Thought ###` / `### Plan ###` 等标记分割 | 确定性解析，不依赖 JSON 格式 |
| **Shared State Pool** | InfoPool 作为唯一真相源 | 多 Agent 状态一致性 |
| **External Knowledge Injection** | `additional_knowledge_*` 字段 | 向通用模型注入领域特定的约束和启发式 |
| **Visual Grounding** | 每次规划/执行都附带屏幕截图 | 所有决策基于真实界面状态 |
| **Dual-Screenshot Reflection** | 前后截图对比判定动作效果 | 精确的动作级反馈 |
| **Conditional Memory** | Notetaker 仅在成功时记录 | 避免错误上下文污染长期记忆 |

---

## 八、关键代码索引

| 文件 | 关键内容 | 行号 |
|------|---------|------|
| `mobile_v3/run_mobileagentv3.py` | 主循环：规划→执行→反思→记忆 | 55-306 |
| `mobile_v3/utils/mobile_agent_e.py` | InfoPool, Manager, Executor, ActionReflector, Notetaker | 全文件 |
| `mobile_v3/utils/mobile_agent_e.py` | Manager.get_prompt() - 首次规划 | 69-93 |
| `mobile_v3/utils/mobile_agent_e.py` | Manager.get_prompt() - 动态修订 | 95-143 |
| `mobile_v3/utils/mobile_agent_e.py` | Manager.parse_response() | 146-154 |
| `mobile_v3/utils/mobile_agent_e.py` | 错误升级逻辑（外部） | run_mobileagentv3.py:82-98 |
| `mobile_v3/utils/mobile_agent_e.py` | 原子动作定义 | 158-183 |
| `mobile_v3/utils/call_mobile_agent_e.py` | VLM 调用封装 | 全文件 |
| `os_world_v3/.../mobile_agent_modules.py` | OSWorld 版 Manager（结构化规划） | 328-443 |
| `os_world_v3/.../mobile_agent.py` | OSWorld 版主循环 | 252-474 |

---

## 九、设计启示与可借鉴点

1. **分阶段规划**（首次拆解 vs 增量修订）是一种低开销的规划策略——不需要每步都从头推理，也不需要维持复杂的规划树；
2. **错误升级阈值**（`err_to_manager_thresh`）是可调的，为不同任务难度提供了灵活性；
3. **Skip-on-Invalid** 是一个简单但有效的优化：避免了因 LLM 格式抖动产生的不必要规划开销；
4. **InfoPool 扁平化设计**降低了多 Agent 通信复杂度——没有消息传递协议，只有共享内存读写；
5. **Visual Grounding** 贯穿全流程——规划、执行、反思全部基于截图，这是 Mobile Agent 区别于文本 Agent 的核心特征；
6. **领域知识可插拔** —— `additional_knowledge_manager` / `additional_knowledge_executor` 为不同任务场景（文件管理、音频录制等）提供定制化的先验知识注入通道。

---

## 十、对 gui-agent-evaluation 项目的技术借鉴评估

> 更新日期：2026-07-20
> 基于对 Mobile-Agent-v3 源码（`mobile_v3/`）和 gui-agent-evaluation 源码（`src/`）的交叉分析。

### 10.1 两项目定位对比

| 维度 | Mobile-Agent-v3 | gui-agent-evaluation |
|---|---|---|
| 模式 | **Online 执行**：VLM 驱动实时决策 | **Offline 评测**：事后验证 Agent 轨迹 |
| 核心数据 | 实时截图 + 指令 | Agent 执行日志（动作/控件坐标-名称/步骤语义推导）+ 操作截图序列 |
| 检查点/子目标生成 | Manager：指令 + 初始截图 → 扁平编号列表 | Decomposer：纯文本指令 + RAG 知识 → 结构化 JSON |
| 检查点 → 动作映射 | Executor 隐式推理：手持当前子目标 + 截图 → 1个原子动作 | Verifier 显式匹配：intent recall → alignment → VLM 验证 |
| 动作级反馈 | **有**：ActionReflector 每步输出 A/B/C（成功/错误页/无变化）| **部分有**：ABValidator 输出符合预期/不符合预期/无法判定，但未区分错误页 vs 无变化 |
| 闭环重规划 | 连续失败 → error_flag_plan → Manager 重规划 | 无闭环（纯评测，不驱动 Agent 行为） |
| 记忆机制 | Notetaker：仅在动作成功时记录关键信息 | 无 |

### 10.2 gui-agent-evaluation 的已有优势

gui-agent-evaluation 的执行证据链比 Mobile-Agent-v3 的 InfoPool 更为丰富：

| 证据层 | gui-agent-evaluation 已有 | Mobile-Agent-v3 对应物 |
|---|---|---|
| 动作类型 + 坐标 + 文本 | `seq_info[].planning_output.parsed_action` | `InfoPool.action_history`（仅记录动作 JSON） |
| 动作前后截图 | `seq_info[].image_relative_path` + `hydrate_payload_images` | 仅保留当前步和上一步截图 |
| Agent 步骤级语义推导 | `seq_info[].action_purpose` / `_action_purposes` | `InfoPool.summary_history`（更简略） |
| 控件坐标/名称 | 部分 payload 包含 | 无（仅通过截图视觉定位） |
| 页面 AB 对比验证 | `ABValidator` → `StepABResult`（含 pagea/b_description） | ActionReflector（仅输出 A/B/C 标签） |
| 检查点结构化定义 | `{name, required, preconditions, expected_state}` | 扁平编号文本列表 |

Mobile-Agent-v3 的 Agent 仅凭**截图 + 指令**做决策，而 gui-agent-evaluation 采集的是 Agent 全量执行日志，信息密度更高，具备做更精细分析的先天条件。

### 10.3 核心架构差距：缺失的动作级 A/B/C 分层

Mobile-Agent-v3 的最精巧设计不是"有截图对比"，而是**将截图对比结果三态化并嵌入闭环**：

```
Mobile-Agent-v3:
  ActionReflector(前截图 + 后截图) → outcome ∈ {A, B, C}
    A: 成功/部分成功 → 推进 progress_status
    B: 进入了错误页面 → 可能需要回退 → 累计失败计数
    C: 无任何变化 → 换策略重试 → 累计失败计数
  连续 B/C ≥ err_to_manager_thresh → Manager 重规划
```

gui-agent-evaluation 的 ABValidator 已经逐步骤产出了 `label ∈ {"符合预期", "不符合预期", "无法判定"}`，这本质上是**一个弱化的二态判定**——"不符合预期"将 B 和 C 合并了。B（错误页）和 C（无变化）在评估 Agent 质量时含义完全不同：

- B 型失败说明 Agent **意图方向对但目标定位错**（例如点了相邻控件）
- C 型失败说明 Agent **动作未生效**（例如点了不可点击区域、或页面未加载完成）

**这是一个低实现成本的增强**：ABValidator 已经在调用 VLM 对比截图并产出了 `pagea_description`、`pageb_description`、`thought` 等详细中间产物。只需在 prompt 中增加 B/C 区分指令，并在 `StepABResult` 中增加一个 `outcome` 字段即可：

```python
# 当前: StepABResult.label ∈ {"符合预期", "不符合预期", "无法判定"}
# 增强: StepABResult.outcome ∈ {"A", "B", "C"}  # 映射 Mobile-Agent-v3 语义
#   A: 页面切换符合预期
#   B: 进入了与预期无关的错误页面（可回退）
#   C: 页面无任何实质变化
```

### 10.4 动作级 A/B/C 的 downstream 价值

一旦有了动作级 A/B/C 序列，gui-agent-evaluation 现有的 planning failure 检测可以做到更精确的归因：

```json
// 当前 planning_failure evidence:
"必要 checkpoint 有意图匹配但截图/VLM 未证明达成：设置搜索结果已展示"

// 增强后（结合动作级 A/B/C 序列）:
"checkpoint '设置搜索结果已展示' 未达成。关联步骤 7-9:
  step 7 点击搜索框 → A (成功，搜索框已激活)
  step 8 点击搜索按钮 → C (无变化，可能点击了不可交互区域)
  step 9 点击第二个搜索按钮 → B (进入了错误的搜索结果页)
  → 根因推断: Agent 定位到错误的搜索入口控件"
```

此外还可以支撑新的检测维度：

| 新增检测 | 证据 | 含义 |
|---|---|---|
| **B 型失败密度** | 轨迹中 B 占比过高 | Agent 控件定位能力弱（视觉感知问题，非规划问题） |
| **C 型失败密度** | 轨迹中 C 占比过高 | Agent 动作执行无效（交互时序问题或控件状态判断错误） |
| **B→Back→重试模式** | B 后出现 Back + 重试同类型动作 | 典型的目标定位偏移后自愈 |
| **连续 C 无重规划** | 连续 C 但无策略变化 | Agent 缺乏自省能力 |

### 10.5 InfoPool 扁平化状态管理借鉴

Mobile-Agent-v3 的 `InfoPool` dataclass 是所有 Agent 的唯一真相源，通过属性读写而非消息传递完成跨模块通信。gui-agent-evaluation 当前各模块间的数据流转依赖 JSON 文件 + 函数参数 + payload dict 隐式传递，存在状态不一致风险。

可借鉴方案：定义一个 `EvalContext` dataclass，作为基线编排的统一状态容器：

```python
@dataclass
class EvalContext:
    """Single source of truth for evaluation pipeline state."""
    # 输入
    instruction: str = ""
    payload: dict = field(default_factory=dict)
    checkpoints: list[Checkpoint] = field(default_factory=list)

    # AB 层
    ab_report: ABValidationReport | None = None

    # 意图层
    intent_matches: list[CheckpointIntentMatch] = field(default_factory=list)
    checkpoint_alignments: list[CheckpointAlignment] = field(default_factory=list)

    # 验证层
    verification_report: VerificationReport | None = None
    state_sequence: Any = None

    # 异常层
    repeated_prediction: Any = None
    planning_failure_result: PlanningFailureResult | None = None
```

这避免了在 `repeated_baseline.run_repeated_baseline()` 中将十多个中间产物作为函数参数传递的模式，降低了模块重构时的接口变更风险。

### 10.6 错误升级阈值应用于检查点粒度自校准

Mobile-Agent-v3 的 `err_to_manager_thresh` 思路可以转化为 gui-agent-evaluation 的**检查点质量诊断**：

在 `planning_failure.py` 的 `detect_planning_failure()` 输出中增加检查点粒度的统计字段：

```python
# 每个 checkpoint 的消耗分析
{
  "checkpoint_index": 2,
  "name": "搜索结果已展示",
  "agent_steps_consumed": 8,           # Agent 花了 8 个步骤
  "action_outcome_distribution": {      # ← 需要动作级 A/B/C
      "A": 5, "B": 1, "C": 2
  },
  "quality_flag": "coarse"  # 粒度过粗标记
}
```

如果一个 checkpoint 平均消耗步数远超整体均值且伴随高 B/C 率，说明这个检查点的 `expected_state` 可能定义得过粗或模糊，Agent 无法准确理解目标。这些标记可以**反馈给 Decomposer**的 prompt 作为 `### 上一次分解质量反馈 ###`，形成检查点质量的自我校准闭环。

### 10.7 总结：优先级排序

| 优先级 | 借鉴点 | 实现成本 | 价值 |
|---|---|---|---|
| P0 | ABValidator 增加 A/B/C 三态 outcome | 低：仅修改 prompt + StepABResult 字段 | 为 planning failure 提供动作级归因能力 |
| P1 | 动作级 A/B/C 驱动 planning failure 增强 | 中：需 consumption_analyzer + subtype 扩展 | 区分"规划问题"和"执行问题" |
| P2 | EvalContext 扁平化状态管理 | 中：需重构 baseline 编排入口 | 降低跨模块状态不一致风险 |
| P3 | 检查点粒度自校准反馈循环 | 高：需 Decomposer → Verifier → Decomposer 回路 | 提升检查点生成质量
