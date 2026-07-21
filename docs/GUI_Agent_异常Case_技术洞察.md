# GUI Agent 异常 Case 技术洞察说明

状态：异常 taxonomy 和研究洞察材料；其中 1.2 “异常 case 的定义边界”作为当前实现采用的顶层异常分类来源。具体字段、输出和工程实现规范以 `docs/01-技术方案.md` 为准。

与当前实现的对应关系：

- 循环/死循环 -> `src.evaluator.state_evidence` + 重复检测器，后续统一输出 `loop` 事件。
- 重复动作 -> `src.common.repeated_action_detector`，后续映射为顶层 `repeated_action` 事件。
- Grounding 错误 -> 待补齐，需结合动作目标、坐标、页面变化和 OCR/UI 证据。
- 规划失效 -> 当前由 `src.evaluator.planning_failure` 第一版聚合，后续接入 TaskGraph/TaskProgress。
- Hallucination -> 待补齐，需对比 agent 描述、action purpose、页面描述和 OCR/UI 证据。
- 异常中断响应 -> 待补齐，验证码、登录、权限弹窗、Crash、网络加载等作为 subtype。
- 提前终止 -> 当前是 planning failure 子类型，后续提升为顶层 `premature_termination` 事件。

---
# GUI Agent 异常Case 技术洞察文档

> **文档版本**: v1.0 · 2026-07-01
> **研究边界**: GUI Agent 在执行自动化任务时产生的各类异常行为，包括循环跳转、重复点击、Grounding 错误、Error Recovery 失败等
> **文献覆盖**: 17 篇精选论文 (2024–2026)，涵盖 ICML、CVPR、AAAI、ACL 等顶会

---

## 目录

