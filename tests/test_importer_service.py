import csv
import json
import tempfile
import unittest
from pathlib import Path

from publisher_reliability.errors import AppError
from publisher_reliability.importer import import_csv
from publisher_reliability.services import ResearchService
from publisher_reliability.storage import HEADERS, Storage


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

                exported = list(
                    csv.DictReader(
                        service.export_predictions(sort="url_asc").splitlines()
                    )
                )
                self.assertEqual(len(exported), 2)
                self.assertEqual(
                    [row["url"] for row in exported],
                    [
                        "https://example.com/article-1",
                        "https://example.com/article-2",
                    ],
                )
                first = exported[0]
                self.assertEqual(first["prediction_family"], "bert")
                self.assertEqual(first["prediction_fold_id"], "1")
                self.assertEqual(first["prediction_model_name"], "BERT fold 1 (historical)")
                self.assertEqual(first["prediction_model_provenance"], "paper_dataset")
                self.assertEqual(first["prediction_origin"], "user_import")
                self.assertEqual(first["predicted_label"], "1")
                self.assertEqual(
                    [first[f"prob_class_{index}"] for index in range(5)],
                    ["0.0", "1.0", "0.0", "0.0", "0.0"],
                )
                self.assertTrue(first["prediction_run_id"])
                self.assertTrue(first["model_id"])
                self.assertNotIn("private title", service.export_predictions())
                self.assertNotIn("private author", service.export_predictions())

                article_availability = service.available_models(
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
                # A publisher is not an evaluation input: its class is read from the
                # article predictions instead, by publisher_aggregation.
                publisher = service.publisher_summaries()[0]
                self.assertEqual(publisher["run_count"], 2)
                self.assertEqual(publisher["probability_run_count"], 2)

                unknown = service.available_models(
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

                # A family with no predictions of its own in the released dataset is
                # still covered: the guard must recognise a training article for it,
                # which it can only do if fold membership is a property of the article
                # rather than of the model family.
                dataset_article = storage.rows["prediction_runs"][0]["article_id"]
                for family, artifact_kind in (
                    ("custom_encoder_one", "custom_transformer_bundle"),
                    ("custom_encoder_two", "custom_transformer_bundle"),
                ):
                    self.assertFalse(
                        any(
                            row["family"] == family
                            for row in storage.rows["models"]
                        ),
                        f"{family} must have no imported predictions in this fixture",
                    )
                    paper_model = {column: "" for column in HEADERS["models"]}
                    paper_model.update(
                        model_id=f"paper-{family}-fold-2",
                        family=family,
                        fold_id="2",
                        artifact_kind=artifact_kind,
                        official_manifest_entry_sha256="d" * 64,
                    )
                    with self.assertRaises(AppError) as leaked:
                        service.assert_not_training_article(
                            paper_model, dataset_article
                        )
                    self.assertEqual(leaked.exception.code, "TRAINING_DATA_LEAKAGE")
                    self.assertEqual(leaked.exception.details["model_family"], family)

                    # Its own held-out fold stays evaluable.
                    held_out = dict(paper_model)
                    held_out.update(model_id=f"paper-{family}-fold-1", fold_id="1")
                    service.assert_not_training_article(held_out, dataset_article)
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

                # A publisher class is now derived on demand from the article
                # predictions, never created and stored by the user.
                publisher_id = storage.rows["prediction_runs"][0]["publisher_id"]
                derived = service.publisher_aggregation(publisher_id)
                self.assertEqual(derived["method"], "majority_vote")
                self.assertEqual(len(derived["models"]), 1)
                entry = derived["models"][0]
                self.assertEqual(entry["used_count"], 2)
                self.assertEqual(entry["result_class"], 1)
                self.assertEqual(entry["family"], "bert")

                # Excluding an article changes the reading without writing anything.
                excluded_article = entry["article_ids"][0]
                narrowed = service.publisher_aggregation(
                    publisher_id, excluded_article_ids=[excluded_article]
                )
                narrowed_entry = narrowed["models"][0]
                self.assertEqual(narrowed_entry["used_count"], 1)
                self.assertEqual(narrowed_entry["excluded_count"], 1)
                self.assertIsNone(narrowed_entry["result_class"])
                self.assertIn("two leakage-safe", narrowed_entry["unavailable_reason"])

                # The counting rule is a parameter of the question, not of the data.
                for method in ("ordinal_mean", "mean_probabilities"):
                    other = service.publisher_aggregation(publisher_id, method=method)
                    self.assertEqual(other["method"], method)
                    self.assertEqual(other["models"][0]["used_count"], 2)
                with self.assertRaises(AppError) as bad_method:
                    service.publisher_aggregation(publisher_id, method="nonsense")
                self.assertEqual(bad_method.exception.code, "INVALID_INPUT")

                # Evaluating several articles at once is no longer an operation.
                with self.assertRaises(AppError) as rejected:
                    service.evaluate(
                        {
                            "input": {
                                "type": "publisher",
                                "url": "https://example.com/",
                                "requested_article_count": 2,
                            },
                            "model_id": model_id,
                        },
                        "publisher-reject",
                    )
                self.assertEqual(rejected.exception.code, "INVALID_INPUT")
                self.assertEqual(
                    rejected.exception.message, "Unknown evaluation input type."
                )


class RejectedImportModelRegistrationTest(unittest.TestCase):
    """A historical identity exists to explain predictions, so it needs at least one.

    A family/fold whose every row was rejected as conflicting explains nothing. Left
    registered, it appears on the Models page as a checkpoint identity accounting for
    no prediction at all, which is indistinguishable from a real dataset identity.
    """

    FIELDS = [
        "url",
        "bert_predicted_label",
        "bert_fold_id",
        *[f"bert_prob_class_{index}" for index in range(5)],
        "roberta_predicted_label",
        "roberta_fold_id",
        *[f"roberta_prob_class_{index}" for index in range(5)],
    ]

    @classmethod
    def _row(cls, url: str, *, bert: int, roberta: int, fold: int = 2) -> dict[str, str]:
        row = {"url": url}
        for family, label in (("bert", bert), ("roberta", roberta)):
            row[f"{family}_predicted_label"] = str(label)
            row[f"{family}_fold_id"] = str(fold)
            for index in range(5):
                row[f"{family}_prob_class_{index}"] = "1" if index == label else "0"
        return row

    def _write(self, path: Path, rows: list[dict[str, str]]) -> None:
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=self.FIELDS)
            writer.writeheader()
            writer.writerows(rows)

    def test_a_wholly_rejected_import_registers_no_model(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "conflicting.csv"
            # The same article and model with two different outputs: unresolvable.
            self._write(source, [
                self._row("https://outlet.example/a", bert=1, roberta=1),
                self._row("https://outlet.example/a", bert=3, roberta=3),
            ])

            with Storage(root / "data") as storage:
                result = import_csv(storage, source)

                self.assertEqual(result["status"], "failed")
                self.assertEqual(storage.rows["prediction_runs"], [])
                self.assertEqual(storage.rows["models"], [])
                self.assertEqual(len(json.loads(result["warnings_json"])), 2)
                storage.reload()

    def test_a_partially_rejected_import_registers_only_what_it_explains(self) -> None:
        # BERT conflicts on the one article; RoBERTa agrees with itself and survives.
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "partial.csv"
            self._write(source, [
                self._row("https://outlet.example/a", bert=1, roberta=2),
                self._row("https://outlet.example/a", bert=3, roberta=2),
            ])

            with Storage(root / "data") as storage:
                result = import_csv(storage, source)

                self.assertEqual(result["status"], "succeeded_with_rejections")
                families = {row["family"] for row in storage.rows["models"]}
                self.assertEqual(families, {"roberta"})
                self.assertEqual(len(storage.rows["prediction_runs"]), 1)
                storage.reload()


if __name__ == "__main__":
    unittest.main()
