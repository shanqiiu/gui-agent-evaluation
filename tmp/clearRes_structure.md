# clearRes.json 结构解析文档

> **文件位置**: `1b3c9d23-8b45-4c9b-8034-9c36b35aa1df/clearRes.json`
>
> **来源**:  语音助手对话管理系统的原始响应数据。
>
> **格式**: JSON (另存有 `clearRes.gzip` 压缩版本，18,496 行)
>
> **对应任务**: 用户指令 "到淘宝再来一单芝华仕3m多的真皮沙发"

---

## 1. 顶层结构

```json
{
  "responses": [...],   // 系统处理过程中逐条记录的响应结果（21 条）
  "requests": [...]     // 与 responses 一一对应的请求数据（21 条）
}
```

`responses` 和 `requests` 数量相同（各 21 条），下标一一对应，表示同一轮交互中的请求/响应。

| 字段        | 类型       | 说明                                                         |
| ----------- | ---------- | ------------------------------------------------------------ |
| `responses` | Response[] | 对话管理系统 (DM) 处理该轮交互后逐条输出的响应。每条代表系统在任务推进过程中的一个状态快照。 |
| `requests`  | Request[]  | 发送给 DM 的原始请求数据，包含设备上下文、环境信息、ASR 文本等。 |

---

## 2. Response 结构

每条 `Response` 表示一次系统输出，记录了从意图识别到动作执行的完整生命周期。

```
Response {
  // === 流程状态标记 ===
  isReactFinish          boolean
  triggerRedLine         boolean
  isFinished             boolean | undefined
  isDialogFinished       boolean | undefined
  isFinal                boolean | undefined
  isReactTask            boolean
  hasPartialResult       boolean
  isIgnoreDialogState    boolean
  isContainsDialogFinishDirective boolean
  isWriteToClient        boolean

  // === 指令 ===
  directives             Directive[]
  directiveInfo          DirectiveInfo
  remoteDirectives       Directive[]  // 远程下发的指令

  // === 会话信息 ===
  session                Session

  // === 业务属性 ===
  isSkillHosting         boolean
  errorCode              string
  errorMsg               string

  // === 上下文 ===
  contexts               Context[]

  // === 调试信息 ===
  debugInfo              DebugInfo

  // === 时间戳 ===
  record_time            number | undefined
}
```

### 2.1 流程状态标记

| 字段                              | 类型                | 说明                                                         |
| --------------------------------- | ------------------- | ------------------------------------------------------------ |
| `isReactFinish`                   | boolean             | React 前端渲染是否完成                                       |
| `triggerRedLine`                  | boolean             | 是否触发红线（安全/合规拦截）                                |
| `isFinished`                      | boolean / undefined | 该轮响应是否已结束。**首次响应为 `false`，后续执行阶段为 `undefined`** |
| `isDialogFinished`                | boolean / undefined | 对话是否已结束。意图识别阶段为 `true`，执行阶段为 `false`    |
| `isFinal`                         | boolean / undefined | 是否为最终响应                                               |
| `isReactTask`                     | boolean             | 是否为 React 任务                                            |
| `hasPartialResult`                | boolean             | 是否有部分结果                                               |
| `isIgnoreDialogState`             | boolean             | 是否忽略对话状态                                             |
| `isContainsDialogFinishDirective` | boolean             | 是否包含对话结束指令                                         |
| `isWriteToClient`                 | boolean             | 是否写入客户端                                               |
| `errorCode`                       | string              | 错误码，`"0"` 表示成功                                       |
| `errorMsg`                        | string              | 错误信息                                                     |
| `record_time`                     | number / undefined  | 记录时间戳（毫秒级 Unix 时间戳）。最后一个 response 为 `undefined` |

### 2.2 directives — 指令

表示系统在该响应中下发的一条指令。每条指令由 `header`（命名空间+名称）和 `payload`（载荷）组成。

```
Directive {
  header    { namespace: string, name: string }
  payload   object                    // 结构随 name 变化
}
```

#### 2.2.1 指令类型一览

| namespace             | name                         | 触发时机             | 关键 payload 字段                                            |
| --------------------- | ---------------------------- | -------------------- | ------------------------------------------------------------ |
| `SimulatingOperation` | `UpdateJarvisTaskState`      | 任务状态变更时       | `state` (枚举状态码), `text` (用户可见文本)                  |
| `SimulatingOperation` | `SimulatingOperationContext` | 模拟操作开始前       | `turnId`, `interactionId`, `actionId`, `sessionId`, `intent`, `status` (`"start"`) |
| `SimulatingOperation` | `GetPageInfo`                | 获取当前页面信息     | `packageName`, `jarvisSessionId`, `instruction`, `useVirtualScreen`, `preloadTime`, `akRequired`, `isSupportLoading`, `extraInfo` |
| `SimulatingOperation` | `ExecuteCommand`             | 执行具体操作         | 包含操作执行结果                                             |
| `SimulatingOperation` | `ThinkModeInfo`              | 处于思考模式时       | `actionPurpose` (操作目的), `uiSummary` (UI 摘要)            |
| `Command`             | `CheckAppExist`              | 检查目标应用是否存在 | `appName` (应用名称), `packageName` (包名)                   |
| `Command`             | `OpenApp`                    | 打开目标应用         | `appName`, `packageName`, `isNeedKeepAlive`, `useVirtualScreen`, `responses` (TTS 反馈), `isAppOperation`, `isNeedResume` |
| `UserInteraction`     | `Indication`                 | 用户交互提示         | `isInterrupt`, `interruptWaitTime`                           |

