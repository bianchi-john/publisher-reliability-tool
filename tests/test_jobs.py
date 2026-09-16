"""`JobManager.clear()`: wipe the job history, but never out from under a live job.

A row is only ever handed to the background worker through `submit()`, which both
writes it and puts its ID on the in-process queue. Tests here insert rows straight
into the ledger instead, so a fabricated "queued" or "running" row sits there without
the worker thread ever touching it — the guard is exercised deterministically, with
no race against a real background job.
"""

import tempfile
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


if __name__ == "__main__":
    unittest.main()
