# FuncOracleCheck

FuncOracleCheck 是项目内集成的达尔文功能判定能力，用于对 GUI Agent 执行轨迹做单步功能正确性和 E2E 意图达成判定。

## 入口

| 文件 | 用途 |
|------|------|
| `main.py` | FastAPI 服务入口，提供任务队列、上传参数、单步判定和 E2E 判定接口 |
| `oracle_service.py` | 单步/E2E 判定的统一服务封装，供 API 和 CLI 复用 |
| `framework.py` | 本地单样本 CLI 调试入口 |
| `framework_batch_eval.py` | benchmark 批量评估入口 |

## 运行

安装依赖：

```bash
pip install -r requirements.txt
```

启动服务：

```bash
uvicorn main:app --host 0.0.0.0 --port 20025
```

本地单样本调试：

```bash
python framework.py --metadata path/to/metadata.json
python framework.py --data-dir path/to/sample_dir
```

批量评估前修改 `conf/run_benchmark_config.conf`，然后执行：

```bash
python framework_batch_eval.py
```

## E2E 输入与重复动作判定输出

`POST /check_e2e` 的输入是一条实际 Agent 执行轨迹，不需要预置期望坐标。重复动作判定使用实际动作序列、实际点击坐标、截图序列和达尔文 E2E 判定结果。

最小输入格式：

```json
{
  "instruction": "在抖音首页点击视频进入播放页，然后点赞并收藏",
  "step_level_instruction": "点击视频->点击点赞->点击收藏",
  "seq_info": [
    {
      "index": 0,
      "image_relative_path": "<第0张截图base64>",
      "planning_output": {
        "parsed_action": {
          "action_type": "click",
          "start_box": [530, 1200],
          "end_box": [],
          "text": "点击视频",
          "direction": ""
        }
      }
    },
    {
      "index": 1,
      "image_relative_path": "<第1张截图base64>",
      "planning_output": {
        "parsed_action": {
          "action_type": "click",
          "start_box": [995, 1448],
          "end_box": [],
          "text": "点击点赞按钮",
          "direction": ""
        }
      }
    },
    {
      "index": 2,
      "image_relative_path": "<第2张截图base64>",
      "planning_output": {
        "parsed_action": {
          "action_type": "click",
          "start_box": [995, 1448],
          "end_box": [],
          "text": "再次点击点赞按钮",
          "direction": ""
        }
      }
    },
    {
      "index": 3,
      "image_relative_path": "<第3张截图base64>",
      "planning_output": {
        "parsed_action": {
          "action_type": "finished",
          "start_box": [],
          "end_box": [],
          "text": "任务完成",
          "direction": ""
        }
      }
    }
  ]
}
```

字段说明：

| 字段 | 说明 |
|------|------|
| `instruction` | 用户任务意图 |
| `step_level_instruction` | 可选的步骤级计划，用于检查 Plan 覆盖进展 |
| `seq_info[*].image_relative_path` | 生产接口中传 base64 截图；第 `i` 张截图是第 `i` 步动作执行前的页面 |
| `parsed_action.action_type` | 实际动作类型，如 `click`、`type`、`swipe`、`wait`、`finished` |
| `parsed_action.start_box` | Agent 实际执行坐标，不是预期坐标 |
| `parsed_action.text` | Agent 的动作文本或输入文本 |
| `parsed_action.direction` | 滑动/拖拽方向 |

重复动作判定会在达尔文 E2E 判定后追加输出：

```json
{
  "重复动作判定结果": "abnormal",
  "重复动作判定依据": "检测到1段重复动作异常；首段位于步骤1到步骤2，动作为click，目标为点击播放页右侧点赞按钮。",
  "repeated_action_result": {
    "label": "abnormal",
    "type": "repeated_action",
    "severity": "low",
    "confidence": 0.91,
    "ranges": [
      {
        "start_step": 1,
        "end_step": 2,
        "action_type": "click",
        "target": "点击播放页右侧点赞按钮",
        "repeat_type": "repeated_action",
        "evidence": [
          "步骤1和步骤2动作等效",
          "期间无新增检查点达成"
        ]
      }
    ]
  }
}
```

当前重复动作判定是轻量规则实现：连续窗口内动作类型等效、点击坐标或控件语义相似、页面/Plan 无新增进展，且不属于重试、删除、多选等合理重复场景时，判为重复动作异常。

## 模型服务配置

达尔文判定框架通过 OpenAI-compatible `chat/completions` 接口调用 LLM/VLM，配置集中在 `conf/run_server_config.conf` 和 `conf/run_benchmark_config.conf` 的 `[MLLMConfig]`：

```ini
llm_model_name=your-llm-model
llm_model_url=http://host:port/v1/chat/completions
vlm_model_name=your-vlm-model
vlm_model_url=http://host:port/v1/chat/completions
llm_api_key_env=MLOPS_API_KEY
vlm_api_key_env=MLOPS_API_KEY
include_top_k=true
request_timeout=120
```

本地模型可用 `model/inference.py` 启动 vLLM 服务：

```bash
python model/inference.py --serve --host 0.0.0.0 --port 8000 --tp 1
```

如果本地服务不需要鉴权，将 `llm_api_key_env` / `vlm_api_key_env` 置空；如果使用严格 OpenAI API 且不接受 `top_k` 参数，将 `include_top_k=false`。
## 目录说明

| 目录 | 内容 |
|------|------|
| `app/` | FastAPI 请求模型 |
| `oracle/function_oracle/` | 规则式功能 oracle 与队列消费逻辑 |
| `GUI_TestFramework_v1/` | 达尔文 MLLM/VLM 判定框架 |
| `external_apis/` | OCR、目标检测、Jar 解析等外部服务适配 |
| `utils/` | 图像、JSON、布局、存储等通用工具 |
| `conf/` | test/production 与 benchmark 配置 |
