import csv
import subprocess
import tempfile
import unittest
from pathlib import Path

from publisher_reliability.errors import AppError
from publisher_reliability.identity import article_id, normalized_hostname, publisher_id
from publisher_reliability.prediction_dataset import (
    BASE_PUBLIC_COLUMNS,
    PUBLIC_COLUMNS,
    USER_PREDICTIONS_FILENAME,
    _dataset_row,
    restore_user_predictions,
    sync_user_predictions,
)
from publisher_reliability.storage import HEADERS, Storage
from scripts.prepare_public_dataset import prepare_release
from scripts.verify_public_dataset import verify_release


class PredictionDatasetSyncTest(unittest.TestCase):
    def test_mirror_preserves_model_name_and_manifest_identity(self) -> None:
        model = {column: "" for column in HEADERS["models"]}
        model.update(
            model_id="custom-model",
            family="custom_encoder_one",
            fold_id="4",
            display_name="Custom encoder — fold 4",
            artifact_kind="custom_transformer_bundle",
            official_manifest_entry_sha256="a" * 64,
        )
        run = {column: "" for column in HEADERS["prediction_runs"]}
        run.update(
            prediction_run_id="run",
            article_id="article",
            canonical_url="https://example.com/article",
            normalized_hostname="example.com",
            model_id="paper-model",
            predicted_class="3",
            prob_class_0="0.01",
            prob_class_1="0.02",
            prob_class_2="0.07",
            prob_class_3="0.80",
            prob_class_4="0.10",
        )

        row = _dataset_row(run, model)

        self.assertEqual(row["prediction_model_name"], model["display_name"])
        self.assertEqual(row["prediction_model_provenance"], "paper_official")
        self.assertEqual(
            row["prediction_official_manifest_entry_sha256"],
            "a" * 64,
        )

    def test_mirrors_without_duplicates_and_restores_user_run(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.csv"
            release = root / "predictions"
            original = {column: "" for column in BASE_PUBLIC_COLUMNS}
            original.update(
                {
                    "article_id": "source-1",
                    "url": "https://example.com/original",
                    "domain": "example.com",
                    "bert_predicted_label": "0",
                    "bert_fold_id": "1",
                    "roberta_predicted_label": "1",
                    "roberta_fold_id": "1",
                }
            )
            for family in ("bert", "roberta"):
                for index in range(5):
                    original[f"{family}_prob_class_{index}"] = "0.2"
            with source.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=BASE_PUBLIC_COLUMNS)
                writer.writeheader()
                writer.writerow(original)
            prepare_release(source, release, 24.0)

            user_url = "https://example.com/user-evaluated"
            user_article_id = article_id(user_url)
            model = {column: "" for column in HEADERS["models"]}
            model.update(
                {
                    "model_id": "local-model",
                    "family": "bert",
                    "fold_id": "1",
                    "display_name": "Local BERT",
                    "artifact_kind": "pytorch_state_dict",
                    "class_order_json": "[0,1,2,3,4]",
                    "runtime_scientific_json": "{}",
                    "status": "compatible",
                    "artifact_available": "true",
                    "runnable": "true",
                    "registered_at": "2026-07-24T00:00:00Z",
                    "last_validated_at": "2026-07-24T00:00:00Z",
                }
            )
            run = {column: "" for column in HEADERS["prediction_runs"]}
            run.update(
                {
                    "prediction_run_id": "local-run",
                    "article_id": user_article_id,
                    "canonical_url": user_url,
                    "publisher_id": publisher_id("example.com"),
                    "normalized_hostname": normalized_hostname(user_url),
                    "model_id": "local-model",
                    "predicted_class": "2",
                    "prob_class_0": "0.05",
                    "prob_class_1": "0.10",
                    "prob_class_2": "0.70",
                    "prob_class_3": "0.10",
                    "prob_class_4": "0.05",
                    "origin": "local_inference",
                    "action": "missing_run_inference",
                    "input_source": user_url,
                    "content_retention": "discard",
                    "job_id": "job-1",
                    "inference_started_at": "2026-07-24T00:00:00Z",
                    "inference_completed_at": "2026-07-24T00:00:01Z",
                    "duration_ms": "1000",
                    "device": "cpu",
                    "software_versions_json": "{}",
                    "recorded_at": "2026-07-24T00:00:01Z",
                }
            )

            self.assertEqual(
                sync_user_predictions(release, [run], {"local-model": model}),
                1,
            )
            self.assertEqual(
                sync_user_predictions(release, [run], {"local-model": model}),
                0,
            )

            # The released file and its manifest are untouched: mirroring a user's own
            # evaluation must never modify the tracked, shared research corpus.
            original_bytes_after_sync = (release / "predictions.csv").read_bytes()
            original_manifest_after_sync = (release / "manifest.json").read_bytes()
            result = verify_release(release)
            self.assertEqual(result["dataset_original_records"], 1)
            self.assertEqual(result["user_evaluation_records"], 0)
            with (release / "predictions.csv").open(
                encoding="utf-8", newline=""
            ) as stream:
                original_rows = list(csv.DictReader(stream))
            self.assertEqual(len(original_rows), 1)
            self.assertEqual(original_rows[0]["prediction_origin"], "dataset_original")

            # The user's own evaluation instead lands in a private mirror file.
            mirror_path = release / USER_PREDICTIONS_FILENAME
            with mirror_path.open(encoding="utf-8", newline="") as stream:
                mirror_rows = list(csv.DictReader(stream))
            self.assertEqual(list(mirror_rows[0]), PUBLIC_COLUMNS)
            self.assertEqual(len(mirror_rows), 1)
            self.assertEqual(mirror_rows[0]["prediction_origin"], "user_evaluation")
            self.assertEqual(mirror_rows[0]["prediction_run_id"], "local-run")
            self.assertEqual(mirror_rows[0]["model_id"], "local-model")
            self.assertEqual(mirror_rows[0]["prediction_model_name"], "Local BERT")
            self.assertEqual(
                mirror_rows[0]["prediction_model_provenance"],
                "local_checkpoint",
            )
            self.assertEqual(
                mirror_rows[0]["prediction_official_manifest_entry_sha256"],
                "",
            )

            with Storage(root / "restored-state") as restored:
                self.assertEqual(restore_user_predictions(restored, release), 1)
                self.assertEqual(restore_user_predictions(restored, release), 0)
                self.assertEqual(
                    sync_user_predictions(
                        release,
                        restored.rows["prediction_runs"],
                        {
                            row["model_id"]: row
                            for row in restored.rows["models"]
                        },
                    ),
                    0,
                )
                self.assertEqual(
                    restored.rows["prediction_runs"][0]["origin"],
                    "local_inference",
                )
                self.assertEqual(
                    restored.rows["prediction_runs"][0]["prediction_run_id"],
                    "local-run",
                )
            with Storage(root / "restored-state") as reopened:
                self.assertEqual(len(reopened.rows["prediction_runs"]), 1)

            # A full restore-and-resync round trip still never touches the shared file.
            self.assertEqual(
                (release / "predictions.csv").read_bytes(), original_bytes_after_sync
            )
            self.assertEqual(
                (release / "manifest.json").read_bytes(), original_manifest_after_sync
            )


