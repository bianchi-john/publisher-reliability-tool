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
    def test_ambiguous_imported_fold_membership_is_never_evaluated(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fields = [
                "url",
                "bert_predicted_label",
                "bert_fold_id",
                *[f"bert_prob_class_{index}" for index in range(5)],
            ]
            with Storage(root / "data") as storage:
                for fold_id in (1, 2):
                    source = root / f"fold-{fold_id}.csv"
                    with source.open("w", encoding="utf-8", newline="") as stream:
                        writer = csv.DictWriter(stream, fieldnames=fields)
                        writer.writeheader()
                        writer.writerow(
                            {
                                "url": "https://example.com/ambiguous",
                                "bert_predicted_label": "1",
                                "bert_fold_id": str(fold_id),
                                **{
                                    f"bert_prob_class_{class_id}": (
                                        "1" if class_id == 1 else "0"
                                    )
                                    for class_id in range(5)
                                },
                            }
                        )
                    import_csv(storage, source)

                historical = next(
                    row
                    for row in storage.rows["models"]
                    if row["family"] == "bert" and row["fold_id"] == "1"
                )
                local_model = {
                    **historical,
                    "model_id": "local-bert-fold-1",
                    "artifact_kind": "pytorch_state_dict",
                    "artifact_locator": "models/bert_fold_1.pt",
                    "artifact_sha256": "a" * 64,
                    "status": "validated_not_runnable",
                    "artifact_available": True,
                    "runnable": False,
                }
                storage.upsert("models", "model_id", local_model)
                service = ResearchService(storage, offline=True)
                identifier = storage.rows["prediction_runs"][0]["article_id"]

                with self.assertRaises(AppError) as raised:
                    service.assert_not_training_article(local_model, identifier)
                self.assertEqual(raised.exception.code, "TRAINING_DATA_LEAKAGE")
                self.assertEqual(
                    raised.exception.details["article_test_folds"], [1, 2]
                )

                availability = service.available_models(
                    input_type="article",
                    url="https://example.com/ambiguous",
                )
                self.assertEqual(availability["items"], [])
                self.assertEqual(
                    availability["availability"]["code"],
                    "TRAINING_DATA_LEAKAGE",
                )

    def test_import_enforces_decompressed_byte_limit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "too-large.csv"
            source.write_text(
                "url,bert_predicted_label,bert_fold_id,"
                "bert_prob_class_0,bert_prob_class_1,bert_prob_class_2,"
                "bert_prob_class_3,bert_prob_class_4\n",
                encoding="utf-8",
            )
            with Storage(root / "data") as storage:
                with self.assertRaises(AppError) as raised:
                    import_csv(
                        storage,
                        source,
                        max_decompressed_bytes=32,
                    )
                self.assertEqual(raised.exception.code, "PAYLOAD_TOO_LARGE")

    def test_import_rejects_non_finite_probabilities(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "non-finite.csv"
            fields = [
                "url",
                "bert_predicted_label",
                "bert_fold_id",
                *[f"bert_prob_class_{index}" for index in range(5)],
            ]
            with source.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader()
                writer.writerow(
                    {
                        "url": "https://example.com/article",
                        "bert_predicted_label": "0",
                        "bert_fold_id": "1",
                        "bert_prob_class_0": "NaN",
                        "bert_prob_class_1": "0",
                        "bert_prob_class_2": "0",
                        "bert_prob_class_3": "0",
                        "bert_prob_class_4": "0",
                    }
                )
            with Storage(root / "data") as storage:
                with self.assertRaises(AppError) as raised:
                    import_csv(storage, source)
                self.assertEqual(raised.exception.code, "IMPORT_INVALID")
                self.assertEqual(storage.rows["prediction_runs"], [])

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
                self.assertEqual(article["source_type"], "dataset")
                self.assertEqual(article["dataset_run_count"], 1)
                self.assertEqual(article["local_run_count"], 0)

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