#### 2.2.2 任务状态 (`state`) 枚举

| 值                  | text           | 含义                 |
| ------------------- | -------------- | -------------------- |
| `STATE_THINKING`    | "思考中"       | 系统正在理解用户指令 |
| `STATE_OPERATE_APP` | "正在使用淘宝" | 系统正在操作目标应用 |

#### 2.2.3 `Command/OpenApp` 的 `responses` 结构

```json
{
  "responses": [{
    "commandUserInteractionSpeak": {
      "speakTextId": "brieftts_syscommon_success",
      "text": "好的。"
    },
    "commandUserInteractionDisplayText": {
      "displayTextId": "brieftts_syscommon_success",
      "text": "好的。"
    },
    "displayText": "",
    "ttsText": "",
    "resultCode": "0"
  }]
}
```

### 2.3 directiveInfo

```
DirectiveInfo {
  controlPolicy    string              // 控制策略（空字符串）
  directivePolicy  string              // 指令策略：固定为 "ClearSetAndExecute"
}
```

### 2.4 session — 会话信息

表示当前对话的会话上下文。

```
Session {
  messageName              string       // "dialogResult"
  audioStreamId            string       // 音频流 UUID
  dialogPageId             string       // 对话框页面 ID
  isNewFlow                boolean      // 是否为新流程
  interactionId            number       // 交互 ID（当前为 2）
  agentId                  string       // Agent 标识（skill 托管 ID）
  originRequestType        string       // 原始请求类型："text"
  receiver                 string       // 接收者包名 "com.huawei.hmos.vassistant"
  isExperiencePlan         boolean      // 是否为经验计划
  fullDuplexMode           boolean      // 是否全双工模式
  messageId                string       // 消息 UUID
  sessionId                string       // 会话 UUID
  dialogId                 number       // 对话 ID
  deviceId                 string       // 设备 UUID
  vtId                     string       // 语音技术 ID
  isOmt                    boolean      // 是否 OMT 标记
  sender                   string       // "DM" (Dialogue Manager)
  appId                    string       // 应用 ID
  ignoreVerify             boolean      // 是否跳过验证
  durations                Duration[]   // 各 hop 耗时
  retryId                  string       // 重试 ID
  resultSourceType         number       // 结果源类型
  devF                     string       // 设备标识（脱敏，如 "030**bca21"）
}
```

#### 2.4.1 Duration — 各处理阶段耗时

```
Duration {
  duration     number        // 耗时（毫秒）
  hop          string        // 处理阶段/跳点
  startDuration? number      // 起始时间戳（仅在最后一项出现）
  endDuration? number        // 结束时间戳（仅与 startDuration 同时出现）
}
```

| hop                                                 | 含义             |
| --------------------------------------------------- | ---------------- |
| `dm/skillSearchSelector`                            | 技能搜索选择器   |
| `T301` / `T302`                                     | 内部处理阶段编号 |
| `dm/moderation`                                     | 内容审核         |
| `dm/decision`                                       | 决策             |
| `dm/llm/firstResult/APP_OPERATION/AAS_STREAM_QUEUE` | LLM 首 Token     |
| `dm/llm/e2e/APP_OPERATION/AAS_STREAM_QUEUE`         | LLM 端到端       |
| `dm/e2e`                                            | 端到端总耗时     |

### 2.5 contexts — 上下文数据

每条 Response 包含多个 Context，每个 Context 有 `header`（标识来源）和 `payload`（内容）。

#### 2.5.1 Context 类型一览

| namespace              | name            | 说明                 |
| ---------------------- | --------------- | -------------------- |
| `Statistics`           | `Slotinfo`      | Slot 填充统计        |
| `DialogInfo`           | `NLPRecognizer` | NLP 识别结果（核心） |
| `DialogInfo`           | `DialogStatus`  | 对话状态             |
| `InformationRetrieval` | `RetrievalInfo` | 信息检索信息         |

#### 2.5.2 Statistics/Slotinfo

| 字段                | 类型     | 说明                   |
| ------------------- | -------- | ---------------------- |
| `missingSlots`      | string[] | 缺失的.slot 名称列表   |
| `necessarySlotsNum` | number   | 必要 slot 数量         |
| `filledSlots`       | string[] | 已填充的 slot 名称列表 |
| `priority`          | (null    | string)[]              |

