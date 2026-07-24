"""아주 가벼운 백그라운드 작업 레지스트리 (음성/렌더/한번에 공용).

voicewright/server/jobs.py 의 패턴을 따르되, 단계(stage)와 로그를 가진
범용 작업으로 일반화했다. UI 는 /api/mf/jobs/{id} 를 폴링한다.
"""
from __future__ import annotations

import asyncio
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class Job:
    job_id: str
    kind: str                          # "synth" | "render" | "oneclick"
    bundle: str
    status: str = "queued"             # queued | running | done | error
    stage: str = ""                    # 사람이 읽는 현재 단계
    completed: int = 0
    total: int = 0
    log: list[str] = field(default_factory=list)
    result: dict[str, Any] | None = None
    error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "kind": self.kind,
            "bundle": self.bundle,
            "status": self.status,
            "stage": self.stage,
            "completed": self.completed,
            "total": self.total,
            "log": self.log[-200:],
            "result": self.result,
            "error": self.error,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
        }

    def add_log(self, line: str) -> None:
        self.log.append(line)


class Registry:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}

    def create(self, *, kind: str, bundle: str, total: int = 0) -> Job:
        job_id = secrets.token_hex(4)
        job = Job(job_id=job_id, kind=kind, bundle=bundle, total=total,
                  status="queued", started_at=datetime.now(timezone.utc))
        self._jobs[job_id] = job
        return job

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def finish(self, job: Job, *, status: str, result: dict | None = None,
               error: str | None = None) -> None:
        job.status = status
        job.result = result
        job.error = error
        job.finished_at = datetime.now(timezone.utc)


_registry: Registry | None = None
_lock = asyncio.Lock()


def get_registry() -> Registry:
    global _registry
    if _registry is None:
        _registry = Registry()
    return _registry
