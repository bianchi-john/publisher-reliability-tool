"""The persisted background worker: clearing its history, and running a job to the end.

`ClearJobsTest` covers `JobManager.clear()`, which must wipe the job history but never
out from under a live job. A row is only ever handed to the worker through `submit()`,
which both writes it and puts its ID on the in-process queue; that class inserts rows
straight into the ledger instead, so a fabricated "queued" or "running" row sits there
without the worker thread ever touching it — the guard is exercised deterministically,
with no race against a real background job.

`JobExecutionTest` does the opposite, and submits real jobs so the worker thread
actually runs them: a job the API has accepted has to reach a terminal state, carry a
stable error code when it fails, and never strand the temporary upload it acquired.
"""

import csv
import tempfile
import time
import unittest
from pathlib import Path

from publisher_reliability.errors import AppError
from publisher_reliability.jobs import JobManager
from publisher_reliability.services import ResearchService
from publisher_reliability.storage import HEADERS, Storage


def _job(job_id: str, status: str) -> dict[str, str]:
    row = {column: "" for column in HEADERS["jobs"]}
    row.update(
        job_id=job_id,
        job_type="model_validation",
        status=status,
        phase="scanning" if status == "running" else "",
        progress="10" if status == "running" else "0",
        request_json="{}",
        result_json="{}",
        created_at="2026-07-24T00:00:00Z",
        updated_at="2026-07-24T00:00:00Z",
    )
    return row


class ClearJobsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.storage = Storage(Path(self.temporary.name) / "data")
        service = ResearchService(self.storage, offline=True)
        self.jobs = JobManager(self.storage, service)

    def tearDown(self) -> None:
        self.jobs.stop()
        self.storage.close()
        self.temporary.cleanup()

    def test_clears_every_terminal_job_and_reports_the_count(self) -> None:
        self.storage.upsert("jobs", "job_id", _job("succeeded-1", "succeeded"))
        self.storage.upsert("jobs", "job_id", _job("failed-1", "failed"))

        removed = self.jobs.clear()

        self.assertEqual(removed, 2)
        self.assertEqual(self.storage.rows["jobs"], [])

    def test_is_harmless_when_there_is_nothing_to_clear(self) -> None:
        self.assertEqual(self.jobs.clear(), 0)

    def test_refuses_while_a_job_is_queued(self) -> None:
        self.storage.upsert("jobs", "job_id", _job("succeeded-1", "succeeded"))
        self.storage.upsert("jobs", "job_id", _job("queued-1", "queued"))

        with self.assertRaises(AppError) as raised:
            self.jobs.clear()
        self.assertEqual(raised.exception.code, "INVALID_INPUT")
        self.assertEqual(len(self.storage.rows["jobs"]), 2)

    def test_refuses_while_a_job_is_running(self) -> None:
        self.storage.upsert("jobs", "job_id", _job("running-1", "running"))

        with self.assertRaises(AppError) as raised:
            self.jobs.clear()
        self.assertEqual(raised.exception.code, "INVALID_INPUT")
        self.assertEqual(len(self.storage.rows["jobs"]), 1)

    def test_no_partial_deletion_when_refused(self) -> None:
        """A refusal must never remove some rows and leave others."""

        self.storage.upsert("jobs", "job_id", _job("succeeded-1", "succeeded"))
        self.storage.upsert("jobs", "job_id", _job("succeeded-2", "succeeded"))
        self.storage.upsert("jobs", "job_id", _job("running-1", "running"))

        with self.assertRaises(AppError):
            self.jobs.clear()

        self.assertEqual(len(self.storage.rows["jobs"]), 3)