#### 2.5.3 DialogInfo/NLPRecognizer — NLP 识别结果

这是 Response 中最核心的上下文数据。

```
NLPRecognizer {
  intentName              string             // 意图名称："APP_OPERATION"
  finalNluResult          NLUResult           // NLU 最终结果
  intentId                string              // 意图 ID (2001100311000000)
  nluIntentName           string              // NLU 意图名称
  asrText                 string              // ASR 识别文本（用户语音转文字）
  subDomainName           string              // 子域名称："System tools"
  domainId                string              // 域 ID ("2001")
  businessInfo            object              // 业务信息
  reference               string              // 引用信息
  nluIntentId             string              // NLU 意图 ID
  slots                   Slot[]              // 槽位列表
  subDomainId             string              // 子域 ID ("20011004")
  domainName              string              // 域名称："System builtIn"
  selectableResponses     string[]            // 可选响应
}
```

##### 2.5.3.1 NLUResult

```
NLUResult {
  intentions              Intention[]          // 识别到的意图列表
  domainInfo              DomainInfo           // 领域信息
}
```

##### 2.5.3.2 Intention

```
Intention {
  domainInfo             { domainId: string, subDomainId: string }
  intentName             string               // "APP_OPERATION"
  confidence             number               // 置信度 (0.999999)
  groupId                number               // 意图组 ID
  intentId               string               // 意图 ID
  decisionPriority       string               // 决策优先级 ("high")
  nluProvider            string               // NLU 提供者 ("LLM")
  fullSceneIntentPriority string              // 全场景优先级 ("high")
  taskType               string               // 任务类型 ("NEW")
  slots                  Slot[]               // 意图级 slot（嵌套结构）
  provider               string               // "HW"
  action                 Action               // 动作信息
  timestamp              number               // 时间戳
  ...                  (其他布尔标记字段)
}
```

##### 2.5.3.3 Slot (意图级)

意图下的 slot 采用嵌套结构：

```
Slot {
  useReferenceSlots    ReferenceSlot[]  // 引用槽位
  query                QuerySlot[]       // 查询槽位
}
```

| 字段        | 类型      | 说明                                      |
| ----------- | --------- | ----------------------------------------- |
| `type`      | string    | slot 类型 ("query" / "useReferenceSlots") |
| `origValue` | string    | 原始值                                    |
| `value`     | SlotValue | 解析后的值                                |

##### 2.5.3.4 SlotValue

| 字段          | 类型    | 说明                                              |
| ------------- | ------- | ------------------------------------------------- |
| `charOffset`  | number  | 字符偏移量                                        |
| `sequence`    | number  | 序列号                                            |
| `indict`      | boolean | 是否有效判定                                      |
| `isInference` | boolean | 是否为推理值                                      |
| `nature`      | string  | 性质 ("-1")                                       |
| `oriText`     | string  | 原始文本（可能为占位符如 `${outputs_utterance}`） |
| `isCorrected` | boolean | 是否经过纠错                                      |
| `normalValue` | string  | **归一化值**（最终使用的文本）                    |
| `user.extend` | boolean | 用户扩展标记                                      |

##### 2.5.3.5 Slot (NLPRecognizer 级)

NLPRecognizer 下的 slot 采用平铺结构：

| 字段            | 类型        | 说明                                      |
| --------------- | ----------- | ----------------------------------------- |
| `name`          | string      | slot 名称 ("useReferenceSlots" / "query") |
| `dataType`      | string      | 数据类型                                  |
| `isPositive`    | boolean     | 是否为正值                                |
| `isSlotPron`    | boolean     | 是否为槽位 pronounce                      |
| `origPronounce` | string[]    | 原始发音                                  |
| `sources`       | string[]    | 来源                                      |
| `origValue`     | string[]    | 原始值数组                                |
| `value`         | SlotValue[] | 值数组                                    |
| `isLastOne`     | boolean     | 是否为最后一个 slot                       |
| `extendValue`   | object      | 扩展值                                    |

##### 2.5.3.6 Action

```
Action {
  actionName              string              // "APP_OPERATION"
  oriActionName           string              // "AppOperation"
  actionId                number              // 动作 ID (1)
  state                   string              // "ON_GOING"
  type                    string              // "Action"
  taskTurn                string              // "turn1.task1"
  taskType                string              // "NEW"
  provider                string              // "LLM"
  inputs                  ActionInput[]       // 输入参数
  groupId                 number              // 1
  flowId                  number              // 1
  isFinalAction           boolean             // false
  streamAction            boolean             // false
  isNeedMultiAction       boolean             // false
  needCheck               boolean             // false
  isPlanFirstAction       boolean             // false
  isIgnoreContextUpdate   boolean             // false
  isFunctionExec          boolean             // false
  needModeration          boolean             // false
  isTransparent           boolean             // false
  isQuickSystemConvert    boolean             // false
}
```

