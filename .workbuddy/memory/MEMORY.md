# GUI Agent 执行评估 — 项目记忆

## 项目概述
构建针对 AI 智能体的自动化测试评估系统，实现对多模态 GUI Agent 任务执行合理性、结果正确性、执行效率的自动判定。

## 核心方向
1. 执行轨迹合理性判定（操作前后截图对比 + 差分偏差三分类）
2. 结果正确性判定（检查点达成率）
3. 执行效率判定（语义相似度挖掘重复/无效操作）

## 参考论文
- VeriGUI (ACL 2026): TVAE 框架，截图对比验证
- TrajAD (arXiv 2026): 轨迹异常三分类
- GUI-SHEPHERD (arXiv 2025): 步骤级 process reward
- GUI-Critic-R1 (arXiv 2025): 执行前错误诊断

## 追踪资源
- OSU-NLP-Group/GUI-Agents-Paper-List: 557+ 论文合集 (每周追踪)
- MuskAI/Awesome-AIGC-Detection: AIGC 检测 (每周追踪)

## 技术选型
- VLM: Qwen2.5-VL-7B (语义对齐)
- LLM: Qwen3-8B / GPT-4o (任务分解)
- Embedding: text-embedding-3-large / BGE-M3 (意图编码)
- RAG: ChromaDB / LanceDB