1. [背景与问题定义](#1-背景与问题定义)
2. [四维聚类分析框架](#2-四维聚类分析框架)
   - 2.1 维度一：错误发生阶段
   - 2.2 维度二：时序异常模式
   - 2.3 维度三：环境诱导异常
   - 2.4 维度四：能力缺口
3. [核心数据与量化基准](#3-核心数据与量化基准)
4. [关键研究方向与代表论文](#4-关键研究方向与代表论文)
   - 4.1 系统性 Error Taxonomy
   - 4.2 Hallucination 诊断与消除
   - 4.3 Error Recovery 与 Self-Reflection
   - 4.4 记忆机制与长链路问题
   - 4.5 真实环境鲁棒性
5. [跨维度交叉分析](#5-跨维度交叉分析)
6. [缺口与机遇（Research Gaps）](#6-缺口与机遇)
7. [推荐阅读路径](#7-推荐阅读路径)
8. [论文速查表](#8-论文速查表)

---

## 1. 背景与问题定义

### 1.1 为什么 GUI Agent 异常 case 值得专门研究

当前 GUI Agent 在标准 benchmark 上的成功率仍然有限（OSWorld: ~47%，AndroidWorld: ~63%），而这些 benchmark 大多采用 **静态理想化环境**，严重低估了真实部署中的异常频率。

核心矛盾：**Completion Rate ≠ Correctness**。论文 *When Web Agents Finish but Still Fail* 揭示，Agent 可以以 96.0% 的 completion rate 完成任务，但 binary accuracy 远低于此——Agent 自信地声称完成，但答案错误、字段缺失或依赖过期证据。

### 1.2 异常 case 的定义边界

本文关注的异常 case 定义为：**GUI Agent 在执行任务过程中偏离预期行为轨迹的所有可观测事件**，包括：

| 类型 | 典型表现 | 可观测信号 |
|------|---------|-----------|
| 循环/死循环 | 在有限页面集合间反复跳转 | 轨迹重复、步骤数超阈值 |
| 重复动作 | 对同一元素重复点击或输入 | Action history 中出现相同 action |
| Grounding 错误 | 点击坐标偏离目标元素 | Action 发生但 UI 无变化 |
| 规划失效 | 遗漏关键步骤或误解目标 | 任务完成标准未达到 |
| Hallucination | 幻觉出不存在的元素 | 截图与 agent 描述不一致 |
| 异常中断响应 | 无法处理权限弹窗/Crash | 中断弹窗出现后行为异常 |
| 提前终止 | 部分完成即声称完成 | 评估结果与 agent 声称矛盾 |

### 1.3 当前研究的主要特点

- **领域新兴**：GUI Agent 异常 case 无专门综述，相关知识散落在方法论文的 failure analysis 章节
- **数据驱动**：研究方向从经验性 failure analysis 向系统性 taxonomy 演进
- **基准建设**：RoTS (1,216 cases)、D-GARA (152 tasks)、Parallel WebBench (1,679 records)、AndroTMem (1,069 tasks) 等 benchmark 陆续建立

---

## 2. 四维聚类分析框架

> 异常通常不是单一维度的产物，而是多个维度交叉叠加的结果。以下四维框架相互正交，共同覆盖完整的异常空间。

### 2.1 维度一：错误发生阶段（Pipeline 纵向维度）

GUI Agent 的执行管线为：**Perception → Reasoning → Execution → Planning/Termination**。不同阶段发生的错误性质不同，下游阶段的异常往往是上游错误的级联后果。

#### 感知阶段 Perception（4 类）

| 子类型 | 具体表现 | 发生率 | 来源 |
|--------|---------|--------|------|
| **PH.1 截图状态误判** | 对当前屏幕全局语义状态错误判断，认为已完成但实际未生效 | — | HalluClear |
| **PH.2 元素存在性幻觉** | 幻觉出界面上不存在的按钮/菜单项 | — | HalluClear, GUI Knowledge Bench |
| **PH.3 元素属性误识别** | 误判按钮可点击性、文本框可编辑性、元素功能类型 | — | HalluClear |
| **PH.4 元素关系误判** | 误判元素间的空间层级关系或父子关系 | — | HalluClear |

> **关键机制**：感知层幻觉会触发级联失败 (Cascading Failures)——错误的感知导致错误的推理，再导致错误的动作。HalluClear 提供了针对该层的系统性 taxonomy 和 mitigation 方案。

#### 推理阶段 Reasoning（4 类）

| 子类型 | 具体表现 | 来源 |
|--------|---------|------|
| **RH.1 指令违背** | 明确忽视或未执行查询中的低级/步骤特定指令 | HalluClear |
| **RH.2 上下文不一致** | 动作历史与推理矛盾、推理与最终动作矛盾 | HalluClear, AndroTMem |
| **RH.3 逻辑缺陷** | 推理过程中因果链断裂、内部逻辑不自洽 | HalluClear |
| **RH.4 事实捏造** | 缺乏外部知识而捏造日期、人名等事实型信息 | HalluClear, RoTS |

> **关键差异**：RH 类错误不依赖视觉输入，纯推理层问题。上下文不一致（RH.2）在长链路任务中尤为严重，是导致重复动作和循环的深层原因。

#### 执行阶段 Execution（6 类）

| 子类型 | 具体表现 | 在 RoTS 中的频次 | 来源 |
|--------|---------|----------------|------|
| **错误 UI 元素交互** | 与语义相似但错误的 UI 元素交互 | **644/1500（最高频）** | RoTS #1 |
| **Grounding 坐标偏差** | 正确识别目标但点击坐标不精确 | — | RoTS #2, Localization Biases |
| **无效操作** | 执行的操作未使 UI 状态发生变化 | 68/1500 | RoTS #3, Agent+P |
| **输入错误** | 文本输入内容错误，常伴随定位错误 | — | RoTS #4 |
| **错误工具使用** | 使用无效/不支持的键盘快捷键或命令 | 50/1500 | RoTS #6 |
| **错误参数/操作目标** | 操作了错误的文件/单元格/参数值 | — | RoTS #7, #8 |

> **关键洞察**："错误 UI 元素交互"（Incorrect UI Element）是**最高频的执行错误**（644/1500），即 Agent 知道要做什么、也成功执行了交互，但选错了元素。这与纯粹的 grounding 坐标偏差性质不同，后者是"认对了但点不准"。

#### 规划/终止阶段 Planning（4 类）

| 子类型 | 具体表现 | 恢复成功率 | 来源 |
|--------|---------|-----------|------|
| **遗漏必要步骤** | 跳过关键操作如未点击"保存"、未粘贴 | 28.6% | RoTS #5 |
| **误解任务目标** | 从根本上误解用户目标，追求不相关子目标 | **16.7%（极低）** | RoTS #9 |
| **未能终止** | 目标已达成时未能意识到并停止 | **11.1%（最低）** | RoTS #10 |
| **Synthesis Collapse** | 已检索到证据，但最终合成阶段失败 | — | Parallel WebBench |

> **关键发现**：规划/终止阶段的错误是**最难恢复的**。"未能终止"的恢复成功率仅 11.1%——这意味着一旦 Agent 进入无限执行状态，现有方法几乎无法纠正。这正是循环跳转问题的规划层根因。

---

### 2.2 维度二：时序异常模式（Temporal 水平维度）

时序维度关注的是**错误在时间轴上的演化模式**，四种模式之间存在传递关系：循环→重复→累积→提前终止/彻底失败。

#### ⚡ 循环跳转（Search Loop）

**定义**：Agent 在有限个页面/状态间反复跳转而无法突破搜索空间。

**成因分析**：
- 缺乏对全局 UI Transition 结构的理解（Agent+P 的核心问题）
- 被局部语义相似元素反复误导
- 规划层的"未能终止"错误在时序上的体现
- 环境配置变化显著影响 looping 频率（OpenApps 量化）

**量化数据**：
- OpenApps 发现同一 Agent 在不同 App 版本间 looping 行为波动超过 50%（Kimi-VL-3B: 63% → 4%）
- Parallel WebBench 将 context-bound search loops 列为三大 persistent failure modes 之首

**缓解方案**：
- UI Transition Graph (UTG) + Symbolic Planning → 减少 37.7% action steps（Agent+P）
- 记忆机制避免重复访问相同路径（EchoTrail-GUI）
- Hierarchical reflection 多时间尺度监控（MobileUse）

---

#### 🔄 重复动作（Repeated Actions）

**定义**：Agent "忘记"已执行过的操作，对同一目标重复执行相同或等效动作。

**成因分析**：
- **"数字健忘症" (Digital Amnesia)**：每次任务独立处理，缺乏跨步骤的经验记忆（EchoTrail-GUI 的核心概念）
- 上下文不一致（RH.2）导致 Agent 无法正确追踪已完成的操作
- 长链路任务中 context window 截断导致历史信息丢失

**量化数据**：
- AndroTMem 对 1,069 tasks (avg 32.1 steps) 分析发现：随交互序列增长，**性能下降主因是 within-task memory failures（而非感知或动作错误）**

**缓解方案**：
- Critic-Guided Memory 构建成功轨迹数据库（EchoTrail-GUI, CVPR'26）
- Anchored State Memory → TCR 提升 5%-30.16%（AndroTMem）
- Hierarchical Reflection → Reflection-on-demand（MobileUse）

---

#### ⏹ 提前终止（Premature Termination）

**定义**：Agent 在收集到部分答案后即声称任务完成，存在字段缺失、依赖过期证据或答案不完整。

**关键现象——Completion-Correctness Gap**：
- Parallel WebBench 中最佳 GRPO 模型 completion rate = **96.0%**，但 element-wise F1 = **0.4529**，binary accuracy 更低
- 这意味着 Agent "完成"了任务但答案质量极差

**成因分析**：
- 缺少 completion verification 机制
- 过程知识（Procedure Knowledge）缺失，无法判断"任务到底做完了没"
- synthetic-data GRPO 只能减少 abstention，无法弥合 completion-correctness gap

**缓解方向**：需要 evidence-grounded coverage verification + synthesis diagnostics

---

#### 📈 错误累积（Error Accumulation / Error Cascading）

**定义**：早期微小错误在后续步骤中不断放大，最终将系统状态推入不可恢复区域（irrecoverable regime）。

**典型 Case（D-GARA 的 Perception Drift）**：
```
App Crash（外部中断）
  → Agent 识别崩溃，重新打开 App ✓
  → 返回搜索页面后，错误假设"搜索词仍在搜索栏中" ✗
  → 直接点击搜索按钮（实际栏内是推荐词）
  → 搜索错误内容 → 任务完全失败
```

**成因分析**：
- Hallucination 触发级联失败（HalluClear）
- Imitation learning 中 delayed intervention 导致早期错误积累
- 模型决策过度依赖 prompt 中的历史动作，而非当前视觉状态

**量化数据**：
- RoTS 分析显示，错误发生步骤距终止越远 (d=0→d=5)，恢复成功率越高；越靠近终止的错误越难恢复
- AgentCPM 在 crash 类异常中 RSR 急剧下降

**缓解方案**：
- Speculative Rollback Correction (SRC)：branch-level imitation，固定窗口分支审查
- HalluClear ensemble credibility estimation：在 hallucination 传播前拦截
- InfiGUI-R1 Error Recovery Scenario Construction：专门训练恢复能力

---

### 2.3 维度三：环境诱导异常（Environment-Induced）

真实部署环境中，外部因素会打断 Agent 的正常执行流，导致一系列次生异常。

#### 分类体系（基于 D-GARA, AAAI 2026）

| 类别 | 具体异常 | 占比 | 特点 |
|------|---------|------|------|
| **System Network** | Wi-Fi 断开、移动数据切换 | 42.8% | 最高频，模拟现实网络波动 |
| **System Resource** | 低电量警告、过热/温度限制 | 28.3% | 系统资源弹窗覆盖目标 UI |
| **UX Disruption** | 更新提示、评分/反馈请求 | 10.5% | 非关键但易干扰 Agent |
| **Permission Control** | 运行时权限对话框（位置、相机等） | 9.2% | 常识可解决，但 Agent 需要识别 |
| **App Malfunction** | App Crash、App Freeze | 9.2% | 最难恢复，可引发 Perception Drift |

#### 关键发现：单按钮 vs 双按钮（D-GARA）

```
双按钮中断（可选择"关闭"跳过）：
  AgentCPM RSR = 82.35%  ← Agent 能绕过

单按钮中断（只能走复杂处理路径）：
  AgentCPM RSR = 9.30%   ← 暴跌 73 个百分点
```

**核心结论**：当前 SOTA GUI Agent 大多靠"跳过中断"来应付环境异常，**缺乏真正处理复杂中断路径的能力**。一旦无法回避，性能急剧恶化。

#### 环境漂移（Version Drift）

OpenApps（Meta FAIR）发现：
- 同一 App 不同版本间 UI 布局变化 → 旧 grounding 坐标完全失效
- **Kimi-VL-3B**: 不同版本成功率从 63% 跌至 4%（跌幅 59 个百分点）
- **根本原因**：Agent 的 grounding 能力绑定了特定版本的视觉特征，不具备版本无关性

#### Visual Atomicity 假设失效（Zero-Permission Manipulation）

Android 中一个被广泛忽视的问题：**UI 状态在 observation 和 action 之间可能发生变化**（visual atomicity 假设不成立）。
- Agent 基于旧截图做出决策，但执行时 UI 已更新
- 导致 grounding 错误和意外操作
- 既是安全问题，也是系统性异常来源

---

### 2.4 维度四：能力缺口（Knowledge & Capability Gaps）

异常行为的**根因层**：Agent 缺乏某些基础能力，导致系统性的特定类型错误。

#### GUI Knowledge Bench 的三维知识分解

| 知识维度 | 缺失表现 | 导致的异常类型 |
|---------|---------|--------------|
| **Interface Knowledge** | 不理解 widget 功能语义、布局层级、系统状态指示器 | 元素属性误识别、错误 UI 元素交互（最高频，644/1500） |
| **Interaction Knowledge** | 不清楚交互操作的效果和适用范围（长按 vs 短按、拖拽方向） | 无效操作（68/1500）、错误工具使用（50/1500） |
| **Procedure Knowledge** | 缺乏对任务 workflow 和进度的感知能力 | 遗漏步骤（67/1500）、提前终止、未能终止（13/1500） |

补充第四类：

| 知识维度 | 缺失表现 | 导致的异常类型 |
|---------|---------|--------------|
| **World Knowledge** | 缺乏领域/外部事实知识 | 事实捏造（RH.4）、误解任务目标（23/1500） |

#### Grounding 能力特化分析

Localization Biases 论文将定位预测分为 4 种类型，量化揭示：
- 去除 XML 坐标辅助后，Gemini 成功率下降约 **35%**
- 说明 **Agent 知道该做什么，但无法从纯视觉推断精确坐标**
- Peak Sharpness Score (PSS) 可量化定位不确定性：低 PSS → 高错误风险

---

## 3. 核心数据与量化基准

### 3.1 错误类型分布（RoTS，1,500 errors）

| 排名 | 错误类型 | 数量 | 占比 | 恢复成功率 |
|------|---------|------|------|-----------|
| 1 | Incorrect UI Element Interaction | 644 | 42.9% | — |
| 2 | Ineffective Action | 68 | 4.5% | — |
| 3 | Miss Necessary Step | 67 | 4.5% | 28.6% |
| 4 | Incorrect Tool Usage | 50 | 3.3% | — |
| 5 | Misunderstand Objective | 23 | 1.5% | **16.7%** |
| 6 | Fail to Terminate | 13 | 0.9% | **11.1%** |
| — | Lack of Knowledge | 31 | 2.1% | — |

> RoTS-32B SOTA: OSWorld 47.4% success rate

### 3.2 环境异常对性能的影响（D-GARA）

| 模型 | 无中断 SR | 有中断 SR | RSR | 下降幅度 |
|------|---------|---------|-----|---------|
| Gemini2.5-flash | 80.26% | 68.42% | 73.77% | -11.84% |
| GPT-4o | 69.08% | 60.53% | 66.67% | -8.55% |
| Qwen2.5-VL-7B | 69.08% | 46.05% | 53.33% | -23.03% |
| UI-TARS-1.5-72B | 50.66% | 39.47% | 48.05% | -11.19% |
| AgentCPM-GUI-8B | 59.87% | 26.97% | 39.56% | **-32.90%** |

**结论**：所有模型在有中断条件下成功率平均下降超过 **17.5%**。专门为 GUI 交互训练的模型（AgentCPM、UI-TARS）在鲁棒性上反而表现更差，说明其 UI 感知训练未覆盖异常场景。

### 3.3 Memory 机制对长链路任务的提升（AndroTMem）

- Anchored State Memory (ASM) vs full-sequence replay：TCR 提升 **5%-30.16%**，AMS 提升 **4.93%-24.66%**
- 跨 12 个 GUI Agent 评估一致有效

### 3.4 Error Recovery 能力现状（GUI-RobustEval）

- 1,216 个可执行 recovery test cases
- **规划层错误（误解目标、未能终止）恢复成功率 < 20%**
- 执行层错误（grounding、错误元素）相对较易恢复（恢复率 40-60%）
- 合成数据（RoTS pipeline）可显著提升 recovery 能力

---

## 4. 关键研究方向与代表论文

### 4.1 系统性 Error Taxonomy

**代表论文**: [RoTS] *Recovering Policy-Induced Errors* (ICML 2026 Spotlight)
**ArXiv**: 2605.29447 · 阿里巴巴

**核心贡献**：
1. **GUI-RobustEval**: 1,216 可执行测试用例，全面覆盖真实错误模式
2. **Error Taxonomy**: 11 类错误类型，含频次统计和恢复难度评级
3. **RoTS Pipeline**: tree-based 主动误差发现 + recovery trajectory 合成，生成 800K 训练数据
4. SOTA: RoTS-32B 在 OSWorld 达 47.4% success rate

**方法亮点**：
区别于被动收集失败轨迹，RoTS **主动构造**错误场景——通过在正确轨迹上注入错误、展开搜索树，发现多样化的 error modes，进而合成对应的 recovery steps。

---

**代表论文**: *When Web Agents Finish but Still Fail* (2026)
**ArXiv**: 2606.20724

**核心贡献**：
- **Parallel WebBench**: 1,679 records，直接揭示 completion-correctness gap
- 三种 persistent failure modes 的可复现 trigger 机制
- GRPO 训练可减少 abstention，但无法弥合 correctness gap

---

### 4.2 Hallucination 诊断与消除

**代表论文**: [HalluClear] *Diagnosing, Evaluating and Mitigating Hallucinations in GUI Agents*
**ArXiv**: 2604.17284

**GUI-specific Hallucination Taxonomy**（区别于通用 VLM hallucination）：
- 感知层（PH.1-4）：截图状态、元素存在性、属性、关系
- 推理层（RH.1-4）：指令、上下文、逻辑、事实

**方法**：
- Ensemble credibility estimation
- 三阶段评估工作流
- 闭环结构化推理（仅 9K 样本 post-training）

**影响**：Ungrounded hallucinations → cascading failures。可用 9K 样本的轻量 post-training 缓解，成本可接受。

---

**代表论文**: *GUI Knowledge Bench* (2026)
**ArXiv**: 2510.26098

**核心发现**：VLM 在三类 GUI 知识上均存在系统性缺陷，且缺陷会直接导致对应类型的异常行为。6 平台、292 应用的广泛评估证明这是**跨平台的普遍问题**。

---

### 4.3 Error Recovery 与 Self-Reflection

**代表论文**: [GUI-Reflection] *Empowering Multimodal GUI Models with Self-Reflection Behavior*
**ArXiv**: 2506.08012 · NTU

**核心问题**：现有 GUI 模型基于近乎无错的离线轨迹训练 → 没有见过错误 → 不会从错误中恢复

**解决方案**：
```
Stage 1: GUI-specific Pre-training（建立 GUI 基础感知）
Stage 2: Offline SFT（在成功轨迹上微调）
Stage 3: Online Reflection Tuning（在线迭代，主动生成和学习恢复策略）
```
**关键**：全自动化数据生成管线，无需人工标注

---

**代表论文**: [InfiGUI-R1] *From Reactive Actors to Deliberative Reasoners*
**ArXiv**: 2504.14239

**核心创新**：Error Recovery Scenario Construction
- 识别历史轨迹中的"易出错步骤"
- 在该步骤注入错误，构造 failure-and-recovery 训练场景
- Sub-goal Guidance 奖励精确中间状态预测

**范式转变**：从被动响应（Reactive Actor）→ 主动推理（Deliberative Reasoner）

---

**代表论文**: [MobileUse] *Hierarchical Reflection for Autonomous Mobile Operation*
**ArXiv**: 2507.16853

**分层反思架构**：

```
Level 3: Task-level（整体任务是否完成？是否需要重新规划？）
Level 2: Subtask-level（当前子目标是否达成？）
Level 1: Action-level（单步动作是否有效？UI 是否有预期变化？）
```

**Reflection-on-demand**：仅在检测到异常信号时触发反思，避免过度反思导致效率损失

**SOTA**: AndroidWorld 62.9%, AndroidLab 44.2%

---

### 4.4 记忆机制与长链路问题

**代表论文**: [EchoTrail-GUI] *Building Actionable Memory via Critic-Guided Self-Exploration* (CVPR 2026)
**ArXiv**: 2512.19396

**问题定义**："数字健忘症"——每次任务独立处理，重复犯同样的错误

**三阶段框架**：
```
Phase 1: Experience Exploration
  → Agent 自主探索 GUI 环境
  → Reward Model 验证，构建成功轨迹数据库

Phase 2: Memory Injection
  → 新任务到来时，检索最相关的历史轨迹
  → 作为 in-context "memories"

Phase 3: GUI Task Inference
  → Memory 注入为 in-context guidance
  → 指导推理和决策
```

---

**代表论文**: [AndroTMem] *Anchored Memory in Long-Horizon GUI Agents*
**ArXiv**: 2603.18429

**关键诊断**：长链路任务性能下降的**主因是任务内记忆失败**，而非感知错误或动作错误

**Anchored State Memory (ASM)**：
- 将交互序列表示为**因果关联的中间状态锚点集合**（非全序列回放，非摘要）
- 支持子目标靶向检索和归因决策

---

### 4.5 真实环境鲁棒性

**代表论文**: [D-GARA] *Dynamic Benchmarking for GUI Agent Robustness* (AAAI 2026)
**ArXiv**: 2511.16590

**贡献**：首个系统性评估 GUI Agent 在真实世界异常下鲁棒性的动态 benchmark

---

**代表论文**: [OpenApps] *Simulating Environment Variations to Measure UI-Agent Reliability* (Meta FAIR)
**ArXiv**: 2511.20766

**核心发现**：
- Looping 和 hallucinating actions 在不同环境配置下差异**超过 50%**
- 这意味着 Agent 的异常行为具有**强环境依赖性**，不能脱离环境评估

---

**代表论文**: [Speculative Rollback Correction]
**ArXiv**: 2606.12485

**核心问题**：Imitation learning 中传统"出错后纠正"策略存在 delayed intervention 问题——等到明显失败时，错误已经累积到不可恢复

**SRC 方案**：Branch-level imitation，以固定窗口对分支进行持续审查，在错误传播前进行 rollback

---

## 5. 跨维度交叉分析

四个维度并非独立，典型的严重异常往往是多维度交叉叠加的结果：

### 5.1 最危险的交叉路径

```
感知错误（Dim1-感知）
    ↓ 幻觉元素存在
推理错误（Dim1-推理）
    ↓ 基于错误感知做出错误规划
重复动作（Dim2）
    ↓ 反复尝试不存在的元素
错误累积（Dim2）
    ↓ 页面状态被推入异常路径
循环跳转（Dim2）
    ↓ 无法突破，任务失败
```

**严重程度**：致命级 ⚠️
**典型案例**：HalluClear 的 PH.2 引发的级联失败

---

### 5.2 环境诱导的规划崩溃

```
App Crash（Dim3-环境）
    ↓ Perception Drift
感知状态错误（Dim1-感知）
    ↓ 误以为历史操作仍有效
推理错误（Dim1-推理）
    ↓ 基于错误历史做决策
错误累积（Dim2）
    ↓ 无法恢复
任务失败
```

**严重程度**：严重级 ⚠️
**典型案例**：D-GARA 的 Perception Drift case

---

### 5.3 知识缺失→循环探索

```
过程知识缺失（Dim4）
    ↓ 不知道任务完成标准
提前终止 or 循环（Dim2）
    ↓ 要么错误声称完成，要么无目的循环

界面知识缺失（Dim4）
    ↓ 不认识 widget 类型 → 用错交互方式
无效操作（Dim1-执行）
    ↓ 操作反复无效
循环跳转（Dim2）
```

**严重程度**：中等级，但频发

---

## 6. 缺口与机遇（Research Gaps）

### 6.1 已基本解决 ✅

| 问题 | 解决方案 | 残余局限 |
|------|---------|---------|
| GUI Agent 的系统性 Error Taxonomy | RoTS, HalluClear | 覆盖还不够全面 |
| Memory 机制减少重复错误 | EchoTrail-GUI, AndroTMem | 离线记忆，实时更新能力弱 |
| Self-Reflection 数据生成 | GUI-Reflection | 数据质量 vs 多样性 trade-off |
| 真实异常 Benchmark | D-GARA | 覆盖异常类型还有限 |

### 6.2 部分解决，仍有大量空间 🔄

| 问题 | 当前进展 | Gap |
|------|---------|-----|
| Error Recovery（规划层） | InfiGUI-R1, GUI-Reflection | 规划层恢复率仍 <20% |
| 循环跳转的主动预防 | Agent+P (UTG) | 需要事先构建 UTG，不适合动态应用 |
| Grounding 能力 | Localization Biases (PSS) | 视觉坐标预测仍高度依赖 XML 辅助 |
| Completion Verification | Parallel WebBench 指出问题 | 尚无有效解决方案 |

### 6.3 几乎未被研究 ❌

| 未解决问题 | 说明 |
|-----------|------|
| **异常case的在线实时检测** | 现有方案都是 offline 分析，缺乏实时异常检测器 |
| **GUI Agent 专属异常综述** | 该细分方向无专门综述，知识散落在各方法论文中 |
| **跨平台异常一致性** | 不同平台（Web/Android/Desktop）的异常模式是否共享？ |
| **版本无关的 Grounding** | App 版本漂移导致的 grounding 失效尚无鲁棒解法 |
| **Synthesis Collapse 的主动预防** | Parallel WebBench 发现了问题，但无缓解方案 |
| **多 Agent 系统中的异常传播** | 单 Agent 的异常如何在 multi-agent 系统中级联 |

---

## 7. 推荐阅读路径

### 路径 A：快速建立全局认知（3 篇）

1. **GUI Agents: A Survey** (2412.13501, ACL'25) — 整体框架
2. **Recovering Policy-Induced Errors** (2605.29447, ICML'26) — Error taxonomy 核心
3. **HalluClear** (2604.17284) — Hallucination 专题

### 路径 B：深入 Error Recovery（4 篇）

1. **GUI-Reflection** (2506.08012) — 自动化 reflection 数据生成
2. **InfiGUI-R1** (2504.14239) — Error recovery scenario 构造
3. **MobileUse** (2507.16853) — 分层反思架构（SOTA）
4. **Speculative Rollback Correction** (2606.12485) — 错误累积的 rollback 方案

### 路径 C：深入记忆机制（2 篇）

1. **EchoTrail-GUI** (2512.19396, CVPR'26) — Critic-guided memory
2. **AndroTMem** (2603.18429) — 因果关联锚点记忆

### 路径 D：深入鲁棒性评估（3 篇）

1. **D-GARA** (2511.16590, AAAI'26) — 真实异常 benchmark
2. **OpenApps** (2511.20766, Meta FAIR) — 环境漂移量化
3. **When Web Agents Finish but Still Fail** (2606.20724) — Completion-correctness gap

---

## 8. 论文速查表

| # | 论文简称 | ArXiv ID | 会议/年份 | 核心贡献 |
|---|---------|---------|----------|---------|
| 1 | RoTS | [2605.29447](https://arxiv.org/abs/2605.29447) | ICML 2026 Spotlight | Error taxonomy + 800K 恢复数据 + SOTA |
| 2 | Parallel WebBench | [2606.20724](https://arxiv.org/abs/2606.20724) | 2026 | 三种 persistent failure modes，completion-correctness gap |
| 3 | EchoTrail-GUI | [2512.19396](https://arxiv.org/abs/2512.19396) | CVPR 2026 | Critic-guided 记忆机制，消除重复错误 |
| 4 | OpenApps | [2511.20766](https://arxiv.org/abs/2511.20766) | Meta FAIR 2025 | 环境变化 → looping 波动 >50% |
| 5 | HalluClear | [2604.17284](https://arxiv.org/abs/2604.17284) | 2026 | GUI hallucination 8 类 taxonomy + 9K 样本 mitigation |
| 6 | GUI Knowledge Bench | [2510.26098](https://arxiv.org/abs/2510.26098) | 2025 | 三维知识缺口，6 平台 292 应用 |
| 7 | Localization Biases | [2506.15425](https://arxiv.org/abs/2506.15425) | 2025 | PSS 量化定位不确定性，去坐标 -35% |
| 8 | DiagEval | [2605.17439](https://arxiv.org/abs/2605.17439) | 2026 | 轨迹条件化诊断，恢复 45.6%-62.1% 误判 |
| 9 | GUI-Reflection | [2506.08012](https://arxiv.org/abs/2506.08012) | 2025 | 自动化 reflection 三阶段训练 |
| 10 | InfiGUI-R1 | [2504.14239](https://arxiv.org/abs/2504.14239) | 2025 | Error recovery scenario 构造，sub-goal guidance |
| 11 | MobileUse | [2507.16853](https://arxiv.org/abs/2507.16853) | 2025 | 分层反思，AndroidWorld SOTA 62.9% |
| 12 | D-GARA | [2511.16590](https://arxiv.org/abs/2511.16590) | AAAI 2026 | 5 类真实异常，平均下降 17.5%+ |
| 13 | Speculative Rollback | [2606.12485](https://arxiv.org/abs/2606.12485) | 2026 | Branch-level rollback，防止错误累积 |
| 14 | AndroTMem | [2603.18429](https://arxiv.org/abs/2603.18429) | 2026 | 锚点记忆，TCR +5%-30% |
| 15 | Agent+P | [2510.06042](https://arxiv.org/abs/2510.06042) | 2025 | UTG + 符号规划，-37.7% steps |
| 16 | Zero-Permission | [2601.12349](https://arxiv.org/abs/2601.12349) | 2026 | Visual atomicity 假设失效，安全风险 |
| 17 | GUI Agents Survey | [2412.13501](https://arxiv.org/abs/2412.13501) | ACL 2025 | 全面综述，perception/reasoning/planning/acting 框架 |

---

*文档整合自：GUI Agent 异常case 调研报告 + 四维聚类分析 + 综述推荐*
*调研方法：ArXiv API 多轮关键词搜索 + Web 搜索补充 + HTML 全文内容提取*