#### 2.5.4 DialogInfo/DialogStatus — 对话状态

| 字段             | 类型     | 说明                                                    |
| ---------------- | -------- | ------------------------------------------------------- |
| `isChangeDomain` | boolean  | 是否切换领域                                            |
| `isLastTurn`     | boolean  | 是否为最后一轮（意图识别时为 `true`，执行时为 `false`） |
| `businessType`   | string   | 业务类型："HalfScreen"（半屏模式）                      |
| `flowStatus`     | string   | 流程状态 ("1")                                          |
| `modeStates`     | object[] | 模式状态列表                                            |
| `llmInfo`        | LLMInfo  | LLM 相关信息                                            |

##### 2.5.4.1 LLMInfo

| 字段                       | 类型     | 说明                     |
| -------------------------- | -------- | ------------------------ |
| `fusionLlmTokensIn`        | number   | LLM 输入 token 数        |
| `fusionLlmTokensOut`       | number   | LLM 输出 token 数        |
| `moderationSource`         | string   | 审核来源 ("sensitive")   |
| `moderationSecurityResult` | string   | 安全结果："ACCEPT"       |
| `moderationLabels`         | string   | 审核标签                 |
| `moderationSubLabels`      | string   | 子标签                   |
| `moderationDecisionSource` | string[] | 决策来源列表             |
| `pluginLlmTokensInTotal`   | number   | 插件 LLM 输入 token 总数 |
| `pluginLlmTokensOutTotal`  | number   | 插件 LLM 输出 token 总数 |
| `recordType`               | number   | 记录类型                 |

#### 2.5.5 InformationRetrieval/RetrievalInfo — 信息检索

| 字段              | 类型   | 说明                             |
| ----------------- | ------ | -------------------------------- |
| `searchRouteType` | string | 搜索路由类型（通常为 `"empty"`） |

### 2.6 debugInfo — 调试信息

记录了 NLU 链路和 Agent 推理的完整调试信息。

```
DebugInfo {
  // === 流程追踪 ===
  beforeConvertFlows          Flow[]        // 转换前流程
  afterConvertFlows           Flow[]        // 转换后流程
  
  // === 决策列表 ===
  beforeDecisionDomainList    DomainDecision[]  // 决策前的领域候选
  afterDecisionDomainList     DomainDecision[]  // 决策后的领域列表
  
  // === NLU 调试 ===
  nluDebugs                   object[]      // NLU 调试信息
  chatNluDebugs               object[]      // 聊天 NLU 调试
  visionResults               object[]      // 视觉识别结果
  visualDebugInfo             object        // 视觉调试
  searchgateDebugInfo         object        // 搜索门控调试
  wiseCenterDebugs            object[]      // WiseCenter 调试
  knowledgeDebugInfo          object        // 知识调试
  
  // === 候选信息 ===
  candidateActions            object        // 候选动作
  candidateAgents             object        // 候选 Agent
  candidateIntentLabels       object        // 候选意图标签
  
  // === 元数据 ===
  isChatMode                  boolean       // 是否聊天模式
  conversationRound           number        // 对话轮次
  skillCostTime               number        // 技能耗时 (ms)
  skillRound                  number        // 技能轮次
  rewriteText                 string        // 文本重写
  memoryMessage               object        // 记忆消息
  
  // === Agent 推理 ===
  appOperationDebugInfo       AppOperationDebugInfo | undefined  // 存在时包含详细推理
  
  // === 审核 ===
  openDomainDialogInfo        string[]      // 开放域审核信息（JSON 字符串数组）
}
```

#### 2.6.1 Flow — 流程定义

```
Flow {
  flowIndex    number         // 流程索引 (1)
  actions      Action[]       // 动作列表（结构与 NLPRecognizer 中的 action 一致）
}
```

#### 2.6.2 DomainDecision — 领域决策

```
DomainDecision {
  intentName              string          // "APP_OPERATION"
  intentId                string          // "2001100311000000"
  groupId                 number          // 1
  intentPriority          number          // 16
  decisionPriority        string          // "high"
  skillId                 string          // "huawei.app.operation.agent"
  taskType                string          // "NEW"
  isDomainMatch           boolean         // 是否匹配领域（after 阶段无此字段）
  isDelegating            boolean         // 是否委托
  precision               string          // "0.999999"
  fullSceneIntentPriority string          // "high"
  ...
}
```

#### 2.6.3 AppOperationDebugInfo — App 操作详细调试信息

仅在包含 `Command`/`SimulatingOperation/ExecuteCommand` 指令的 Response 中出现，**包含了 LLM Agent 的完整推理链**。

