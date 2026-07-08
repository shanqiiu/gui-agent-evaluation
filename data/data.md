# 数据解析文档：一二方系统自动化测试数据集

---

## 1. 概述

本目录包含自动化测试运行数据，由智能助手驱动执行。

每条数据记录一次完整的自动化任务执行过程，包含：用户指令、AI 思考过程、页面交互操作、屏幕截图、UI 树信息等。

数据集包含 **400 条** 独立的 UUID 任务记录。

---

## 2. 目录结构

```
e63dd288-af51-4147-9ac8-67cf73042651/          ← 根目录（任务批次）
├── .codegraph/                                  ← 内部元数据
│   ├── .gitignore
│   └── codegraph.db
├── <taskId-1>/                                  ← 任务 UUID（如 0072df9f-...）
│   ├── utg.json                                 ← 核心：有向图结构化数据
│   ├── utg.gzip                                 ← utg.json 的 gzip 压缩版本
│   ├── home/                                    ← 起始状态快照
│   │   ├── temp_image-screenshot-origin.jpg
│   │   └── temp_fusion-context.json
│   ├── end/                                     ← 结束状态快照
│   │   ├── temp_image-screenshot-origin.jpg
│   │   └── temp_fusion-context.json
│   ├── catchDataTurnId1/                        ← 交互轮次 1 的截图和上下文
│   │   ├── temp_image-screenshot-origin.jpg     （或 drawRect 版本）
│   │   └── temp_fusion-context.json
│   ├── catchDataTurnId2/
│   ├── catchDataTurnId3/
│   ├── ...
│   ├── catchDataTurnIdN/
│   ├── oriRes.gzip                              ← 原始响应数据（gzip）
│   ├── clearRes.gzip                            ← 清理后的响应数据（gzip）
│   ├── corpusResult.gzip                        ← 语料库结果（gzip）
│   └── phoneLog.gzip                            ← 手机日志（gzip）
├── <taskId-2>/
├── ...
└── <taskId-400>/
```

### 2.1 目录变体

不同任务记录的子目录数量可能略有不同：

| 任务示例       | 包含目录                     | 说明                   |
| -------------- | ---------------------------- | ---------------------- |
| `0072df9f-...` | home + 7 catchDataTurn + end | 完整流程，包含中间状态 |
| `0080571a-...` | home + 6 catchDataTurn + end | 流程较短               |

---

## 3. 核心文件：utg.json

**UTG = UI Task Graph（UI 任务有向图）**

这是唯一结构化的 JSON 文件，是整个数据集的核心。它使用图模型描述从屏幕截图中识别出的 UI 元素之间的状态转移关系。

### 3.1 顶级结构

```
utg.json
├── nodes          ← UI 状态节点列表（数组）
├── stepData       ← 按步骤组织的行为数据（数组）
├── edges          ← 节点间边/转移关系（数组）
├── num_nodes      ← 节点总数
└── num_edges      ← 边总数
```

### 3.2 节点（nodes）结构

每个节点表示一个 UI 状态或交互步骤，包含图片引用和元数据。

```json
{
    "image": "图片路径（本地绝对路径或远程 REST 路径）",
    "node_type": "normal",
    "shape": "image" | "dot" | "star",
    "raw_item": {
        "directives": "指令 JSON 字符串",
        "originalPageInfo": "原始 UI 页面信息 JSON 字符串"
    },
    "id": "home" | 1 | 2 | 3 | ... | "end",
    "label": "home" | "Step1" | "Step2" | ... | "end",
    "title": "嵌套 JSON 字符串（含 instruction, stepId, contexts 等）"
}
```

#### 节点字段说明

| 字段                        | 类型         | 说明                                                         |
| --------------------------- | ------------ | ------------------------------------------------------------ |
| `image`                     | 字符串       | 节点状态的屏幕截图路径。`home` 和 `end` 节点引用初始/最终截图；中间节点引用对应 `catchDataTurnIdX/temp_image-screenshot-*` 的截图 |
| `node_type`                 | `normal`     | 当前固定值                                                   |
| `shape`                     | 字符串       | 节点可视化形状：`image`（截图节点）、`dot`（起始点）、`star`（中间状态） |
| `raw_item.directives`       | JSON 字符串  | 执行该状态的命令指令，格式为 `[{\"payload\":{...}, \"header\":{...}}]` 数组 |
| `raw_item.originalPageInfo` | JSON 字符串  | 该状态下的原始 UI 布局树（View Hierarchy），包含所有可见元素的 `$ID`、`$rect`、`compid`、`text`、`clickable` 等属性 |
| `id`                        | 字符串或数字 | 节点唯一标识。起始节点为 `"home"`，结束节点为 `"end"`，中间步骤为数字编号（1, 2, 3...） |
| `label`                     | 字符串       | 可视化标签，`"home"` / `"end"` 或 `"StepN"` / `"StepN\n<FIRST>"` |
| `title`                     | JSON 字符串  | 包含完整上下文信息的 JSON 字符串，含 `instruction`（用户指令）、`stepId`、`contexts`（系统上下文）、`directives` 等 |