def _local_run_and_model(url: str, run_id: str) -> tuple[dict[str, str], dict[str, str]]:
    """A minimal local-inference run/model pair, enough to mirror successfully."""

    model = {column: "" for column in HEADERS["models"]}
    model.update(
        model_id="local-model",
        family="bert",
        fold_id="1",
        display_name="Local BERT",
        artifact_kind="pytorch_state_dict",
        class_order_json="[0,1,2,3,4]",
        runtime_scientific_json="{}",
        status="compatible",
        artifact_available="true",
        runnable="true",
        registered_at="2026-07-24T00:00:00Z",
        last_validated_at="2026-07-24T00:00:00Z",
    )
    run = {column: "" for column in HEADERS["prediction_runs"]}
    run.update(
        prediction_run_id=run_id,
        article_id=article_id(url),
        canonical_url=url,
        publisher_id=publisher_id(normalized_hostname(url)),
        normalized_hostname=normalized_hostname(url),
        model_id="local-model",
        predicted_class="2",
        prob_class_0="0.05",
        prob_class_1="0.10",
        prob_class_2="0.70",
        prob_class_3="0.10",
        prob_class_4="0.05",
        origin="local_inference",
        action="missing_run_inference",
        input_source=url,
        content_retention="discard",
        job_id="job-1",
        inference_started_at="2026-07-24T00:00:00Z",
        inference_completed_at="2026-07-24T00:00:01Z",
        duration_ms="1000",
        device="cpu",
        software_versions_json="{}",
        recorded_at="2026-07-24T00:00:01Z",
    )
    return run, model