| 字段                      | 类型     | 说明                                                         |
| ------------------------- | -------- | ------------------------------------------------------------ |
| `agentId`                 | string   | Agent 标识                                                   |
| `action`                  | string   | **执行的动作**，如 `"open(淘宝)"`, `"click([897, 937])"`, `"drag([141, 611], [920, 611])"`, `"back()"`, `"do_nothing()"` |
| `actionPurpose`           | string   | **动作目的**（人类可读文本），如 `"打开淘宝"`, `"点击'我的淘宝'进入个人中心"` |
| `instruction`             | string   | 用户原始指令                                                 |
| `formal_instruction`      | string   | 形式化指令（LLM 生成）                                       |
| `difficulty`              | string   | 难度评估：`"easy"` / `"medium"` / `"hard"`                   |
| `thought`                 | string   | Agent 思考标记（通常为 `【0】`）                             |
| `modelInput`              | string   | **发送给 LLM 的完整 prompt**。包含 Role、设备上下文、知识库、用户画像、决策逻辑等 |
| `modelOutput`             | string   | **LLM 的完整输出**。包含 `<think>...</think>` 思考过程和 `<action>...</action>` `<difficulty>...</difficulty>` `<formal_instruction>...</formal_instruction>` |
| `targetAppName`           | string   | 目标应用名称                                                 |
| `packageName`             | string   | 包名                                                         |
| `appVersion`              | string   | 应用版本                                                     |
| `versionName`             | string   | 版本名                                                       |
| `timeCost`                | string   | 执行耗时（"13012" 表示 13012ms）                             |
| `exeStatus`               | number   | 执行状态码（`0` = 成功）                                     |
| `aasErrorMsg`             | string   | Agent 错误信息（空表示无错误）                               |
| `errorDebugInfo`          | object   | 错误调试：`{ errorCode, errorMsg }`                          |
| `type`                    | string   | 类型："AAS"                                                  |
| `history`                 | string   | 任务历史记录（如 `"[Task_1 Begin, Instruction: ...]"`）      |
| `aasTimeCost`             | object   | 时间成本：`{ receiveAasTime, requestAasTime }`               |
| `aamStatistics`           | object   | 统计信息：`{ llmRmTime7B, searchSkill1stTime, experienceRetrievalDuration, similarityResult }` |
| `baseExtraInfo`           | object   | 基础额外信息：`{ callerSource, intent }`                     |
| `uploadImageUrl`          | string   | 上传图像 URL                                                 |
| `uploadImageId`           | string   | 上传图像 ID                                                  |
| `uploadRawPage`           | string   | 原始页面上传                                                 |
| `imageId`                 | string   | 图像 ID                                                      |
| `imageSource`             | string   | 图像来源                                                     |
| `imageDownloadUrl`        | string   | 图像下载 URL                                                 |
| `rawPage`                 | string   | 原始页面（双转义 JSON 字符串，内容为 JSON 数组，数组第一个元素为页面 UI 树） |
| `page`                    | string   | 页面                                                         |
| `choices`                 | object[] | 选择项                                                       |
| `turnId`                  | number   | 轮次 ID                                                      |
| `interactionId`           | number   | 交互 ID                                                      |
| `stepId`                  | string   | 步骤 ID                                                      |
| `groupId`                 | number   | 组 ID                                                        |
| `sessionId`               | string   | 会话 ID                                                      |
| `deviceId`                | string   | 设备 ID                                                      |
| `userIntervention`        | boolean  | 是否有用户干预                                               |
| `userResponse`            | string   | 用户回复                                                     |
| `userInterventionActions` | object[] | 用户干预动作列表                                             |
| `ruleId`                  | string   | 规则 ID                                                      |
| `planSource`              | string   | 计划来源                                                     |
| `teachType`               | string   | 教学类型                                                     |
| `completeTime`            | string   | 完成时间                                                     |
| `rmScores`                | object[] | RM 评分                                                      |
| `uiSummary`               | string   | UI 摘要                                                      |
| `memory`                  | string   | 用户记忆                                                     |
| `originalName`            | string   | 原始名称                                                     |

##### 2.6.3.3 rawPage — 标签-坐标映射（页面 UI 控件树）

`rawPage` 是页面 UI 控件的完整树描述，存储为**双转义的 JSON 字符串`**。解析后是一个 JSON 数组，数组第一个元素为页面根节点。这是文件中**唯一包含控件名与坐标映射关系的来源**——LLM Agent 根据此结构理解页面布局、定位控件文本标签、并据此选择点击坐标。

**解析流程**：

```
rawPage (双转义 JSON 字符串)
  → JSON.parse() → JSON 数组
  → 取数组第一个元素 → 页面根节点 {width, height, nodes}
  → 遍历 nodes → 读取 text + bounds → 标签-坐标映射
