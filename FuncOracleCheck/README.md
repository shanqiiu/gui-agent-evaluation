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
