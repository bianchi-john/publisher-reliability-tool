"""One persisted FIFO background worker."""

from __future__ import annotations

import json
import queue
import threading
import uuid
from pathlib import Path
from typing import Callable

from .errors import AppError
from .custom_models import import_custom_transformer_bundle
from .importer import import_csv
from .model_scanner import scan_model_roots
from .official_models import import_official_model
from .services import ResearchService
from .storage import Storage, json_field, utc_now


# Opening and terminal phase per job type. Evaluation reports many more phases in
# between (see ResearchService.evaluate); the other two are short enough that an
# opening and a terminal phase describe them honestly.
START_AND_TERMINAL_PHASE = {
    "evaluation": ("preparing", "saving"),
    "dataset_import": ("parsing", "saving"),
    "model_validation": ("scanning", "saving"),
}


class JobManager:
    """Runs long operations on one background thread, one at a time.

    A single FIFO worker is deliberate: evaluations load multi-gigabyte checkpoints,
    and running two at once would exhaust memory on the workstation this demo targets.
    Every state change is persisted, so a job interrupted by a restart is visible as
    failed rather than silently lost.
    """

    def __init__(
        self,
        storage: Storage,
        service: ResearchService,
        *,
        model_roots: tuple[Path, ...] = (),
        dataset_upload_max_bytes: int = 536_870_912,
        model_upload_max_bytes: int = 8_589_934_592,
    ):
        self.storage = storage
        self.service = service
        self.model_roots = model_roots
        self.dataset_upload_max_bytes = dataset_upload_max_bytes
        self.model_upload_max_bytes = model_upload_max_bytes
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
        """Persist a queued job, then hand it to the worker.

        The row is written before the job is queued, so a job the API has accepted is
        always visible afterwards, even if the process stops immediately.
        """

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
        """Run one queued job to a terminal state, recording why it failed if it did."""

        row = next(
            (row for row in self.storage.rows["jobs"] if row["job_id"] == identifier),
            None,
        )
        if row is None or row["status"] != "queued":
            return
        request = json.loads(row["request_json"])
        opening, terminal = START_AND_TERMINAL_PHASE[row["job_type"]]
        self._update(row, status="running", phase=opening, progress=10)
        try:
            if row["job_type"] == "evaluation":
                result = self.service.evaluate(
                    request,
                    identifier,
                    on_progress=lambda phase, progress: self._update(
                        row, status="running", phase=phase, progress=progress
                    ),
                )
            elif row["job_type"] == "dataset_import":
                result = self._run_dataset_import(request)
            else:
                result = self._run_model_validation(request)
            self._update(
                row,
                status="succeeded",
                phase=terminal,
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
            # The cause stays out of the job row: it may name a local path.
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

    def _acquired_upload(self, token: object, missing_message: str) -> Path:
        """Resolve one upload token to the private temporary file the API wrote.

        The token must remain a bare filename: a path separator would let a request
        reach outside the uploads directory.
        """

        if not isinstance(token, str) or Path(token).name != token:
            raise AppError("INVALID_INPUT", "Invalid upload token.")
        source = self.storage.data_dir / "uploads" / token
        if not source.is_file():
            raise AppError("PROCESS_INTERRUPTED", missing_message)
        return source

    def _run_dataset_import(self, request: dict[str, object]) -> dict[str, object]:
        """Import one acquired CSV or CSV.GZ upload and drop its temporary source."""

        token = str(request["source_upload_id"])
        source = self._acquired_upload(token, "The acquired dataset source is missing.")
        result = import_csv(
            self.storage,
            source,
            source_name=str(request.get("source_name", token)),
            max_decompressed_bytes=self.dataset_upload_max_bytes,
        )
        source.unlink(missing_ok=True)
        return result

    def _run_model_validation(self, request: dict[str, object]) -> dict[str, object]:
        """Import an official or custom bundle, or rescan the configured model roots.

        The three shapes are told apart by what the API acquired beforehand: several
        official files, one custom ZIP, or nothing at all for a plain rescan.
        """

        tokens = request.get("source_upload_ids")
        token = request.get("source_upload_id")
        if isinstance(tokens, list):
            return self._import_official_upload(tokens, request.get("source_names"))
        if isinstance(token, str):
            source = self._acquired_upload(
                token, "The acquired custom model source is missing."
            )
            result = import_custom_transformer_bundle(
                self.storage,
                source,
                max_uncompressed_bytes=self.model_upload_max_bytes,
            )
            source.unlink(missing_ok=True)
            return result
        return scan_model_roots(self.storage, self.model_roots)

    def _import_official_upload(
        self, tokens: list[object], names: object
    ) -> dict[str, object]:
        """Reassemble one original paper model from the files the API acquired.

        Every token and name is validated before any file is opened, because a Llama
        checkpoint arrives as two segments that only mean something together.
        """

        if not tokens or any(
            not isinstance(value, str) or Path(value).name != value for value in tokens
        ):
            raise AppError("INVALID_INPUT", "Invalid official upload tokens.")
        sources = [self.storage.data_dir / "uploads" / str(value) for value in tokens]
        if any(not source.is_file() for source in sources):
            raise AppError(
                "PROCESS_INTERRUPTED", "An acquired official model file is missing."
            )
        if (
            not isinstance(names, list)
            or len(names) != len(sources)
            or any(not isinstance(value, str) for value in names)
        ):
            raise AppError("INVALID_INPUT", "Official source names are invalid.")
        result = import_official_model(
            self.storage,
            sources,
            source_names=names,
            max_uncompressed_bytes=self.model_upload_max_bytes,
        )
        for source in sources:
            source.unlink(missing_ok=True)
        return result

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
        tokens = request.get("source_upload_ids")
        if isinstance(tokens, list):
            for value in tokens:
                if isinstance(value, str) and Path(value).name == value:
                    (self.storage.data_dir / "uploads" / value).unlink(missing_ok=True)