```

###### 根节点字段

| 字段     | 类型   | 说明                            |
| -------- | ------ | ------------------------------- |
| `width`  | number | 屏幕宽度（px），此任务中为 1216 |
| `height` | number | 屏幕高度（px），此任务中为 2688 |
| `nodes`  | Node[] | 顶层控件列表（通常 5-11 个）    |

###### 页面控件节点 (Node)

| 字段         | 类型     | 说明                                                         |
| ------------ | -------- | ------------------------------------------------------------ |
| `type`       | string   | 节点类型：`layout` / `text` / `icon` / `relativeitem` / `listview` |
| `oriType`    | string   | 原始类型：`tabbar`（底部导航栏）、`listview`（列表）、`relativeitem`（相对布局）等 |
| `bounds`     | number[] | 控件边界框 `[x1,y1,x2,y2]`，基于 1216x2688 屏幕              |
| `text`       | string   | 控件的**标签文本**（用于 Agent 语义匹配如"我的淘宝"）        |
| `content`    | string   | 控件内容的额外描述                                           |
| `id`         | string   | 控件唯一标识 ID                                              |
| `confidence` | string   | 文本识别置信度                                               |
| `subNodes`   | Node[]   | 子控件节点列表                                               |
| `actions`    | object[] | 可执行的动作列表                                             |
| `frame`      | object   | 绝对定位时的框架信息                                         |

**坐标计算**：Agent 执行的 `click([x,y])` 基于 `bounds` 中心点：

```
center_x = round((bounds[0] + bounds[2]) / 2)
center_y = round((bounds[1] + bounds[3]) / 2)
```

**标签-坐标映射示例（Response 7 "我的淘宝" 页面顶部操作区）：**

| 控件标签   | oriType        | bounds                 | 说明                   |
| ---------- | -------------- | ---------------------- | ---------------------- |
| "全"       | `relativeitem` | `[19, 308, 1191, 799]` | 全部入口               |
| "部"       | `relativeitem` | `[19, 308, 1191, 799]` | 全部入口（子节点文本） |
| "全部"     | `relativeitem` | `[19, 308, 1191, 799]` | 全部订单按钮           |
| "我的订单" | `relativeitem` | `[19, 308, 1191, 799]` | 订单区域标题           |

**标签-坐标映射示例（Response 9 "订单搜索"页面商品条目）：**

| 控件标签                     | oriType        | bounds                  | 说明                        |
| ---------------------------- | -------------- | ----------------------- | --------------------------- |
| "芝华仕 真皮沙发"            | `relativeitem` | `[164, 120, 941, 241]`  | 商品名称（第一个匹配项）    |
| "管理"                       | `relativeitem` | `[978, 119, 1074, 239]` | 订单管理按钮                |
| "天猫芝华仕敏华专卖店"       | `listview`     | `[0, 249, 1215, 1671]`  | 店铺名称                    |
| "【优惠价】芝华仕大黑牛真皮" | `listview`     | `[0, 249, 1215, 1671]`  | 商品描述                    |
| "¥5078.46"                   | `listview`     | `[0, 249, 1215, 1671]`  | 价格                        |
| "删除订单"                   | `listview`     | `[0, 249, 1215, 1671]`  | 删除按钮                    |
| "加入购物车"                 | `listview`     | `[0, 249, 1215, 1671]`  | 加购按钮 ← Agent 点击的条目 |

**验证码页面标注（Response 11 滑块验证）：**

| 控件标签                           | oriType        | bounds                   | 说明           |
| ---------------------------------- | -------------- | ------------------------ | -------------- |
| "亲，请按照说明进行验证哦"         | `text`         | `[307, 625, 910, 693]`   | 验证码提示标题 |
| "拖动滑块出现完整的一个树后就松开" | `relativeitem` | `[70, 820, 1150, 1709]`  | 滑块区域       |
| "请按照说明拖动滑块"               | `relativeitem` | `[70, 820, 1150, 1709]`  | 操作指引       |
| "点我反馈"                         | `relativeitem` | `[469, 1842, 751, 2169]` | 反馈按钮       |


##### 2.6.3.2 modelOutput 结构

```xml
<think>
<!-- Agent 思考过程 -->
1. 意图确认：用户想在淘宝再次购买...
2. 约束推导：
   - 目标 App：淘宝
   - 商品关键词：芝华仕 3m 真皮沙发
   - 操作：再来一单（复购）
