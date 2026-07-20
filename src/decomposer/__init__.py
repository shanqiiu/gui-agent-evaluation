"""src/decomposer — 任务分解引擎（LLM + RAG）"""

from .decomposer import Decomposer, init_decomposer, decompose_instruction
from .knowledge_store import query_knowledge, ingest_documents
from .models import TaskAnnotation, TaskGraph
from .projection import migrate_checkpoints_to_task_graph, project_checkpoints
from .schema import (
    TASK_ANNOTATION_SCHEMA_VERSION,
    TASK_GRAPH_SCHEMA_VERSION,
    TaskGraphSchemaError,
    decode_task_annotation,
    decode_task_graph,
    dumps_task_annotation,
    dumps_task_graph,
    encode_task_annotation,
    encode_task_graph,
    loads_task_annotation,
    loads_task_graph,
    validate_task_annotation,
    validate_task_graph,
)

__all__ = [
    "Decomposer",
    "init_decomposer",
    "decompose_instruction",
    "query_knowledge",
    "ingest_documents",
    "TaskGraph",
    "TaskAnnotation",
    "project_checkpoints",
    "migrate_checkpoints_to_task_graph",
    "TASK_GRAPH_SCHEMA_VERSION",
    "TASK_ANNOTATION_SCHEMA_VERSION",
    "TaskGraphSchemaError",
    "decode_task_graph",
    "encode_task_graph",
    "loads_task_graph",
    "dumps_task_graph",
    "validate_task_graph",
    "decode_task_annotation",
    "encode_task_annotation",
    "loads_task_annotation",
    "dumps_task_annotation",
    "validate_task_annotation",
]
