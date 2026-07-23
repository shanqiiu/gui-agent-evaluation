"""Asynchronous job runner for the evaluation pipeline.

Manages subprocess execution of preprocessor and evaluator commands,
captures output streams, and provides SSE-ready event queues for
real-time frontend updates.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[2]
PREPROCESS_CMD = ["python", "-m", "src.preprocessor.pipeline"]
EVALUATE_CMD = ["python", "-m", "src.evaluator.repeated_baseline"]


@dataclass
class JobInfo:
    job_id: str
    job_type: str  # "preprocess" | "evaluate"
    status: str = "pending"  # pending | running | completed | failed
    created_at: float = 0.0
    started_at: float = 0.0
    finished_at: float = 0.0
    config: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] = field(default_factory=dict)
    output_dir: str = ""
    logs: list[str] = field(default_factory=list)
    error: str = ""


class JobManager:
    """Manages pipeline jobs with asyncio subprocess + SSE streaming."""

    def __init__(self) -> None:
        self._jobs: dict[str, JobInfo] = {}
        self._queues: dict[str, asyncio.Queue[str | None]] = {}

    # ── public API ──────────────────────────────────────────────────

    def create_job(self, job_type: str, config: dict[str, Any]) -> JobInfo:
        job = JobInfo(
            job_id=uuid.uuid4().hex[:12],
            job_type=job_type,
            config=config,
            created_at=time.time(),
        )
        self._jobs[job.job_id] = job
        self._queues[job.job_id] = asyncio.Queue()
        return job

    def get_job(self, job_id: str) -> JobInfo | None:
        return self._jobs.get(job_id)

    def list_jobs(self) -> list[dict[str, Any]]:
        return [
            {
                "job_id": j.job_id,
                "job_type": j.job_type,
                "status": j.status,
                "created_at": j.created_at,
                "config": j.config,
                "output_dir": j.output_dir,
                "error": j.error,
            }
            for j in sorted(self._jobs.values(), key=lambda x: -x.created_at)
        ]

    def get_queue(self, job_id: str) -> asyncio.Queue[str | None] | None:
        return self._queues.get(job_id)

    # ── execution ───────────────────────────────────────────────────

    async def run_preprocess(self, job: JobInfo) -> None:
        """Run preprocessing pipeline as a subprocess."""
        config = job.config
        input_path = config.get("input_path", "")
        output_dir = config.get("output_dir", "")
        batch_mode = config.get("batch", False)
        task_graph = config.get("task_graph_enabled", False)
        mock_mode = config.get("mock", False)

        cmd = list(PREPROCESS_CMD)
        if batch_mode:
            cmd.extend(["--batch", input_path])
        else:
            cmd.append(input_path)
        if output_dir:
            cmd.extend(["--output", output_dir])
        job.output_dir = output_dir

        env = os.environ.copy()
        if task_graph:
            env["TASK_GRAPH_ENABLED"] = "1"
        if mock_mode:
            env["PREPROCESS_MOCK"] = "1"

        await self._run_command(job, cmd, env)

    async def run_evaluate(self, job: JobInfo) -> None:
        """Run evaluation baseline as a subprocess."""
        config = job.config
        input_path = config.get("input_path", "")
        output_dir = config.get("output_dir", "")
        batch_mode = config.get("batch", False)
        mock_mode = config.get("mock", False)
        skip_verify = config.get("skip_checkpoint_verify", False)

        cmd = list(EVALUATE_CMD)
        if batch_mode:
            cmd.extend(["--batch", input_path])
        else:
            cmd.append(input_path)
        if output_dir:
            cmd.extend(["--output-dir", output_dir])
        job.output_dir = output_dir or str(Path(input_path).parent / "repeated_baseline")
        if mock_mode:
            cmd.append("--mock")
        if skip_verify:
            cmd.append("--skip-checkpoint-verify")

        await self._run_command(job, cmd, os.environ.copy())

    async def _run_command(
        self,
        job: JobInfo,
        cmd: list[str],
        env: dict[str, str],
    ) -> None:
        queue = self._queues.get(job.job_id)
        if queue is None:
            return

        env = {**env, "PYTHONIOENCODING": "utf-8"}
        job.status = "running"
        job.started_at = time.time()
        job.logs = []
        await queue.put(json.dumps({"type": "status", "status": "running", "cmd": " ".join(cmd)}))

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=str(ROOT_DIR),
                env=env,
            )

            async def read_stream() -> None:
                assert process.stdout is not None
                while True:
                    line = await process.stdout.readline()
                    if not line:
                        break
                    text = line.decode("utf-8", errors="replace").rstrip("\n\r")
                    if text:
                        job.logs.append(text)
                        await queue.put(json.dumps({"type": "log", "line": text}))

            await read_stream()
            returncode = await process.wait()

            if returncode == 0:
                job.status = "completed"
                job.finished_at = time.time()
                # Try to read batch result if batch mode
                result = self._read_result(job)
                job.result = result
                await queue.put(json.dumps({
                    "type": "status",
                    "status": "completed",
                    "returncode": returncode,
                    "result": result,
                }))
            else:
                job.status = "failed"
                job.finished_at = time.time()
                job.error = f"Exit code: {returncode}"
                await queue.put(json.dumps({
                    "type": "status",
                    "status": "failed",
                    "returncode": returncode,
                    "error": job.error,
                }))

        except Exception as exc:
            job.status = "failed"
            job.finished_at = time.time()
            job.error = str(exc)
            await queue.put(json.dumps({
                "type": "status",
                "status": "failed",
                "error": str(exc),
            }))

        finally:
            await queue.put(None)  # signal end of stream

    def _read_result(self, job: JobInfo) -> dict[str, Any]:
        """Read batch_result.json or baseline_result.json from output."""
        candidates = [
            Path(job.output_dir) / "batch_result.json",
            Path(job.output_dir) / "baseline_result.json",
        ]
        for path in candidates:
            try:
                if path.is_file():
                    return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}


# singleton
_manager = JobManager()


def get_job_manager() -> JobManager:
    return _manager
