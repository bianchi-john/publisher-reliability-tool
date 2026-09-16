"""The CSV a user exports from the Articles page.

The export answers one question: which model said what about which article, and with
what confidence in each class. So it is one row per prediction run — never one row per
article, and never a publisher-level verdict, which is derived on demand and not a
stored record at all.
"""

import csv
import io
import tempfile
import unittest
from pathlib import Path

from publisher_reliability.errors import AppError
from publisher_reliability.importer import import_csv
from publisher_reliability.services import PREDICTION_EXPORT_COLUMNS, ResearchService
from publisher_reliability.storage import HEADERS, Storage

FAMILIES = ("bert", "roberta")
FIELDS = [
    "url",
    *[
        column
        for family in FAMILIES
        for column in (
            f"{family}_predicted_label",
            f"{family}_fold_id",
            *[f"{family}_prob_class_{index}" for index in range(5)],
        )
    ],
]


def prediction_row(url: str, fold_id: int, labels: dict[str, int]) -> dict[str, str]:
    """One dataset row: the same article scored by each family's held-out fold."""

    row: dict[str, str] = {"url": url}
    for family, label in labels.items():
        row[f"{family}_predicted_label"] = str(label)
        row[f"{family}_fold_id"] = str(fold_id)
        for index in range(5):
            row[f"{family}_prob_class_{index}"] = "1" if index == label else "0"
    return row


def parse(document: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(document)))


class PredictionExportTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.storage = Storage(self.root / "data")

        source = self.root / "dataset.csv"
        with source.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerow(prediction_row("https://outlet.example/a", 2, {"bert": 1, "roberta": 1}))
            writer.writerow(prediction_row("https://outlet.example/b", 2, {"bert": 3, "roberta": 4}))
        import_csv(self.storage, source)
        self.service = ResearchService(self.storage, offline=True)

    def tearDown(self) -> None:
        self.storage.close()
        self.temporary.cleanup()

    def add_user_prediction(self) -> None:
        """Record a locally inferred run, as a user evaluation would."""

        dataset_run = self.storage.rows["prediction_runs"][0]
        run = {field: "" for field in HEADERS["prediction_runs"]}
        run.update(
            {key: dataset_run[key] for key in ("article_id", "canonical_url", "normalized_hostname", "publisher_id")},
            prediction_run_id="11111111-1111-1111-1111-111111111111",
            model_id=dataset_run["model_id"],
            origin="local_inference",
            predicted_class="2",
            **{f"prob_class_{index}": "1" if index == 2 else "0" for index in range(5)},
            action="recompute",
            input_source="url",
            content_retention="discard",
            job_id="22222222-2222-2222-2222-222222222222",
            inference_started_at="2026-09-16T10:00:00Z",
            inference_completed_at="2026-09-16T10:00:01Z",
            duration_ms="1000",
            device="cpu",
            software_versions_json="{}",
            recorded_at="2026-09-16T10:00:01Z",
        )
        self.storage.append("prediction_runs", run)
        self.service = ResearchService(self.storage, offline=True)

    def test_header_is_the_agreed_column_set(self) -> None:
        document = self.service.export_predictions()
        self.assertEqual(
            next(csv.reader(io.StringIO(document))), PREDICTION_EXPORT_COLUMNS
        )

    def test_one_row_per_prediction_with_every_class_probability(self) -> None:
        rows = parse(self.service.export_predictions())

        # Two articles scored by two families each.
        self.assertEqual(len(rows), 4)
        first = next(row for row in rows if row["url"].endswith("/a") and row["prediction_family"] == "bert")
        self.assertEqual(first["predicted_label"], "1")
        self.assertEqual(
            [first[f"prob_class_{index}"] for index in range(5)],
            ["0.0", "1.0", "0.0", "0.0", "0.0"],
        )

    def test_every_model_is_identified_by_a_readable_name(self) -> None:
        rows = parse(self.service.export_predictions())

        for row in rows:
            self.assertTrue(row["prediction_model_name"])
            self.assertIn(row["prediction_family"], {"bert", "roberta"})
            self.assertTrue(row["prediction_fold_id"])
            self.assertTrue(row["prediction_model_provenance"])
            # The run and job identifiers are what distinguish one session's work.
            self.assertTrue(row["prediction_run_id"])
            self.assertTrue(row["model_id"])

    def test_all_models_for_one_article_stay_together(self) -> None:
        rows = parse(self.service.export_predictions(sort="url_asc"))

        urls = [row["url"] for row in rows]
        self.assertEqual(urls, sorted(urls))
        for url in set(urls):
            positions = [index for index, value in enumerate(urls) if value == url]
            self.assertEqual(positions, list(range(positions[0], positions[0] + len(positions))))

    def test_user_evaluations_are_exported_beside_dataset_predictions(self) -> None:
        self.add_user_prediction()

        rows = parse(self.service.export_predictions())
        origins = {row["prediction_origin"] for row in rows}
        self.assertEqual(origins, {"user_import", "local_inference"})

        only_user = parse(self.service.export_predictions(origin="local_inference"))
        self.assertEqual(len(only_user), 1)
        self.assertEqual(only_user[0]["predicted_label"], "2")
        self.assertEqual(only_user[0]["job_id"], "22222222-2222-2222-2222-222222222222")

    def test_export_carries_no_publisher_level_verdict(self) -> None:
        document = self.service.export_predictions()

        # A publisher class is read on demand and never stored, so it cannot appear
        # here; every row is one model's reading of one article.
        self.assertNotIn("publisher_class", document)
        self.assertNotIn("aggregation", document)
        for column in PREDICTION_EXPORT_COLUMNS:
            self.assertNotIn("aggregat", column)
        rows = parse(document)
        self.assertEqual(len({row["prediction_run_id"] for row in rows}), len(rows))

    def test_unknown_filters_are_refused(self) -> None:
        with self.assertRaises(AppError) as source:
            self.service.export_predictions(article_source="something_else")
        self.assertEqual(source.exception.code, "INVALID_INPUT")

        with self.assertRaises(AppError) as sort:
            self.service.export_predictions(sort="by_vibes")
        self.assertEqual(sort.exception.code, "INVALID_INPUT")


if __name__ == "__main__":
    unittest.main()
