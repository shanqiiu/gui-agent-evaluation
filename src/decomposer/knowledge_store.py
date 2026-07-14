"""
App 私有知识库：ChromaDB 向量存储 + 文档摄入。

用法:
    # 首次：摄入 App 知识文档
    python knowledge_store.py --ingest src/decomposer/app_knowledge/

    # 检索
    python knowledge_store.py --query "定时开关机怎么设置"
"""

import argparse
import os
from pathlib import Path
from typing import Optional

# Auto-load .env from project root
try:
    from dotenv import load_dotenv
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    load_dotenv(_PROJECT_ROOT / ".env")
except ImportError:
    pass

import chromadb
from chromadb.utils import embedding_functions


# ── 配置 ────────────────────────────────────────────────────────

_DB_DIR = Path(__file__).resolve().parent / "chroma_db"
_COLLECTION_NAME = "app_knowledge"

# 默认使用 sentence-transformers 做 embedding
# 也可用 text-embedding-3-large 或 BGE-M3
_EMBEDDING_MODEL = "all-MiniLM-L6-v2"


def get_store(persist_dir: Optional[Path] = None) -> chromadb.Collection:
    """获取或创建 ChromaDB collection。"""
    path = str(persist_dir or _DB_DIR)
    client = chromadb.PersistentClient(path=path)
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=_EMBEDDING_MODEL
    )
    return client.get_or_create_collection(
        name=_COLLECTION_NAME,
        embedding_function=ef,
    )


def ingest_documents(docs_dir: str):
    """扫描目录下所有 .md 文件，切段后摄入 ChromaDB。"""
    collection = get_store()
    doc_path = Path(docs_dir)

    if not doc_path.is_dir():
        print(f"[ERROR] 目录不存在: {docs_dir}")
        return

    md_files = sorted(doc_path.glob("*.md"))
    if not md_files:
        print(f"[WARN] 目录下无 .md 文件")
        return

    for mf in md_files:
        app_name = mf.stem
        content = mf.read_text(encoding="utf-8")

        # 简单切段：按 ## 标题分段
        sections = content.split("\n## ")
        sections[0] = sections[0].lstrip("# ").strip()  # 首个段落去掉顶级标题

        ids, documents, metadatas = [], [], []
        for i, sec in enumerate(sections):
            if not sec.strip():
                continue
            # 取段首行作为标题
            title = sec.split("\n")[0].strip()
            chunk_id = f"{app_name}_s{i}"
            ids.append(chunk_id)
            documents.append(sec.strip())
            metadatas.append({"app": app_name, "section": title})

        if ids:
            collection.add(ids=ids, documents=documents, metadatas=metadatas)
            print(f"[OK] {app_name}: {len(ids)} 段已摄入")

    print(f"共 {collection.count()} 条记录")


def query_knowledge(query: str, app_name: Optional[str] = None, top_k: int = 5) -> list[str]:
    """检索相关 App 知识。若 ChromaDB 未建库或无数据，返回空列表不触发模型下载。"""
    # 检查 ChromaDB 是否已初始化（不触发 embedding 模型加载）
    db_file = _DB_DIR / "chroma.sqlite3"
    if not db_file.is_file():
        return []
    collection = get_store()
    if collection.count() == 0:
        return []
    where = {"app": app_name} if app_name else None
    results = collection.query(query_texts=[query], n_results=top_k, where=where)
    docs = results.get("documents", [[]])[0]
    return [d for d in docs if d]


# ── CLI ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="App 知识库管理")
    parser.add_argument("--ingest", help="摄入目录下的 .md 文档")
    parser.add_argument("--query", help="检索查询")
    parser.add_argument("--app", help="限定 App 名称")
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()

    if args.ingest:
        ingest_documents(args.ingest)
    elif args.query:
        docs = query_knowledge(args.query, app_name=args.app, top_k=args.top_k)
        for i, d in enumerate(docs):
            print(f"[{i+1}] {d[:200]}...")
    else:
        parser.print_help()