3. 信息缺口：...
4. 现有规则/经验：...
5. 方案决策：...
</think>
<action>
open("淘宝", restart_app=True)
</action>
<difficulty>
easy
</difficulty>
<formal_instruction>
在淘宝中再来一单芝华仕3m多的真皮沙发
</formal_instruction>
```

##### 2.6.3.3 modelInput 结构

完整的 LLM prompt，包含以下部分：

| 部分                  | 说明                                                   |
| --------------------- | ------------------------------------------------------ |
| Role                  | Agent 角色定义（"小艺帮帮忙"）                         |
| Input Data Definition | 输入数据分类（设备上下文、知识库、用户画像、用户交互） |
| Decision Logic        | 决策逻辑（意图增强、任务规划、APP执行）                |
| Device & Context      | 当前应用、已安装应用、位置、时间                       |
| Knowledge Base        | 工具列表、规则、经验                                   |
| User Memory           | 用户资料和记忆                                         |
| History               | 历史交互记录                                           |
| Skills                | 可用技能                                               |
| Rules                 | 适用规则                                               |

#### 2.6.4 openDomainDialogInfo — 开放域审核

JSON 字符串数组，每条包含内容安全审核结果：

```json
{
  "header": { "namespace": "OpenDomainDialog", "name": "moderation" },
  "payload": {
    "retCode": "0",
    "retMsg": "Success",
    "data": {
      "securityResult": "ACCEPT",
      "labels": [],
      "confidences": [],
      "subLabels": [],
      "audits": [],
      "forbidDuration": 0,
      "violationCount": 0,
      "triggerRedLine": false,
      "timeout": false,
      "moderationRoute": "empty"
    },
    "textSource": "sensitive",
    "textStatus": "complete"
  }
}
```

---

## 3. Request 结构

`Request` 是发送给 Dialogue Manager 的请求数据。

```
Request {
  session     Session              // 会话上下文（结构与 Response 中的 session 类似）
  contexts    Context[]            // 上下文（与 Response 中的 contexts 不同）
  record_time number               // 记录时间戳
  events      Event[]              // 系统事件
}
```

### 3.1 session（Request 中的版本）

与 Response 中的 session 相比，Request 的 session 多了一些设备相关字段、少了 `durations`、`retryId`、`resultSourceType`、`ignoreVerify` 等字段：

| 字段             | 类型   | 说明                     |
| ---------------- | ------ | ------------------------ |
| `deviceCategory` | string | 设备类别                 |
| `deviceModel`    | string | 设备型号                 |
| 其余字段         | -      | 与 Response session 相同 |

### 3.2 contexts（Request 中的版本）

Request 的 contexts 包含了更多系统级上下文信息：

| namespace             | name                         | 出现时机  | 说明           |
| --------------------- | ---------------------------- | --------- | -------------- |
| `System`              | `Application`                | 所有请求  | 当前应用信息   |
| `System`              | `ClientContext`              | 所有请求  | 客户端上下文   |
| `System`              | `SupportedLanguages`         | 请求 0-3  | 支持语言列表   |
| `System`              | `PermissionsList`            | 请求 0-3  | 权限列表       |
| `TextRecognizer`      | `AsrRecognize`               | 请求 0-3  | ASR 识别结果   |
| `System`              | `AppInfo`                    | 请求 4    | 应用信息       |
| `SimulatingOperation` | `PageInfo`                   | 请求 5-19 | 页面信息       |
| `SimulatingOperation` | `SimulatingOperationContext` | 请求 5-19 | 模拟操作上下文 |
| `SimulatingOperation` | `Termination`                | 请求 20   | 终止标记       |

### 3.3 events — 系统事件

每个 Request 包含 6 个系统事件：

| namespace | name             | 说明     | 关键字段                                                     |
| --------- | ---------------- | -------- | ------------------------------------------------------------ |
| `System`  | `Device`         | 设备信息 | `deviceType` (CLS-AL00), `osType` (OpenHarmony), `deviceBrand` (HUAWEI), `marketingName` (HUAWEI Mate 70), `sysVersion` (OpenHarmony-6.1.1.120), `romVersion` |
| `System`  | `DateAndTime`    | 日期时间 | 当前日期时间信息                                             |
| `System`  | `Language`       | 系统语言 | 当前语言设置                                                 |
| `System`  | `OsLanguage`     | OS 语言  | 操作系统语言                                                 |
| `System`  | `HomeCountry`    | 归属国家 | 归属国家/地区                                                |
| `System`  | `RoamingCountry` | 漫游国家 | 漫游国家/地区                                                |

---

## 4. 时序与生命周期

```
请求到达 DM
    │
    ▼
Response 0: 意图识别 + 审核通过         record_time ≈ 1779621323119
    ├── [状态] STATE_THINKING (思考中)
    ├── [NLPRecognizer] APP_OPERATION intent (置信度 0.999999)
    └── [DialogStatus] isLastTurn=true, dialogFinished=true
    │
    ▼
Response 1: SimulatingOperationContext  start
    └── turnId=1, actionId=1, status="start"
    │
    ▼
Response 2: 任务状态更新
    └── [状态] STATE_OPERATE_APP (正在使用淘宝)
    │
    ▼
Response 3: 检查App + 执行open
    ├── [Command] CheckAppExist(淘宝)
    └── [动作] open(淘宝)  [timeCost: 13012ms]
        ├── 包含完整 modelInput（LLM prompt）
        └── 包含完整 modelOutput（LLM 推理链）
    │
    ▼
Response 4: 打开应用
    ├── [UserInteraction] Indication
    ├── [Command] OpenApp(淘宝)
    ├── [Think] ThinkModeInfo
    └── [GetPageInfo] 获取淘宝页面
    │
    ▼
Response 5: click([897, 937]) "我的淘宝"     [timeCost: 8450ms]
    ▼
Response 6: click([897, 935]) "我的淘宝"     [timeCost: 8428ms]
         （重复点击，坐标有偏移）
    ▼
