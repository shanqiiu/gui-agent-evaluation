# 模块 A — 任务分解引擎（LLM + RAG）

基于 LLM + ChromaDB RAG 的任务分解引擎，将自然语言指令分解为结构化检查点列表，供 `convert_to_check_e2e.py` 生成 `step_plan`。

## 快速开始

### 1. 摄入 App 知识

首次使用前，需将 App 操作路径知识摄入 ChromaDB：

```bash
python src/decomposer/knowledge_store.py --ingest src/decomposer/app_knowledge/
```

输出：
```
[OK] settings: 9 段已摄入
共 9 条记录
```

### 2. 启动 LLM 服务

分解器依赖 OpenAI-compatible chat completions API。例如使用 vLLM 启动 Qwen3-8B：

```bash
vllm serve Qwen/Qwen3-8B --port 8000
```

### 3. 测试分解

```bash
LLM_MODEL_URL=http://localhost:8000/v1/chat/completions \
LLM_MODEL_NAME=qwen3-8b \
python src/decomposer/test_decomposer.py
```

### 4. 集成到数据管线

在转换时启用 `--decompose`，自动生成 `step_plan`：

```bash
python data/convert_to_check_e2e.py --batch reorg_output/ \
    --decompose \
    --send http://localhost:20025
```

这会自动：
1. 从 utg.json 提取 instruction（如 "打开密码自动填充和保存功能"）
2. 调用 RAG 检索 settings 知识 → 返回相关页面流
3. 调用 LLM 分解 → 生成结构化检查点 JSON
4. 将检查点拼接为 `step_plan` 字符串
5. 保存到 payload 的 `step_level_instruction` 字段，替代默认的 action description

## API 参考

### Decomposer 类

```python
from decomposer import Decomposer

d = Decomposer(
    model_url="http://localhost:8000/v1/chat/completions",  # OpenAI-compatible API
    model_name="qwen3-8b",                                    # 模型名
    api_key="",                                               # 可选，API Key
    timeout=60,                                               # 请求超时（秒）
)

# 分解指令
checkpoints = d.decompose(
    instruction="打开密码自动填充和保存功能",
    app_name="settings",    # 限定 RAG 检索的 App 知识
    top_k=5,                # RAG 返回的知识片段数
)
```

`decompose()` 返回：

```json
[
  {
    "name": "点击隐私和安全",
    "required": true,
    "preconditions": "已进入设置首页",
    "expected_state": "进入隐私设置页面"
  },
  {
    "name": "点击密码保险箱",
    "required": true,
    "preconditions": "已进入隐私设置页面",
    "expected_state": "进入密码保险箱管理页面"
  },
  ...
]
```

### 便捷函数

```python
from decomposer import init_decomposer, decompose_instruction

# 初始化全局实例
init_decomposer(model_url="...", model_name="qwen3-8b")

# 后续直接调用
checkpoints = decompose_instruction("关闭指关节截屏功能")
```

### knowledge_store 组件

```python
from decomposer import query_knowledge, ingest_documents

# 程序化摄入
ingest_documents("src/decomposer/app_knowledge/")

# 程序化检索
docs = query_knowledge("定时开关机", app_name="settings", top_k=5)
# → ["首页: 搜索栏（顶部）...", "## 定时开关机设置...", ...]
```

## 扩展 App 知识

在 `app_knowledge/` 下新增 `<AppName>.md` 文件，遵循 `settings.md` 的格式：

```markdown
# <AppName> — 页面流与关键元素

## 应用信息
- 包名: com.example.app
- 应用名: 示例应用
- 分辨率: 1280 × 2832

## 主要页面流

### 首页
- 元素A、元素B

### 功能页
- 路径: 首页 → 功能页
- 关键控件描述

## 关键操作模式

### 操作名称
1. 步骤1
2. 步骤2
3. 预期结果
```

新增后需重新摄入：

```bash
python src/decomposer/knowledge_store.py --ingest src/decomposer/app_knowledge/
```

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `LLM_MODEL_URL` | `http://localhost:8000/v1/chat/completions` | LLM API 地址 |
| `LLM_MODEL_NAME` | `qwen3-8b` | 模型名称 |
| `LLM_API_KEY` | （空） | API Key（可选） |
| `RAG_PERSIST_DIR` | `src/decomposer/chroma_db/` | ChromaDB 持久化目录 |
| `RAG_EMBED_MODEL` | `all-MiniLM-L6-v2` | sentence-transformers 模型 |