#### 节点类型

```
home  ──→  Step1  ──→  Step2  ──→  ...  ──→  StepN  ──→  end
 (起始)      (思考)       (操作)                 (结果)       (结束)
```

- **home 节点**：系统就绪状态的截图，`directives` 和 `originalPageInfo` 均为空 `{}`
- **Step1 节点**：通常为 `<FIRST>` 标记，AI 助手的初始思考响应
- **Step2 至 StepN-1**：实际交互操作的中间状态，每个节点包含截图和 PageInfo
- **end 节点**：任务结束状态，`directives` 和 `originalPageInfo` 均为空 `{}`

### 3.3 步骤数据（stepData）结构

```json
{
    "stepData": [
        {
            "stepId": "home"
        },
        {
            "action_type": "用户回复(打开密码自动填充和保存功能);",
            "cost_time": "4283",
            "stepId": "1"
        },
        {
            "action_type": "open(\"设置\", restart_app=True)",
            "cost_time": "190",
            "stepId": "5"
        },
        {
            "action_type": "scroll([500, 800], down)",
            "cost_time": "3309",
            "stepId": "6",
            "thought": "【0】",
            "type": "AAS",
            "ui_summary": ""
        },
        {
            "action_type": "click([315, 918])",
            "cost_time": "3619",
            "stepId": "7",
            "thought": "【0】",
            "type": "AAS",
            "ui_summary": ""
        },
        {
            "action_type": "clarify(当前页面需要你手动操作);",
            "cost_time": "702",
            "stepId": "12",
            "thought": "【0】",
            "type": "AAS",
            "ui_summary": ""
        }
    ]
}
```

#### 步骤字段说明

| 字段          | 类型   | 说明                                                         |
| ------------- | ------ | ------------------------------------------------------------ |
| `stepId`      | 字符串 | 与节点的 `id` 对应                                           |
| `action_type` | 字符串 | 该步骤执行的具体操作。格式包括：`用户回复(...)`、`open("应用名")`、`click([x, y])`、`scroll([x1, y1], direction)`、`clarify(...)`、`edit(...)` 等 |
| `cost_time`   | 字符串 | 该步骤耗时（毫秒）                                           |
| `thought`     | 字符串 | AI 思考过程标记，如 `【0】`、`【301】`，数值可能指代某种状态码 |
| `type`        | 字符串 | 当前固定为 `AAS`（Agent Action System？）                    |
| `ui_summary`  | 字符串 | UI 摘要描述，当前均为空                                      |

---

## 4. 图边（edges）结构

```json
{
    "edges": [
        {
            "flag": "new",
            "costTime": "4283ms",
            "from": 1,
            "id": "1_2",
            "to": 2,
            "label": 1,
            "title": "{...}",
            "view_images": ["/rest/.../catchDataTurnId1/..."],
            "events": [
                {
                    "event_id": 1,
                    "event_type": "[{...命令结构}]",
                    "event_str": "打开密码自动填充和保存功能"
                }
            ]
        }
    ]
}
```

#### 边字段说明

| 字段          | 类型        | 说明                                             |
| ------------- | ----------- | ------------------------------------------------ |
| `flag`        | 字符串      | 当前固定为 `new`                                 |
| `costTime`    | 字符串      | 从源节点到目标节点的耗时，格式如 `"4283ms"`      |
| `from`        | 节点 ID     | 起始节点                                         |
| `to`          | 节点 ID     | 目标节点                                         |
| `id`          | 字符串      | 边的唯一标识，格式 `{from}_{to}`                 |
| `label`       | 节点 ID     | 与 `from` 相同                                   |
| `title`       | JSON 字符串 | 包含 `instruction`、`stepId`、`contexts` 的 JSON |
| `view_images` | 字符串数组  | 该转移对应的截图路径                             |
| `events`      | 数组        | 该转移触发的事件列表                             |