class JobExecutionTest(unittest.TestCase):
    """The worker must reach a terminal state and never strand an acquired upload.

    Unlike `ClearJobsTest`, these run real jobs through the background thread. Dataset
    import is the one job type that needs neither a network nor a checkpoint, so it is
    what the lifecycle is exercised with.
    """

    FIELDS = [
        "url",
        "bert_predicted_label",
        "bert_fold_id",
        *[f"bert_prob_class_{index}" for index in range(5)],
    ]

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.storage = Storage(Path(self.temporary.name) / "data")
        self.jobs = JobManager(self.storage, ResearchService(self.storage, offline=True))
        self.uploads = self.storage.data_dir / "uploads"

    def tearDown(self) -> None:
        self.jobs.stop()
        self.storage.close()
        self.temporary.cleanup()

    def _upload(self, name: str, rows: int = 3) -> Path:
        path = self.uploads / name
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=self.FIELDS)
            writer.writeheader()
            for index in range(rows):
                row = {
                    "url": f"https://outlet.example/{index}",
                    "bert_predicted_label": "1",
                    "bert_fold_id": "2",
                }
                for column in range(5):
                    row[f"bert_prob_class_{column}"] = "1" if column == 1 else "0"
                writer.writerow(row)
        return path

    def _await(self, job_id: str, timeout: float = 30.0) -> dict[str, object]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            job = self.jobs.get(job_id)
            if job["status"] in {"succeeded", "failed"}:
                return job
            time.sleep(0.01)
        raise AssertionError(f"job {job_id} never reached a terminal state")

    def test_a_successful_import_finishes_and_drops_its_upload(self) -> None:
        source = self._upload("good.csv")

        job = self._await(
            self.jobs.submit(
                "dataset_import",
                {"source_upload_id": "good.csv", "source_name": "good.csv"},
            )
        )

        self.assertEqual(job["status"], "succeeded")
        self.assertEqual(job["progress"], 100)
        self.assertEqual(job["error_code"], "")
        self.assertEqual(job["result"]["status"], "succeeded")
        self.assertEqual(len(self.storage.rows["prediction_runs"]), 3)
        # The temporary upload is private scratch space, not a record to keep.
        self.assertFalse(source.exists())

    def test_a_failing_import_records_its_code_and_drops_its_upload(self) -> None:
        source = self.uploads / "bad.csv"
        source.write_text("not,a,prediction,file\n1,2,3,4\n", encoding="utf-8")

        job = self._await(
            self.jobs.submit(
                "dataset_import",
                {"source_upload_id": "bad.csv", "source_name": "bad.csv"},
            )
        )

        self.assertEqual(job["status"], "failed")
        self.assertEqual(job["error_code"], "IMPORT_INVALID")
        self.assertTrue(job["error_message"])
        self.assertFalse(source.exists())

    def test_an_upload_token_may_not_escape_the_uploads_directory(self) -> None:
        job = self._await(
            self.jobs.submit(
                "dataset_import",
                {"source_upload_id": "../state/meta.csv", "source_name": "meta"},
            )
        )

        self.assertEqual(job["status"], "failed")
        self.assertEqual(job["error_code"], "INVALID_INPUT")
        # The ledger the token pointed at is untouched.
        self.assertTrue(self.storage.path("meta").is_file())

    def test_a_vanished_upload_fails_without_a_traceback(self) -> None:
        job = self._await(
            self.jobs.submit(
                "dataset_import",
                {"source_upload_id": "absent.csv", "source_name": "absent.csv"},
            )
        )

        self.assertEqual(job["status"], "failed")
        self.assertEqual(job["error_code"], "PROCESS_INTERRUPTED")

    def test_importing_the_same_content_twice_adds_nothing(self) -> None:
        self._upload("first.csv")
        first = self._await(
            self.jobs.submit(
                "dataset_import",
                {"source_upload_id": "first.csv", "source_name": "first.csv"},
            )
        )
        self._upload("second.csv")
        second = self._await(
            self.jobs.submit(
                "dataset_import",
                {"source_upload_id": "second.csv", "source_name": "second.csv"},
            )
        )

        self.assertEqual(second["status"], "succeeded")
        # Identity is the content, so the second upload resolves to the first import.
        self.assertEqual(second["result"]["import_id"], first["result"]["import_id"])
        self.assertEqual(len(self.storage.rows["imports"]), 1)
        self.assertEqual(len(self.storage.rows["prediction_runs"]), 3)
        self.storage.reload()

    def test_an_unknown_job_type_is_refused_before_anything_is_written(self) -> None:
        with self.assertRaises(AppError) as raised:
            self.jobs.submit("nonsense", {})
        self.assertEqual(raised.exception.code, "INVALID_INPUT")
        self.assertEqual(self.storage.rows["jobs"], [])


if __name__ == "__main__":
    unittest.main()
