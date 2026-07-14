"""
StateGraph builder: converts aggregated KeyState list into a complete
StateGraph with transitions, loop/back tracking, and metrics.
"""

from __future__ import annotations

from typing import Optional

from .models import KeyState, StateGraph, StateTransition


def build_graph(
    states: list[KeyState],
    task_uuid: str,
    instruction: str,
    total_steps: int,
) -> StateGraph:
    """
    Build a complete StateGraph from merged KeyState list.
    
    Detects:
    - Forward transitions (normal state progression)
    - Back transitions (returning to a previously visited state)
    - Loop transitions (same state repeated)
    - Error transitions (terminal states reached prematurely)
    """
    graph = StateGraph(
        task_uuid=task_uuid,
        instruction=instruction,
        total_steps=total_steps,
    )

    if not states:
        return graph

    graph.start_state_id = states[0].state_id
    graph.end_state_id = states[-1].state_id

    # Build transitions
    visited: dict[str, int] = {}  # fingerprint → last_seen_step
    transitions: list[StateTransition] = []

    for state in states:
        fp = state.ocr_fingerprint

        if fp and fp in visited:
            # This state was seen before
            prev_step = visited[fp]
            if prev_step == state.first_seen_step - 1:
                tt = "forward"
            else:
                tt = "back"
                graph.back_tracking_count += 1
        else:
            tt = "forward"

        if fp:
            visited[fp] = state.last_seen_step

        # Determine transition type for the edge TO this state
        if state.state_type == "terminal":
            tt = "error" if state.label and "手动" in state.label else "forward"

        transitions.append(StateTransition(
            from_state=states[states.index(state) - 1].state_id if states.index(state) > 0 else "",
            to_state=state.state_id,
            trigger_step_idx=state.first_seen_step,
            trigger_action_purpose=state.action_summary[0] if state.action_summary else "",
            transition_type=tt,
        ))

    # Remove the first empty transition
    if transitions and not transitions[0].from_state:
        transitions = transitions[1:]

    graph.states = states
    graph.transitions = transitions

    # Compute metrics
    graph.total_states = len(states)
    graph.stable_states = sum(1 for s in states if s.state_type == "stable")
    graph.intermediate_states = sum(1 for s in states if s.state_type == "intermediate")
    graph.terminal_states = sum(1 for s in states if s.state_type == "terminal")
    graph.loop_count = sum(1 for t in transitions if t.transition_type == "loop")
    graph.total_duration_ms = sum(s.duration_ms for s in states)
    graph.avg_state_duration_ms = (
        graph.total_duration_ms // len(states) if states else 0
    )
    confidences = [s.confidence for s in states]
    graph.avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

    return graph