#### 事件（events）字段

| 字段         | 类型         | 说明                                                         |
| ------------ | ------------ | ------------------------------------------------------------ |
| `event_id`   | 数字或字符串 | 事件标识                                                     |
| `event_type` | 字符串       | 事件类型 JSON，包含动作详情：<br>- `scroll custom`: `{"id":"[500, 800]", "points":[640.0,2265.0], "type":"scroll custom"}`<br>- `click`: `{"bounds":[255,2541,553,2617], "id":"[315, 918]", "nodeText":"隐私和安全", "points":[403,2599], "type":"click"}`<br>- `clarify`: `{"id":"", "setText":"当前页面需要你手动操作", "type":"clarify"}` |
| `event_str`  | 字符串       | 事件关联的原始指令                                           |

---

## 5. 交互轮次（catchDataTurnId）子目录

每个 `catchDataTurnId{N}` 目录包含该步骤执行后的屏幕截图和上下文数据。

```
catchDataTurnId1/
├── temp_image-screenshot-origin.jpg      ← 原始截图（1280x2832 分辨率）
└── temp_fusion-context.json              ← 融合上下文（当前为空 {}}）
```

### 5.1 截图文件类型

| 文件后缀                             | 说明                          |
| ------------------------------------ | ----------------------------- |
| `temp_image-screenshot-origin.jpg`   | 原始屏幕截图                  |
| `temp_image-screenshot-drawRect.jpg` | 带标注框的截图（UI 元素高亮） |

---

## 6. Gzip 压缩文件

每个任务目录下包含 4 个 `.gzip` 压缩文件：

| 文件名              | 推测含义                             |
| ------------------- | ------------------------------------ |
| `oriRes.gzip`       | 原始响应数据（Original Response）    |
| `clearRes.gzip`     | 清理后的响应数据（Cleaned Response） |
| `corpusResult.gzip` | 语料库结果数据                       |
| `phoneLog.gzip`     | 设备端运行日志                       |

---

## 7. UI 树信息（来自 raw_item.originalPageInfo）

每个节点的 `originalPageInfo` 包含完整的 Android/HarmonyOS 视图层次结构：

```json
{
    "$type": "root",
    "$ID": 0,
    "type": "build-in",
    "$rect": "[0.00, 0.00],[1280.00,2832.00]",
    "$attrs": {},
    "clickable": false,
    "longClickable": false,
    "scrollable": false,
    "editable": false,
    "$children": [
        {
            "$type": "page",
            "$ID": 2,
            "CurrentPageUrl": "pages/home/SettingsHome",
            "$children": [...]
        }
    ]
}
```

### 视图属性

| 属性            | 类型   | 说明                                                         |
| --------------- | ------ | ------------------------------------------------------------ |
| `$type`         | 字符串 | 视图类型：`root`、`page`、`JsView`、`Navigation`、`NavBar`、`TitleBar`、`HdsTitleBar`、`Text`、`Button`、`ListContainer` 等 |
| `$ID`           | 数字   | 视图唯一编号                                                 |
| `$rect`         | 字符串 | 视图边界框，格式 `[x1, y1],[x2, y2]`                         |
| `clickable`     | 布尔值 | 是否可点击                                                   |
| `longClickable` | 布尔值 | 是否可长按                                                   |
| `scrollable`    | 布尔值 | 是否可滚动                                                   |
| `compid`        | 字符串 | 组件 ID（如 `HdsTitleBar`、`SearchSettingsComponent`）       |
| `$attrs`        | 对象   | 视图属性键值对（如字体、颜色等）                             |
| `$children`     | 数组   | 子视图列表（树状结构）                                       |

### 应用信息

```json
{
    "BundleName": "com.huawei.hmos.settings",
    "WindowID": 577,
    "WindowName": "settings0",
    "CurrentPageUrl": "pages/home/SettingsHome",
    "CurrentPageName": ""
}
```

---

## 8. 指令系统（directives）结构

每个节点的 `directives` 字段包含 Jarvis 助手执行的命令：

