# GUI Agent Execution Evaluation

This context describes how a GUI Agent task plan is represented and evaluated against its observed execution trajectory.

## Language

**Subtask**:
A planning-level unit that represents a necessary, observable task outcome and may depend on or provide alternatives to other Subtasks.
_Avoid_: Checkpoint, action step, operation

**Checkpoint**:
A compatibility and verification projection of a Subtask used by the existing intent-alignment and execution-verification pipeline.
_Avoid_: Subtask, plan node

**TaskGraph**:
The dependency-aware representation of a task goal, its Subtasks, constraints, and valid alternative branches.
_Avoid_: Checkpoint list, action plan

**Cross-App Sample Set**:
An evaluation set whose task trajectories come from more than one target application; it measures coverage and does not imply that the evaluator or its knowledge base is already application-general.
_Avoid_: General-purpose benchmark, multi-App capability
