"""The bulk "Clear user data" operation: delete a user's own local evaluation history.

This removes only what a user produced on their own machine — their local
predictions, any content they saved alongside one, and the private mirror that
would otherwise restore both — and never the shared, released dataset.
"""

import tempfile
import unittest
from pathlib import Path

from publisher_reliability.errors import AppError
from publisher_reliability.identity import article_id, normalized_hostname, publisher_id
from publisher_reliability.prediction_dataset import (
    USER_PREDICTIONS_FILENAME,
    restore_user_predictions,
    sync_user_predictions,
)
from publisher_reliability.services import ResearchService
from publisher_reliability.storage import HEADERS, Storage


def _model(model_id: str) -> dict[str, str]:
    model = {column: "" for column in HEADERS["models"]}
    model.update(
        model_id=model_id,
        family="bert",
        fold_id="1",
        display_name=f"{model_id} (BERT fold 1)",
        artifact_kind="pytorch_state_dict",
        class_order_json="[0,1,2,3,4]",
        runtime_scientific_json="{}",
        status="compatible",
        artifact_available="true",
        runnable="true",
        registered_at="2026-07-24T00:00:00Z",
        last_validated_at="2026-07-24T00:00:00Z",
    )
    return model


def _run(run_id: str, url: str, model_id: str, origin: str) -> dict[str, str]:
    run = {column: "" for column in HEADERS["prediction_runs"]}
    run.update(
        prediction_run_id=run_id,
        article_id=article_id(url),
        canonical_url=url,
        publisher_id=publisher_id(normalized_hostname(url)),
        normalized_hostname=normalized_hostname(url),
        model_id=model_id,
        predicted_class="2",
        prob_class_0="0.05",
        prob_class_1="0.10",
        prob_class_2="0.70",
        prob_class_3="0.10",
        prob_class_4="0.05",
        origin=origin,
        action="import" if origin != "local_inference" else "missing_run_inference",
        input_source="unavailable" if origin != "local_inference" else url,
        content_retention="discard",
        source_import_id="import-1" if origin != "local_inference" else "",
        job_id="" if origin != "local_inference" else "job-1",
        inference_started_at="2026-07-24T00:00:00Z",
        inference_completed_at="2026-07-24T00:00:01Z",
        duration_ms="1000",
        device="cpu",
        software_versions_json="{}",
        recorded_at="2026-07-24T00:00:01Z",
    )
    return run


def _content(url: str) -> dict[str, str]:
    return {
        "article_id": article_id(url),
        "canonical_url": url,
        "title": "Saved title",
        "text": "Saved body text.",
        "content_saved_at": "2026-07-24T00:00:02Z",
    }


class ClearUserDataTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.storage = Storage(self.root / "data")
        self.release = self.root / "predictions"

        model = _model("local-model")
        self.storage.upsert("models", "model_id", model)

        # A dataset article, imported and never touched locally: must survive.
        self.dataset_run = _run(
            "dataset-run", "https://example.com/dataset-article", "local-model",
            "bundled_import",
        )
        self.storage.append("prediction_runs", self.dataset_run)

        # A local evaluation of a brand-new article: must be removed.
        self.local_run = _run(
            "local-run", "https://example.com/user-article", "local-model",
            "local_inference",
        )
        self.storage.append("prediction_runs", self.local_run)

        # Content the user saved while reusing the *dataset* article's prediction:
        # local_content is populated purely by that user action, regardless of which
        # run's prediction they were looking at, so it must be cleared too.
        self.storage.upsert(
            "local_content", "article_id", _content("https://example.com/dataset-article")
        )
        self.storage.upsert(
            "local_content", "article_id", _content("https://example.com/user-article")
        )

        sync_user_predictions(
            self.release, [self.local_run], {"local-model": model}
        )

        self.service = ResearchService(
            self.storage, offline=True, prediction_dataset_dir=self.release
        )

    def tearDown(self) -> None:
        self.storage.close()
        self.temporary.cleanup()

    def test_wrong_confirmation_changes_nothing(self) -> None:
        before = list(self.storage.rows["prediction_runs"])

        with self.assertRaises(AppError) as raised:
            self.service.clear_user_data(confirmation="please")
        self.assertEqual(raised.exception.code, "INVALID_INPUT")

        self.assertEqual(self.storage.rows["prediction_runs"], before)
        self.assertEqual(len(self.storage.rows["local_content"]), 2)
        self.assertTrue((self.release / USER_PREDICTIONS_FILENAME).exists())

    def test_refuses_while_an_evaluation_job_is_running(self) -> None:
        job = {column: "" for column in HEADERS["jobs"]}
        job.update(
            job_id="job-running",
            job_type="evaluation",
            status="running",
            phase="classifying the article text",
            progress="60",
            request_json="{}",
            created_at="2026-07-24T00:00:00Z",
            updated_at="2026-07-24T00:00:00Z",
        )
        self.storage.upsert("jobs", "job_id", job)

        with self.assertRaises(AppError) as raised:
            self.service.clear_user_data(confirmation="DELETE")
        self.assertEqual(raised.exception.code, "INVALID_INPUT")
        self.assertEqual(len(self.storage.rows["prediction_runs"]), 2)

    def test_removes_only_local_predictions_and_all_saved_content(self) -> None:
        result = self.service.clear_user_data(confirmation="DELETE")

        self.assertEqual(result, {"deleted_predictions": 1, "deleted_saved_content": 2})

        remaining = self.storage.rows["prediction_runs"]
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0], self.dataset_run)
        self.assertEqual(self.storage.rows["local_content"], [])

    def test_dataset_predictions_survive_byte_for_byte(self) -> None:
        """Nothing about the shared dataset row is touched, not even a timestamp."""

        before = dict(self.storage.rows["prediction_runs"][0])
        self.service.clear_user_data(confirmation="DELETE")
        after = next(
            row
            for row in self.storage.rows["prediction_runs"]
            if row["origin"] == "bundled_import"
        )
        self.assertEqual(before, after)

    def test_private_mirror_is_removed(self) -> None:
        self.service.clear_user_data(confirmation="DELETE")

        self.assertFalse((self.release / USER_PREDICTIONS_FILENAME).exists())

    def test_cleared_predictions_do_not_return_after_a_restart(self) -> None:
        """The regression this whole feature exists to prevent.

        If the mirror were cleared *after* the ledger instead of before, a crash or
        even an ordinary restart between the two steps would let
        `restore_user_predictions` read the still-intact mirror and silently bring
        the "deleted" run back — undoing a deletion already reported as complete.
        """

        self.service.clear_user_data(confirmation="DELETE")
        self.storage.close()

        with Storage(self.root / "data") as reopened:
            restored = restore_user_predictions(reopened, self.release)
            self.assertEqual(restored, 0)
            self.assertEqual(len(reopened.rows["prediction_runs"]), 1)
            self.assertEqual(
                reopened.rows["prediction_runs"][0]["origin"], "bundled_import"
            )

    def test_the_reverse_order_would_have_resurrected_the_run(self) -> None:
        """Demonstrates why the mirror is cleared *before* the ledger, not after.

        This does not call `clear_user_data`: it simulates the crash the ordering
        guards against by performing only the ledger half of a (hypothetical)
        ledger-first sequence, stopping there, and reopening storage as a restart
        would. `restore_user_predictions` finds the mirror still intact and brings
        the "deleted" run right back — the exact failure `clear_user_data` avoids by
        clearing the mirror first instead.
        """

        kept = [
            row
            for row in self.storage.rows["prediction_runs"]
            if row["origin"] != "local_inference"
        ]
        self.storage.replace("prediction_runs", kept)
        self.assertTrue((self.release / USER_PREDICTIONS_FILENAME).exists())
        self.storage.close()

        with Storage(self.root / "data") as reopened:
            restored = restore_user_predictions(reopened, self.release)
            self.assertEqual(restored, 1)
            self.assertEqual(len(reopened.rows["prediction_runs"]), 2)

    def test_is_idempotent_and_harmless_with_nothing_left_to_clear(self) -> None:
        self.service.clear_user_data(confirmation="DELETE")

        second = self.service.clear_user_data(confirmation="DELETE")

        self.assertEqual(second, {"deleted_predictions": 0, "deleted_saved_content": 0})
        self.assertEqual(len(self.storage.rows["prediction_runs"]), 1)


if __name__ == "__main__":
    unittest.main()