```json
[
    {
        "header": {
            "namespace": "SimulatingOperation",
            "name": "ExecuteCommand"
        },
        "payload": {
            "jarvisSessionId": "uuid-session-id",
            "actions": [
                {
                    "action": "click",                  // 操作类型: click/scroll/edit/clarify
                    "id": "[315, 918]",                  // 操作坐标
                    "params": {
                        "node": {
                            "confidence": 0.95,          // 元素识别置信度
                            "bounds": [255,2541,553,2617], // 元素边界框
                            "id": "2_7_1",               // UI 元素 ID
                            "text": "隐私和安全",           // 元素文本
                            "type": "text",               // 元素类型
                            "actions": [],                 // 元素可执行动作
                            "content": ""
                        },
                        "similarity": 0.2,              // 相似度评分
                        "localSimilarity": 0.5,
                        "enter": true
                    }
                }
            ]
        }
    },
    {
        "header": {
            "namespace": "SimulatingOperation",
            "name": "GetPageInfo"
        },
        "payload": {
            "akRequired": true,
            "instruction": "打开密码自动填充和保存功能",
            "jarvisSessionId": "...",
            "extraInfo": "{\"isSupportLoading\":true}"
        }
    }
]
```

### 指令命名空间

| namespace             | name                         | 说明                               |
| --------------------- | ---------------------------- | ---------------------------------- |
| `SimulatingOperation` | `ExecuteCommand`             | 执行 UI 操作（点击、滑动、输入等） |
| `SimulatingOperation` | `GetPageInfo`                | 获取当前页面信息                   |
| `SimulatingOperation` | `UpdateJarvisTaskState`      | 更新任务状态（思考中、操作中等）   |
| `SimulatingOperation` | `SimulatingOperationContext` | 设置操作上下文                     |
| `SimulatingOperation` | `ThinkModeInfo`              | 思考模式信息                       |
| `Command`             | `CheckAppExist`              | 检查应用是否存在                   |
| `Command`             | `OpenApp`                    | 打开应用                           |
| `UserInteraction`     | `Indication`                 | 用户交互提示                       |
| `System`              | `Application`                | 系统应用信息                       |
| `System`              | `ClientContext`              | 客户端上下文                       |

### 操作类型（action）

```
click   → 点击指定坐标/UI元素
scroll  → 在指定区域滑动（direction: up/down/custom）
edit    → 文本输入（含 clear 清屏、text 输入内容）
clarify → 需要用户手动操作（任务无法自动完成时）
preCheckDone → 预检查完成
```

---

## 9. 系统上下文（contexts）

每个步骤附带系统运行上下文，包含设备状态、应用信息等：

```json
[
    {
        "header": { "name": "Application", "namespace": "System" },
        "payload": {
            "plugins": [],
            "apps": [
                {
                    "name": "智慧语音",
                    "osType": "HarmonyOS",
                    "id": "hwVoiceAssistant",
                    "packageName": "com.huawei.hmos.vassistant",
                    "version": "11.6.4.902"
                }
            ]
        }
    },
    {
        "header": { "name": "System", "namespace": "System" },
        "payload": {
            "isChildAccount": false,
            "odid": "835b4777-...",       // 设备标识
            "deepThinkMode": false,
            "isSmartCall": true,
            "screenMode": {
                "isSplit": false,
                "screenOrientation": "vertical",
                "innerScreen": true,
                "screenNum": 1
            },
            "userCharacteristics": true,
            "isSupportAgent": true,
            ...
        }
    }
]
```

### 关键上下文字段

| 字段                | 类型   | 说明                                               |
| ------------------- | ------ | -------------------------------------------------- |
| `odid`              | 字符串 | 设备唯一标识（Open Device ID）                     |
| `deepThinkMode`     | 布尔值 | 深度思考模式是否启用                               |
| `screenOrientation` | 字符串 | 屏幕方向（vertical）                               |
| `isChildAccount`    | 布尔值 | 是否为儿童账号                                     |
| `isSupportAgent`    | 布尔值 | 是否支持智能助手                                   |
| `exeStatus`         | 数字   | 执行状态码（0=成功, 301=需滚动, 315=需人工干预等） |
| `ucsAk`             | 字符串 | 用户认证密钥                                       |

---

## 10. 典型任务流程图

以任务 `0072df9f-...` 为例：

```
用户指令: "打开密码自动填充和保存功能"

Step1  [思考中]          4283ms
  ↓
Step2  [AI 处理指令]     4345ms
  ↓
Step3  [正在操作设置]      4347ms
  ↓
Step4  [检查设置应用]      4395ms  CheckAppExist
  ↓
Step5  [打开设置]          190ms   OpenApp
  ↓
Step6  [向下滚动屏幕]      3309ms  click([403, 2579])
  ↓
Step7  [点击"隐私和安全"]  3619ms  click
  ↓
Step8  [向下滚动]          3813ms  scroll
  ↓
Step9  [向下滚动]          3445ms  scroll (exeStatus: 301)
  ↓
Step10 [向下滚动]          3616ms  scroll
  ↓
Step11 [点击"密码保险箱"]  4232ms  click
  ↓
Step12 [需要手动操作]       702ms  clarify
  ↓
end  [任务结束]
```