Response 7: click([900, 326]) "全部"         [timeCost: 8640ms]
    ▼
Response 8: set_text("芝华仕 真皮沙发")      [timeCost: 9345ms]
         （在搜索订单框中输入，去掉了"3m多的"）
    ▼
Response 9: click([854, 315]) 加购           [timeCost: 10540ms]
    ▼
Response 10: do_nothing() 等验证码           [timeCost: 9452ms]
    ▼
Response 11: drag(滑动验证 第一次)           [timeCost: 9060ms] 失败
    ▼
Response 12: do_nothing() 等刷新            [timeCost: 8954ms]
    ▼
Response 13: drag(滑动验证 第二次)           [timeCost: 9950ms] 失败
    ▼
Response 14: drag(滑动验证 第三次)           [timeCost: 11193ms] 失败
    ▼
Response 15-16: do_nothing() × 2            等待响应
    ▼
Response 17: click(刷新验证码)              [timeCost: 23179ms]
    ▼
Response 18: back() 返回                    [timeCost: 8737ms]
    ▼
Response 19: do_nothing() 等提示消失        [timeCost: 9624ms]
    ▼
Response 20: (空记录)                        任务中断
```

---

## 5. 关键常量与硬编码值

| 常数值                                                       | 出现位置                        | 含义                  |
| ------------------------------------------------------------ | ------------------------------- | --------------------- |
| `"ClearSetAndExecute"`                                       | `directiveInfo.directivePolicy` | 指令策略              |
| `"2001100311000000"`                                         | `intentId`, `nluIntentId`       | APP_OPERATION 意图 ID |
| `"2001"`                                                     | `domainId`                      | 系统内置域 ID         |
| `"20011004"`                                                 | `subDomainId`                   | 系统工具子域 ID       |
| `"huawei.app.operation.agent"`                               | `skillId`                       | 应用操作 Agent ID     |
| `"HalfScreen"`                                               | `businessType`                  | 半屏业务模式          |
| `"com.huawei.hmos.vassistant"`                               | `receiver`                      | 华为 Jarvis 语音助手  |
| `"skillHosting80ba57ff4a884289aee0c929dfd5dc18"`             | `agentId`                       | 技能托管 Agent ID     |
| `"feb57f94-ddce-4936-a615-a6a536adb588skillHosting80ba57ff4a884289"` | `appId`                         | 应用 ID               |
| `0.999999`                                                   | `confidence`, `precision`       | NLU 置信度            |
| `{"duration": 45, "hop": "dm/skillSearchSelector"}`          | `session.durations`             | 技能搜索选择器耗时    |
| `{"duration": 217, "hop": "T301"}`                           | `session.durations`             | 内部阶段 T301 耗时    |
| `"STATE_THINKING"`                                           | `directives[].payload.state`    | 思考中状态            |
| `"STATE_OPERATE_APP"`                                        | `directives[].payload.state`    | 操作应用中状态        |
| `"ACCEPT"`                                                   | `moderationSecurityResult`      | 审核通过              |

---

## 6. 动作类型分类

文件中共涉及以下操作类型（从 `modelOutput.action` 提取）：

| 类型         | 示例                                     | 含义                     |
| ------------ | ---------------------------------------- | ------------------------ |
| `open`       | `open("淘宝", restart_app=True)`         | 打开应用                 |
| `click`      | `click([897, 937])`                      | 点击指定坐标             |
| `set_text`   | `set_text([287, 70], "芝华仕 真皮沙发")` | 在指定坐标输入文本       |
| `drag`       | `drag([141, 611], [920, 611])`           | 从起始坐标拖动到结束坐标 |
| `back`       | `back()`                                 | 返回上一页               |
| `do_nothing` | `do_nothing()`                           | 等待（无操作）           |

---

## 7. 数据流总结

```
用户语音 → ASR (TextRecognizer/AsrRecognize) → NLU (NLPRecognizer)
    │                                              │
    │                               Intent: APP_OPERATION
    │                               Query: "到淘宝再来一单芝华仕3m多的真皮沙发"
    │                                              │
    ▼                                              ▼
设备上下文                                LLM 决策
(System/Device, DateAndTime, ...)     modelInput (完整 prompt)
权限、语言、国家、时间                     modelOutput (<think>+<action>)
    │                                              │
    └──────────────────────┬───────────────────────┘
                           ▼
                    策略层 (Decision/Convert)
                    beforeDecisionDomainList → afterDecisionDomainList
                    beforeConvertFlows → afterConvertFlows
                           │
                           ▼
                    指令下发
                    │ Command/OpenApp (打开淘宝)
                    │ Command/CheckAppExist (检查淘宝)
                    │ SimulatingOperation/ExecuteCommand (执行操作)
                    │ SimulatingOperation/GetPageInfo (截图/页面)
                           │
                           ▼
                    返回 Response 序列
                    每条包含完整的 context + debug 信息
```