class PrivateMirrorStaysOutOfVersionControlTest(unittest.TestCase):
    """Locally inferred predictions are the user's own browsing, not release data.

    `.gitignore` deliberately un-ignores `dataset/predictions/*.csv` so the released
    dataset stays tracked, and then re-ignores the private mirror by name. That
    ordering is easy to undo by accident, and undoing it publishes the URLs someone
    evaluated on their own machine, so it is pinned here rather than trusted.
    """

    def check_ignore(self, relative: str) -> int:
        repository = Path(__file__).resolve().parents[1]
        if not (repository / ".git").exists():
            self.skipTest("not a git checkout")
        try:
            completed = subprocess.run(
                ["git", "check-ignore", "--quiet", relative],
                cwd=repository,
                capture_output=True,
            )
        except FileNotFoundError:  # pragma: no cover - git is present in development
            self.skipTest("git is not installed")
        return completed.returncode

    def test_user_prediction_mirror_is_ignored(self) -> None:
        self.assertEqual(
            self.check_ignore(f"dataset/predictions/{USER_PREDICTIONS_FILENAME}"),
            0,
            "the private mirror of user predictions must not be tracked",
        )

    def test_released_dataset_stays_tracked(self) -> None:
        self.assertEqual(
            self.check_ignore("dataset/predictions/predictions.csv"),
            1,
            "the released dataset must remain part of the repository",
        )


class MirrorOriginTest(unittest.TestCase):
    """Only this file's own kind of row may come back out of it.

    The mirror is an ordinary CSV a user can edit, and `prediction_origin` is the one
    column that says what a row is. Restoring without checking it would turn a row
    claiming to be released dataset material into a local evaluation, silently
    relabelling its provenance in the authoritative ledger.
    """

    URL = "https://outlet.example/a"

    def _mirror_row(self, **overrides: str) -> dict[str, str]:
        row = {column: "" for column in PUBLIC_COLUMNS}
        row.update(
            article_id=article_id(self.URL),
            url=self.URL,
            domain=normalized_hostname(self.URL),
            prediction_origin="user_evaluation",
            prediction_run_id="run-1",
            model_id="model-1",
            prediction_family="bert",
            prediction_fold_id="2",
            prediction_model_name="BERT fold 2 (local checkpoint)",
            prediction_model_provenance="local_checkpoint",
            predicted_label="3",
            prediction_action="missing_run_inference",
            input_source=self.URL,
            content_retention="discard",
            job_id="job-1",
            inference_started_at="2026-07-24T00:00:00Z",
            inference_completed_at="2026-07-24T00:00:01Z",
            duration_ms="10",
            device="cpu",
            software_versions_json="{}",
            recorded_at="2026-07-24T00:00:01Z",
        )
        for index in range(5):
            row[f"prob_class_{index}"] = "0.6" if index == 3 else "0.1"
        row.update(overrides)
        return row

    def _restore(self, row: dict[str, str]):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            release = root / "seed"
            release.mkdir()
            with (release / USER_PREDICTIONS_FILENAME).open(
                "w", encoding="utf-8", newline=""
            ) as stream:
                writer = csv.DictWriter(
                    stream, fieldnames=PUBLIC_COLUMNS, lineterminator="\n"
                )
                writer.writeheader()
                writer.writerow(row)
            with Storage(root / "data") as storage:
                restored = restore_user_predictions(storage, release)
                return restored, len(storage.rows["prediction_runs"])

    def test_a_user_evaluation_row_is_restored(self) -> None:
        restored, runs = self._restore(self._mirror_row())
        self.assertEqual(restored, 1)
        self.assertEqual(runs, 1)

    def test_a_row_claiming_to_be_released_data_is_refused(self) -> None:
        with self.assertRaises(AppError) as raised:
            self._restore(self._mirror_row(prediction_origin="dataset_original"))
        self.assertEqual(raised.exception.code, "IMPORT_INVALID")

    def test_a_row_with_no_origin_at_all_is_refused(self) -> None:
        with self.assertRaises(AppError) as raised:
            self._restore(self._mirror_row(prediction_origin=""))
        self.assertEqual(raised.exception.code, "IMPORT_INVALID")


if __name__ == "__main__":
    unittest.main()