**结论**：该任务未能完全自动完成，AI 在最后一步触发了 `clarify` 动作（"当前页面需要你手动操作"），说明密码保险箱页面可能需要额外的生物识别或密码验证。

---

## 11. 数据来源与系统架构

| 组件       | 标识                                                |
| ---------- | --------------------------------------------------- |
| 操作系统   | HarmonyOS                                           |
| 智能助手   | Jarvis / 小艺（包名：`com.huawei.hmos.vassistant`） |
| 目标应用   | 设置（包名：`com.huawei.hmos.settings`）            |
| 设备分辨率 | 1280 × 2832 像素                                    |
| 会话标识   | `jarvisSessionId`（每条任务独立 UUID）              |
| 任务状态机 | `SimulatingOperation` 命名空间驱动                  |

### 任务指令示例

数据集中包含多类针对「设置」应用的自动化测试指令：

- "打开密码自动填充和保存功能"
- "把定时开关机状态设置成每周重复"
- "禁止华为账号指纹验证"

---

## 12. 解析工具建议

### 读取 utg.json

```python
import json

with open('utg.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# 获取节点
nodes = data['nodes']
for node in nodes:
    print(f"Node {node['id']}: {node['label']} (shape={node['shape']})")
    
    # 解析嵌套的 JSON 字符串
    title = json.loads(node['title'])
    print(f"  Instruction: {title.get('instruction', '')}")
    
    # 解析 directives
    if node['raw_item']['directives'] != '{}':
        directives = json.loads(node['raw_item']['directives'])
        for d in directives:
            print(f"  Command: {d['header']['namespace']}/{d['header']['name']}")

# 获取步骤数据
for step in data['stepData']:
    print(f"Step {step['stepId']}: {step['action_type']} ({step['cost_time']}ms)")

# 获取边信息
for edge in data['edges']:
    print(f"{edge['from']} -> {edge['to']}: {edge['costTime']}")
    for event in edge['events']:
        print(f"  Event: {event['event_type']}")
```

### 解压 gzip 文件

```python
import gzip
import json

# 解压 oriRes.gzip
with gzip.open('oriRes.gzip', 'rt', encoding='utf-8') as f:
    original_res = json.load(f)
```

### 解析 action_type

```python
import re

def parse_action(action_type: str):
    """解析 action_type 提取操作类型和参数"""
    # 匹配 click、scroll、open、clarify、edit 等操作
    click_match = re.match(r'click\((\[.*?\])\)', action_type)
    scroll_match = re.match(r'scroll\((\[.*?\]),\s*(\w+)\)', action_type)
    open_match = re.match(r'open\("([^"]+)"', action_type)
    clarify_match = re.match(r'clarify\("([^"]+)"\)', action_type)
    edit_match = re.match(r'edit\((\[.*?\])', action_type)
    
    if click_match:
        return {'type': 'click', 'coords': click_match.group(1)}
    if scroll_match:
        return {'type': 'scroll', 'coords': scroll_match.group(1), 'dir': scroll_match.group(2)}
    if open_match:
        return {'type': 'open_app', 'app': open_match.group(1)}
    if clarify_match:
        return {'type': 'clarify', 'message': clarify_match.group(1)}
    if edit_match:
        return {'type': 'edit', 'coords': edit_match.group(1)}
    return {'type': 'unknown', 'raw': action_type}
```

---

## 13. 字段速查表

