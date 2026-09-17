"""A damaged upload is the user's problem to fix, and must say so.

Both import paths open an archive, validate its directory, and only then stream the
member bytes out. A file that parses at the directory level but is damaged inside --
truncated in transit, or with a member failing its CRC -- fails during that streaming
step, which is past every validation guard.

That matters because of how the worker classifies failures: `AppError` becomes the
stable code it carries, and anything else becomes `INTERNAL_ERROR`, "The operation
failed unexpectedly". A half-uploaded multi-gigabyte checkpoint is an ordinary
accident, not an internal fault, and reporting it as one leaves the user unable to
tell whether to upload again or report a bug. These tests pin the stable codes.
"""

import csv
import gzip
import io
import tempfile
import time
import unittest
import zipfile
from pathlib import Path

from publisher_reliability.errors import AppError
from publisher_reliability.importer import import_csv
from publisher_reliability.jobs import JobManager
from publisher_reliability.services import ResearchService
from publisher_reliability.storage import Storage

FIELDS = [
    "url",
    "bert_predicted_label",
    "bert_fold_id",
    *[f"bert_prob_class_{index}" for index in range(5)],
]


def _prediction_csv_bytes(rows: int = 200) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=FIELDS, lineterminator="\n")
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
    return buffer.getvalue().encode("utf-8")


def _zip_with_bad_crc() -> bytes:
    """A ZIP whose directory parses but whose stored member bytes were altered."""

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_STORED) as archive:
        archive.writestr("prt-model.json", b"B" * 4096)
    raw = bytearray(buffer.getvalue())
    raw[40] ^= 0xFF
    return bytes(raw)


class DamagedDatasetUploadTest(unittest.TestCase):
    def _import(self, blob: bytes, name: str = "upload.csv.gz") -> AppError:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / name
            source.write_bytes(blob)
            with Storage(root / "data") as storage:
                with self.assertRaises(AppError) as raised:
                    import_csv(storage, source)
                self.assertEqual(storage.rows["prediction_runs"], [])
                return raised.exception

    def test_a_truncated_gzip_stream_is_invalid_input_not_a_crash(self) -> None:
        # Stopping mid-stream raises EOFError, which is not an OSError and so used to
        # escape the handler entirely.
        error = self._import(gzip.compress(_prediction_csv_bytes())[:-40])
        self.assertEqual(error.code, "IMPORT_INVALID")

    def test_a_corrupt_deflate_body_is_invalid_input_not_a_crash(self) -> None:
        # Damaged compressed bytes raise zlib.error, which is not an OSError either.
        blob = gzip.compress(_prediction_csv_bytes())
        damaged = blob[:30] + bytes(byte ^ 0xFF for byte in blob[30:60]) + blob[60:]
        error = self._import(damaged)
        self.assertEqual(error.code, "IMPORT_INVALID")

    def test_a_file_that_is_not_gzip_at_all_is_still_invalid_input(self) -> None:
        error = self._import(b"this is plainly not gzip data\n" * 50)
        self.assertEqual(error.code, "IMPORT_INVALID")


class DamagedModelBundleTest(unittest.TestCase):
    """The same contract, through the worker, for a custom model ZIP."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.storage = Storage(Path(self.temporary.name) / "data")
        self.jobs = JobManager(self.storage, ResearchService(self.storage, offline=True))

    def tearDown(self) -> None:
        self.jobs.stop()
        self.storage.close()
        self.temporary.cleanup()

    def _run(self, blob: bytes) -> dict[str, object]:
        token = "bundle.zip"
        (self.storage.data_dir / "uploads" / token).write_bytes(blob)
        job_id = self.jobs.submit(
            "model_validation",
            {
                "source_upload_id": token,
                "source_name": "bundle.zip",
                "bundle_kind": "custom_transformer",
            },
        )
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            job = self.jobs.get(job_id)
            if job["status"] in {"succeeded", "failed"}:
                return job
            time.sleep(0.01)
        raise AssertionError("job never reached a terminal state")

    def test_a_member_failing_its_crc_is_reported_as_a_bad_upload(self) -> None:
        job = self._run(_zip_with_bad_crc())

        self.assertEqual(job["status"], "failed")
        self.assertEqual(job["error_code"], "INVALID_INPUT")
        self.assertIn("corrupt", job["error_message"].lower())
        # Nothing damaged is left behind to confuse the next attempt.
        self.assertEqual(list((self.storage.data_dir / "uploads").iterdir()), [])
        self.assertEqual(list((self.storage.data_dir / "staging").iterdir()), [])
        self.assertEqual(self.storage.rows["models"], [])

    def test_a_bundle_that_is_not_a_zip_is_still_a_bad_upload(self) -> None:
        job = self._run(b"definitely not a zip archive")

        self.assertEqual(job["status"], "failed")
        self.assertEqual(job["error_code"], "INVALID_INPUT")


if __name__ == "__main__":
    unittest.main()
