"""One persisted FIFO background worker."""

from __future__ import annotations

import json
import queue
import threading
import uuid
from pathlib import Path
from typing import Callable

from .errors import AppError
from .importer import import_csv
from .services import ResearchService
from .storage import Storage, json_field, utc_now


class JobManager:
    def __init__(self, storage: Storage, service: ResearchService):
        self.storage = storage
        self.service = service
        self._queue: queue.Queue[str | None] = queue.Queue()
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run, name="publisher-reliability-worker", daemon=True
        )
        self._thread.start()
        for row in self.storage.rows["jobs"]:
            if row["status"] == "queued":
                self._queue.put(row["job_id"])

    def submit(self, job_type: str, request: dict[str, object]) -> str:
        if job_type not in {"evaluation", "dataset_import", "model_validation"}:
            raise AppError("INVALID_INPUT", "Unknown job type.")
        if self._stop.is_set():
            raise AppError("PROCESS_INTERRUPTED", "The worker is shutting down.")
        now = utc_now()
        identifier = str(uuid.uuid4())
        self.storage.upsert(
            "jobs",
            "job_id",
            {
                "job_id": identifier,
                "job_type": job_type,
                "status": "queued",
                "phase": "",
                "progress": 0,
                "request_json": json_field(request),
                "result_json": json_field({}),
                "error_code": "",
                "error_message": "",
                "created_at": now,
                "started_at": "",
                "finished_at": "",
                "updated_at": now,
            },
        )
        self._queue.put(identifier)
        return identifier

    def stop(self) -> None:
        self._stop.set()
        self._queue.put(None)
        self._thread.join(timeout=5)

    def list(self, *, status: str | None = None, job_type: str | None = None):
        rows = [
            self._public(row)
            for row in self.storage.rows["jobs"]
            if (not status or row["status"] == status)
            and (not job_type or row["job_type"] == job_type)
        ]
        rows.sort(key=lambda row: str(row["created_at"]), reverse=True)
        return rows

    def get(self, identifier: str) -> dict[str, object]:
        row = next(
            (row for row in self.storage.rows["jobs"] if row["job_id"] == identifier),
            None,
        )
        if row is None:
            raise AppError("NOT_FOUND", "Job was not found.")
        return self._public(row)

    @staticmethod
    def _public(row: dict[str, str]) -> dict[str, object]:
        return {
            **row,
            "progress": int(row["progress"]),
            "request": json.loads(row["request_json"]),
            "result": json.loads(row["result_json"]),
        }

    def _run(self) -> None:
        while not self._stop.is_set():
            identifier = self._queue.get()
            if identifier is None:
                return
            try:
                self._execute(identifier)
            finally:
                self._queue.task_done()

    def _execute(self, identifier: str) -> None:
        row = next(
            (row for row in self.storage.rows["jobs"] if row["job_id"] == identifier),
            None,
        )
        if row is None or row["status"] != "queued":
            return
        request = json.loads(row["request_json"])
        phases = {
            "evaluation": ("preparing", "saving"),
            "dataset_import": ("parsing", "saving"),
            "model_validation": ("scanning", "saving"),
        }
        self._update(row, status="running", phase=phases[row["job_type"]][0], progress=10)
        try:
            if row["job_type"] == "evaluation":
                result = self.service.evaluate(request, identifier)
            elif row["job_type"] == "dataset_import":
                token = str(request["source_upload_id"])
                if Path(token).name != token:
                    raise AppError("INVALID_INPUT", "Invalid upload token.")
                source = self.storage.data_dir / "uploads" / token
                if not source.is_file():
                    raise AppError(
                        "PROCESS_INTERRUPTED", "The acquired dataset source is missing."
                    )
                result = import_csv(
                    self.storage,
                    source,
                    source_name=str(request.get("source_name", token)),
                )
                source.unlink(missing_ok=True)
            else:
                result = {
                    "registered": 0,
                    "message": "No supported official artifacts were found.",
                }
            self._update(
                row,
                status="succeeded",
                phase=phases[row["job_type"]][1],
                progress=100,
                result_json=json_field(result),
                finished_at=utc_now(),
            )
        except AppError as exc:
            self._cleanup_upload(row, request)
            self._update(
                row,
                status="failed",
                phase="",
                progress=100,
                error_code=exc.code,
                error_message=exc.message,
                finished_at=utc_now(),
            )
        except Exception:
            self._cleanup_upload(row, request)
            self._update(
                row,
                status="failed",
                phase="",
                progress=100,
                error_code="INTERNAL_ERROR",
                error_message="The operation failed unexpectedly.",
                finished_at=utc_now(),
            )

    def _update(self, row: dict[str, str], **values: object) -> None:
        updated = dict(row)
        updated.update(values)
        if updated["status"] == "running" and not updated["started_at"]:
            updated["started_at"] = utc_now()
        updated["updated_at"] = utc_now()
        self.storage.upsert("jobs", "job_id", updated)
        row.update({key: str(value) for key, value in updated.items()})

    def _cleanup_upload(
        self, row: dict[str, str], request: dict[str, object]
    ) -> None:
        if row["job_type"] not in {"dataset_import", "model_validation"}:
            return
        token = request.get("source_upload_id")
        if isinstance(token, str) and Path(token).name == token:
            (self.storage.data_dir / "uploads" / token).unlink(missing_ok=True)