| 文件     | 字段                        | 类型          | 必选 | 说明             |
| -------- | --------------------------- | ------------- | ---- | ---------------- |
| utg.json | `nodes`                     | array         | ✅    | 节点列表         |
| utg.json | `stepData`                  | array         | ✅    | 步骤数据         |
| utg.json | `edges`                     | array         | ✅    | 图的边           |
| utg.json | `num_nodes`                 | number        | ✅    | 节点数           |
| utg.json | `num_edges`                 | number        | ✅    | 边数             |
| node     | `id`                        | string/number | ✅    | 节点标识         |
| node     | `label`                     | string        | ✅    | 显示标签         |
| node     | `image`                     | string        | ✅    | 截图路径         |
| node     | `shape`                     | string        | ✅    | 可视化形状       |
| node     | `title`                     | string(JSON)  | ✅    | 完整 JSON 字符串 |
| node     | `raw_item.directives`       | string(JSON)  | ✅    | 指令             |
| node     | `raw_item.originalPageInfo` | string(JSON)  | ✅    | UI 树            |
| stepData | `stepId`                    | string        | ✅    | 步骤编号         |
| stepData | `action_type`               | string        | ✅    | 操作类型         |
| stepData | `cost_time`                 | string        | ✅    | 耗时(ms)         |
| stepData | `thought`                   | string        | ❌    | AI 思考标记      |
| stepData | `type`                      | string        | ❌    | 固定 "AAS"       |
| edge     | `from`                      | mixed         | ✅    | 源节点           |
| edge     | `to`                        | mixed         | ✅    | 目标节点         |
| edge     | `costTime`                  | string        | ✅    | 转移耗时         |
| edge     | `events[]`                  | array         | ✅    | 事件列表         |
| event    | `event_type`                | string(JSON)  | ✅    | 事件详情         |
| event    | `event_str`                 | string        | ✅    | 原始指令         |

---

## 附录 A：任务状态码

| 状态码 | 说明             |
| ------ | ---------------- |
| 0      | 执行成功         |
| 301    | 需要滚动屏幕     |
| 315    | 需要用户手动干预 |

## 附录 B：截图分辨率

统一为 **1280 × 2832 像素**（HarmonyOS 设备默认分辨率）。

## 附录 C：文件编码

所有 JSON 文件使用 **UTF-8** 编码。

---

## 附录 D：/check_e2e 格式转换

`convert_to_check_e2e.py` 将 utg.json 数据转换为 FuncOracleCheck 的 `/check_e2e` 判定接口所需格式，打通"Agent 原始执行数据 → 异常判定"的完整链路。

### 转换映射

| utg.json 来源 | /check_e2e 字段 | 说明 |
|---|---|---|
| `nodes[].title.instruction` 或 `edges[].title.instruction` | `instruction` | 用户任务意图 |
| 从 `node.raw_item.directives` 提取的动作描述，去重拼接 | `step_level_instruction` | 用 `->` 连接，do-nothing 不参与，同名步骤加序号 |
| `node.raw_item.directives` JSON 解析 | `parsed_action.action_type` | `edit`→`type`, `preCheckDone`→`do-nothing`, `scroll custom`→`scroll` |
| `params.points` / `node.bounds` 中心 | `parsed_action.start_box` / `end_box` | 优先取实际触点坐标 |
| `params.node.text` / `params.node.content` | `parsed_action.text` / `content` | 元素文本和输入内容 |
| `stepData.action_type` 正则解析 | `parsed_action.direction` | 仅提取方向（directives 中无此信息） |
| `node.image` REST URL → 本地文件 | `image_relative_path` | 发送时 `hydrate_payload` 转为 base64 |
| `node.image` REST URL | `_image_source` | 完整 URL，用于溯源 |

### 使用方式

```bash
# 单个原始任务目录 → payload JSON
python data/convert_to_check_e2e.py <task_uuid_dir>/ -o payload.json

# 直接发送到 /check_e2e 服务获取判定结果
python data/convert_to_check_e2e.py <task_uuid_dir>/ --send http://localhost:20025

# 批量转换（支持断点续跑：已存在的 payload 自动跳过）
python data/convert_to_check_e2e.py --batch reorg_output/ --processed -o payloads/

# 批量 + 发送 + 保存结果
python data/convert_to_check_e2e.py --batch reorg_output/ --processed --send http://localhost:20025

# 已保存的 payload 重发
python data/send_payload.py payloads/ --send http://localhost:20025

# 验证核心逻辑
python data/test_convert_to_check_e2e.py
```

### 过滤规则

- 只保留 `node.raw_item.directives` 非空的步骤（无 directives 的为思考/反射节点）
- 不做过多的主观过滤——`open`、`clarify`、`do-nothing` 等均保留在轨迹中
- 最后一步自动追加 `action_type: "finished"`（不参与 action_count 计数）

### 截图三级兜底

1. 用当前步骤对应节点的 `node.image` URL → 解析本地文件
2. 文件不存在 → 用前一步成功加载的截图（`last_loaded` 追踪）
3. 仍为空 → `image_relative_path = ""`
