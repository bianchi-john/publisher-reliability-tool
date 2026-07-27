import csv
import json
import tempfile
import unittest
from pathlib import Path

from publisher_reliability.identity import article_id, normalized_hostname, publisher_id
from publisher_reliability.prediction_dataset import (
    BASE_PUBLIC_COLUMNS,
    PUBLIC_COLUMNS,
    reconcile_prediction_dataset,
    restore_user_predictions,
    sync_user_predictions,
)
from publisher_reliability.storage import HEADERS, Storage
from scripts.prepare_public_dataset import prepare_release
from scripts.verify_public_dataset import verify_release


class PredictionDatasetSyncTest(unittest.TestCase):
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
            result = verify_release(release)
            self.assertEqual(result["dataset_original_records"], 1)
            self.assertEqual(result["user_evaluation_records"], 1)

            with (release / "predictions.csv").open(
                encoding="utf-8", newline=""
            ) as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(list(rows[0]), PUBLIC_COLUMNS)
            self.assertEqual(rows[-1]["prediction_origin"], "user_evaluation")
            self.assertEqual(rows[-1]["prediction_run_id"], "local-run")
            self.assertEqual(rows[-1]["model_id"], "local-model")

            manifest_path = release / "manifest.json"
            stale_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            stale_manifest["records"] = 1
            stale_manifest["user_evaluation_records"] = 0
            stale_manifest["parts"][0]["rows"] = 1
            manifest_path.write_text(
                json.dumps(stale_manifest, indent=2) + "\n",
                encoding="utf-8",
            )
            self.assertTrue(reconcile_prediction_dataset(release))
            self.assertFalse(reconcile_prediction_dataset(release))
            repaired = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(repaired["records"], 2)
            self.assertEqual(repaired["user_evaluation_records"], 1)

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


if __name__ == "__main__":
    unittest.main()
