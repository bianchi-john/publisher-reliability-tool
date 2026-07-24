import csv
import json
import tempfile
import unittest
from pathlib import Path

from publisher_reliability.errors import AppError
from publisher_reliability.importer import import_csv
from publisher_reliability.services import ResearchService
from publisher_reliability.storage import Storage


class ImporterServiceTest(unittest.TestCase):
    def test_import_requires_complete_probability_vector(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "missing-probabilities.csv"
            with source.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(
                    stream,
                    fieldnames=[
                        "url",
                        "bert_predicted_label",
                        "bert_fold_id",
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "url": "https://example.com/article",
                        "bert_predicted_label": "1",
                        "bert_fold_id": "1",
                    }
                )
            with Storage(root / "data") as storage:
                with self.assertRaises(AppError) as raised:
                    import_csv(storage, source)
                self.assertEqual(raised.exception.code, "IMPORT_INVALID")
                self.assertEqual(storage.rows["prediction_runs"], [])

    def test_import_projects_private_fields_and_supports_aggregation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "predictions.csv"
            fields = [
                "url",
                "title",
                "authors",
                "score",
                "bert_predicted_label",
                "bert_fold_id",
                *[f"bert_prob_class_{index}" for index in range(5)],
            ]
            with source.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader()
                for index, predicted_class in enumerate((1, 3), start=1):
                    writer.writerow(
                        {
                            "url": f"https://example.com/article-{index}",
                            "title": f"private title {index}",
                            "authors": "private author",
                            "score": "private score",
                            "bert_predicted_label": predicted_class,
                            "bert_fold_id": 1,
                            **{
                                f"bert_prob_class_{class_id}": (
                                    "1" if class_id == predicted_class else "0"
                                )
                                for class_id in range(5)
                            },
                        }
                    )

            with Storage(root / "data") as storage:
                imported = import_csv(storage, source)
                self.assertEqual(imported["status"], "succeeded")
                self.assertEqual(len(storage.rows["prediction_runs"]), 2)
                serialized = json.dumps(storage.rows)
                self.assertNotIn("private title", serialized)
                self.assertNotIn("private author", serialized)
                self.assertNotIn("private score", serialized)
                self.assertEqual(
                    json.loads(storage.rows["imports"][0]["protected_columns_json"]),
                    ["score"],
                )

                model_id = storage.rows["models"][0]["model_id"]
                local_model = dict(storage.rows["models"][0])
                local_model.update(
                    model_id="local-bert-fold-1",
                    display_name="BERT fold 1 (local checkpoint)",
                    artifact_kind="pytorch_state_dict",
                    artifact_locator="root-1/bert_fold_1.pt",
                    artifact_sha256="a" * 64,
                    loader_recipe="bert_state_dict",
                    status="validated_not_runnable",
                    artifact_available=True,
                    runnable=False,
                )
                storage.upsert("models", "model_id", local_model)
                service = ResearchService(storage, offline=True)
                article = service.article(storage.rows["prediction_runs"][0]["article_id"])
                self.assertEqual(article["run_count"], 1)
                self.assertEqual(article["runs"][0]["probabilities"], [0, 1, 0, 0, 0])

                article_availability = service.available_models(
                    input_type="article",
                    url="https://example.com/article-1",
                )
                available_for_article = article_availability["items"]
                self.assertEqual(
                    [(row["model_id"], row["eligible"]) for row in available_for_article],
                    [(model_id, True)],
                )
                self.assertEqual(
                    article_availability["availability"]["code"], "AVAILABLE"
                )
                available_for_publisher = service.available_models(
                    input_type="publisher",
                    url="https://example.com/",
                    requested_count=2,
                )["items"]
                self.assertEqual(available_for_publisher[0]["article_count"], 2)
                self.assertEqual(available_for_publisher[0]["probability_count"], 2)
                self.assertTrue(available_for_publisher[0]["eligible"])

                publisher = service.publisher_summaries()[0]
                self.assertEqual(publisher["run_count"], 2)
                self.assertEqual(publisher["probability_run_count"], 2)
                self.assertEqual(publisher["evaluation_count"], 0)

                unknown = service.available_models(
                    input_type="article",
                    url="https://example.com/new-article",
                )
                self.assertEqual(
                    unknown["availability"]["code"],
                    "NEW_ARTICLE_REQUIRES_INFERENCE",
                )

                trained_model = dict(local_model)
                trained_model["model_id"] = "local-bert-fold-2"
                trained_model["fold_id"] = "2"
                with self.assertRaises(AppError) as raised:
                    service.assert_not_training_article(
                        trained_model,
                        storage.rows["prediction_runs"][0]["article_id"],
                    )
                self.assertEqual(raised.exception.code, "TRAINING_DATA_LEAKAGE")
                storage.upsert("models", "model_id", trained_model)
                with self.assertRaises(AppError) as evaluated:
                    service.evaluate(
                        {
                            "input": {
                                "type": "article",
                                "url": "https://example.com/article-1",
                            },
                            "model_id": trained_model["model_id"],
                        },
                        "leakage-test-job",
                    )
                self.assertEqual(
                    evaluated.exception.code,
                    "TRAINING_DATA_LEAKAGE",
                )

                result = service.evaluate(
                    {
                        "input": {
                            "type": "publisher",
                            "url": "https://example.com/",
                            "requested_article_count": 2,
                            "allow_partial": False,
                        },
                        "model_id": model_id,
                        "aggregation_method": "majority_vote",
                    },
                    "test-job",
                )
                self.assertEqual(result["result_class"], 1)
                evaluation = storage.rows["evaluations"][0]
                self.assertEqual(
                    len(json.loads(evaluation["prediction_run_ids_json"])), 2
                )


if __name__ == "__main__":
    unittest.main()
