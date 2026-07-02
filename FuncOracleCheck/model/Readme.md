# CLAUDE.md - 项目解析

## 项目概述

这是一个基于 **Qwen2.5-VL-7B-Instruct** 的视觉语言模型（VLM）检查点，经过 LoRA 微调，用于"达尔文判定技术"项目中的 UI-TARS 应用场景。

## 命名规范解码

目录名 `ddp2_Qwen2.5-VL_oracle_vlm_sft_lora_UI-TARS-1_5-7B_top32App0922_dev_bench80p_ckpt19800` 包含以下信息：

| 字段             | 含义                                             |
| ---------------- | ------------------------------------------------ |
| `ddp2`           | 分布式数据并行训练（DDP）第2阶段                 |
| `Qwen2.5-VL`     | 基础模型架构                                     |
| `oracle_vlm`     | 训练任务类型：Oracle VLM（带标签的视觉语言模型） |
| `sft`            | 监督微调（Supervised Fine-Tuning）               |
| `lora`           | 使用 LoRA 参数高效微调                           |
| `UI-TARS-1_5-7B` | 目标应用：UI-TARS，7B参数规模                    |
| `top32App0922`   | 训练数据：Top 32 App，0922版本数据集             |
| `dev_bench80p`   | 开发基准：80%划分                                |
| `ckpt19800`      | 检查点步数：第19,800步                           |

## 模型架构

- **基础模型**: Qwen2.5-VL-7B-Instruct
- **架构类**: `Qwen2_5_VLForConditionalGeneration`
- **总参数**: 8,292,166,656 (~8.3B)
- **权重总量**: 16,584,333,312 bytes (~15.4 GB)
- **精度**: bfloat16

### 语言模型配置

| 参数         | 值                 |
| ------------ | ------------------ |
| 隐藏层维度   | 3584               |
| 中间层维度   | 18944              |
| 注意力头数   | 28                 |
| KV头数       | 4 (GQA)            |
| 隐藏层数     | 28                 |
| 词表大小     | 152,064            |
| 最大位置编码 | 128,000            |
| 滑动窗口     | 32,768             |
| RoPE Theta   | 1,000,000          |
| RoPE缩放     | mrope [16, 24, 24] |

### 视觉编码器配置

| 参数          | 值              |
| ------------- | --------------- |
| 深度          | 32层            |
| 隐藏维度      | 1280            |
| 注意力头数    | 16              |
| Patch大小     | 14x14           |
| 空间合并      | 2x2             |
| 窗口大小      | 112             |
| 全注意力层    | [7, 15, 23, 31] |
| 时间patch大小 | 2               |
| tokens/second | 2               |

## 文件结构

```
├── config.json                     # 模型架构配置
├── generation_config.json          # 生成参数配置
├── chat_template.json              # 简单聊天模板
├── preprocessor_config.json        # 图像处理器配置
├── tokenizer_config.json           # Tokenizer配置（含工具调用模板）
├── tokenizer.json                  # Tokenizer权重 (7MB)
├── vocab.json                      # 词表 (2.7MB)
├── merges.txt                      # BPE合并规则 (1.6MB)
├── model.safetensors.index.json    # 权重分片索引
├── model-00001-of-00004.safetensors  # 权重分片1 (~4.6GB)
├── model-00002-of-00004.safetensors  # 权重分片2 (~4.6GB)
├── model-00003-of-00004.safetensors  # 权重分片3 (~4.6GB)
├── model-00004-of-00004.safetensors  # 权重分片4 (~1.6GB)
└── README.md                       # 原始Qwen2.5-VL文档
```

## 生成配置

```json
{
  "temperature": 0.1,
  "top_p": 0.001,
  "top_k": 1,
  "repetition_penalty": 1.05,
  "do_sample": true
}
```

注意：`top_k=1` 和 `top_p=0.001` 表示几乎贪婪解码，适合UI操作预测等确定性任务。

## 图像预处理

- **图像尺寸范围**: 3,136 ~ 12,845,056 像素
- **归一化**: ImageNet均值/标准差
- **处理器**: Qwen2VLImageProcessor

## 特殊Token

| Token              | ID            | 用途         |
| ------------------ | ------------- | ------------ |
| `<|endoftext|>`    | 151643        | BOS/PAD      |
| `<\|im_start\|>`   | 151644        | 对话起始     |
| `<\|im_end\|>`     | 151645        | EOS/对话结束 |
| `<|image_pad|>`    | 151646-151647 | 图像占位     |
| `<|vision_start|>` | 151652        | 视觉起始     |
| `<|vision_end|>`   | 151653        | 视觉结束     |
| `<|image_pad|>`    | 151655        | 图像Token    |
| `<|video_pad|>`    | 151656        | 视频Token    |

## 加载方式

```python
from transformers import Qwen2_5_VLForConditionalGeneration, AutoProcessor

model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
    "./ddp2_Qwen2.5-VL_...",
    torch_dtype="auto",
    device_map="auto"
)
processor = AutoProcessor.from_pretrained("./ddp2_Qwen2.5-VL_...")
```

## 工作指令

- 此模型为微调检查点，不包含原始训练脚本或数据
- 修改模型配置前先备份原始 config.json
- 评估时使用相同的生成配置（temperature=0.1, top_k=1）
- 模型支持工具调用（tokenizer中包含 tools 模板）
