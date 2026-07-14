"""
Data models for the state extraction pipeline.

These mirror the real data structures from utg.json and clearRes.json.
Only the fields consumed by the extraction pipeline are included.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


# ── Input data models ────────────────────────────────────────────

@dataclass
class UTGNode:
    """Represents a single node from utg.json.nodes[]. Fields are the subset used by extraction."""
    id: int | str
    label: str
    shape: str
    image: str                    # screenshot URL
    raw_directives: str           # JSON string from raw_item.directives
    title_json: str               # JSON string from node.title

    @classmethod
    def from_raw(cls, node: dict) -> "UTGNode":
        raw_item = node.get("raw_item") or {}
        return cls(
            id=node.get("id") or "",
            label=node.get("label", ""),
            shape=node.get("shape", ""),
            image=node.get("image", ""),
            raw_directives=raw_item.get("directives", "{}"),
            title_json=node.get("title", ""),
        )


@dataclass
class UTGStep:
    """Represents a single step from utg.json.stepData[]. Fields consumed by extraction."""
    step_id: str
    action_type: str              # e.g. "click([315, 918])"
    cost_time: str
    thought: str
    step_type: str                # from stepData.type, e.g. "AAS"

    @classmethod
    def from_raw(cls, step: dict) -> "UTGStep":
        return cls(
            step_id=str(step.get("stepId", "")),
            action_type=step.get("action_type", ""),
            cost_time=step.get("cost_time", "0"),
            thought=step.get("thought", ""),
            step_type=step.get("type", ""),
        )


@dataclass
class UTGEdge:
    """Represents a single edge from utg.json.edges[]. Fields consumed by extraction."""
    from_id: int | str
    to_id: int | str
    cost_time: str
    events: list[dict]            # raw event list
    view_images: list[str]        # screenshot URLs

    @classmethod
    def from_raw(cls, edge: dict) -> "UTGEdge":
        return cls(
            from_id=edge.get("from") or "",
            to_id=edge.get("to") or "",
            cost_time=edge.get("costTime", ""),
            events=edge.get("events", []),
            view_images=edge.get("view_images", []),
        )


# ── OCR tree models (from clearRes.json rawPage) ──────────────────

@dataclass
class OCRNode:
    """Single node from clearRes JSON OCR tree."""
    id: str
    type: str                     # "text" | "icon" | "layout" | "image" | "edittext"
    text: str
    content: str
    bounds: list[int]             # [x1, y1, x2, y2]
    confidence: float
    actions: list[dict]           # e.g. [{"name": "clickable", "points": [x, y]}]
    ori_type: str                 # original Android type, e.g. "listitem"
    sub_nodes: list["OCRNode"] = field(default_factory=list)

    @classmethod
    def from_raw(cls, node: dict) -> "OCRNode":
        return cls(
            id=node.get("id", ""),
            type=node.get("type", ""),
            text=node.get("text", ""),
            content=node.get("content", ""),
            bounds=node.get("bounds", []),
            confidence=node.get("confidence", 0.0),
            actions=node.get("actions", []),
            ori_type=node.get("oriType", ""),
            sub_nodes=[cls.from_raw(s) for s in node.get("subNodes", [])],
        )

    def find_node_at_point(self, x: int, y: int) -> Optional["OCRNode"]:
        """
        在 OCR 树中查找包含坐标 (x, y) 的最深层节点（即 Agent 实际点击的目标）。
        
        优先返回叶子节点（无 sub_nodes），因为叶子节点是 OCR 能识别的最精细元素。
        """
        # Check all descendants first, return deepest match
        best: Optional["OCRNode"] = None
        for sub in self.sub_nodes:
            if sub.contains_point(x, y):
                deeper = sub.find_node_at_point(x, y)
                if deeper:
                    # Prefer deeper nodes (more specific)
                    if best is None or len(deeper.id) > len(best.id):
                        best = deeper
        if best:
            return best
        # No descendant matched, check self
        if self.contains_point(x, y):
            return self
        return None

    def contains_point(self, x: int, y: int) -> bool:
        if len(self.bounds) < 4:
            return False
        return (self.bounds[0] <= x <= self.bounds[2] and
                self.bounds[1] <= y <= self.bounds[3])

    def get_parent(self, root: "OCRNode") -> Optional["OCRNode"]:
        """在整棵树中查找当前节点的父节点。"""
        def _find_parent(current: OCRNode, target_id: str) -> Optional["OCRNode"]:
            for sub in current.sub_nodes:
                if sub.id == target_id:
                    return current
                result = _find_parent(sub, target_id)
                if result:
                    return result
            return None
        return _find_parent(root, self.id)

    def get_sibling_texts(self, root: "OCRNode") -> list[str]:
        """返回同级（或同级子节点中）的 text 节点文本。"""
        parent = self.get_parent(root)
        if not parent:
            return []
        texts: list[str] = []
        for sub in parent.sub_nodes:
            if sub.type == "text" and sub.text.strip():
                texts.append(sub.text.strip())
            # Also check grandchildren for text under layout wrappers
            for grandchild in sub.sub_nodes:
                if grandchild.type == "text" and grandchild.text.strip():
                    texts.append(grandchild.text.strip())
        return texts

    def collect_all_texts(self) -> list[dict]:
        """收集树中所有 text 节点（用于指纹计算）。"""
        result: list[dict] = []
        if self.text.strip():
            result.append({
                "id": self.id,
                "type": self.type,
                "bounds": self.bounds,
                "text": self.text,
            })
        for sub in self.sub_nodes:
            result.extend(sub.collect_all_texts())
        return result


# ── Aligned step (intermediate output of parser) ──────────────────

@dataclass
class AlignedStep:
    """Represents a single aligned step with all signals combined."""
    step_id: str
    step_index: int               # 0-based index in sequence

    # Action (from directives)
    action_type: str              # "click" | "scroll" | "type" | "open_app" | "clarify" | "do-nothing" | ...
    action_start_box: list[int]   # [x, y] actual touch coordinates
    action_end_box: list[int]     # [x, y] for multi-point gestures
    action_target: str            # resolved control/element name
    action_content: str           # input text content (for type actions)

    # Intent (from clearRes actionPurpose)
    action_purpose: str           # Agent's self-reported reasoning
    purpose_classification: str   # "state_transition" | "in_state_exploration" | "in_state_interaction" | "terminal"

    # Visual (from screenshot)
    screenshot_path: str          # local path to catchDataTurnId*.jpg
    screenshot_phash: str         # perceptual hash (hex string), computed lazily

    # OCR structure (from clearRes)
    ocr_tree_root: Optional[OCRNode]  # root of OCR tree for this step's screen

    # Timing
    cost_time_ms: int

    # Darwin reference (for later integration)
    step_data_raw: str            # original action_type string from stepData


# ── State extraction output models ────────────────────────────────

@dataclass
class KeyState:
    """A semantically meaningful UI state identified during extraction."""
    state_id: str                 # "s_0", "s_1", ...
    state_type: str               # "stable" | "transient" | "intermediate" | "terminal"

    # Identification
    label: str                    # human-readable label, e.g. "设置首页"
    ocr_fingerprint: str          # SHA-256 hash prefix of OCR text layout
    phash_fingerprint: str        # representative pHash (mode of frames in state)

    # Coverage
    step_indices: list[int]       # which steps belong to this state
    step_range: tuple[int, int]   # [start_step_idx, end_step_idx)

    # Actions
    action_summary: list[str]     # condensed actionPurpose entries for this state

    # Timing
    duration_ms: int              # total time spent in this state
    first_seen_step: int
    last_seen_step: int

    # Evidence
    confidence: float             # 0.0 - 1.0
    boundary_evidence: list[str]  # why this state boundary was chosen


@dataclass
class StateTransition:
    """An edge in the state graph."""
    from_state: str               # state_id
    to_state: str                 # state_id
    trigger_step_idx: int         # the step that caused the transition
    trigger_action_purpose: str   # Agent's stated reason
    transition_type: str          # "forward" | "back" | "loop" | "error"


@dataclass
class StateGraph:
    """Complete state graph for a single task."""
    task_uuid: str
    instruction: str
    total_steps: int

    states: list[KeyState] = field(default_factory=list)
    transitions: list[StateTransition] = field(default_factory=list)
    start_state_id: str = ""
    end_state_id: str = ""

    # Metrics
    total_states: int = 0
    stable_states: int = 0
    intermediate_states: int = 0
    terminal_states: int = 0
    back_tracking_count: int = 0
    loop_count: int = 0
    total_duration_ms: int = 0
    avg_state_duration_ms: int = 0
    avg_confidence: float = 0.0

    def to_dict(self) -> dict:
        """Serialize to JSON-compatible dict (matching v2.0 output format)."""
        states_json = []
        for s in self.states:
            states_json.append({
                "state_id": s.state_id,
                "label": s.label,
                "state_type": s.state_type,
                "step_range": list(s.step_range),
                "duration_ms": s.duration_ms,
                "action_summary": s.action_summary,
                "boundary_evidence": s.boundary_evidence,
                "confidence": s.confidence,
                "ocr_fingerprint": s.ocr_fingerprint,
            })

        transitions_json = []
        for t in self.transitions:
            transitions_json.append({
                "from": t.from_state,
                "to": t.to_state,
                "trigger_step_idx": t.trigger_step_idx,
                "trigger_action_purpose": t.trigger_action_purpose,
                "transition_type": t.transition_type,
            })

        return {
            "task_uuid": self.task_uuid,
            "instruction": self.instruction,
            "total_steps": self.total_steps,
            "state_graph": {
                "states": states_json,
                "transitions": transitions_json,
                "start_state": self.start_state_id,
                "end_state": self.end_state_id,
            },
            "metrics": {
                "total_states": self.total_states,
                "stable_states": self.stable_states,
                "intermediate_states": self.intermediate_states,
                "terminal_states": self.terminal_states,
                "back_tracking_count": self.back_tracking_count,
                "loop_count": self.loop_count,
                "total_duration_ms": self.total_duration_ms,
                "avg_state_duration_ms": self.avg_state_duration_ms,
                "avg_confidence": round(self.avg_confidence, 2),
            },
        }


@dataclass
class PipelineContext:
    """Container for all data flowing through the pipeline."""
    task_uuid: str
    instruction: str

    # Raw parsed data
    utg_nodes: list[dict] = field(default_factory=list)
    utg_steps: list[dict] = field(default_factory=list)
    utg_edges: list[dict] = field(default_factory=list)
    clear_res_pages: list[dict] = field(default_factory=list)
    action_purposes: list[str] = field(default_factory=list)

    # Intermediate outputs
    aligned_steps: list[AlignedStep] = field(default_factory=list)
    boundaries: list[int] = field(default_factory=list)       # step indices of confirmed boundaries
    merged_states: list[KeyState] = field(default_factory=list)
    graph: Optional[StateGraph] = None
