"""Reading a publisher's class from the article predictions already held.

A publisher class is not a record the user creates. It is derived on demand, per
model, from the articles currently stored, and it changes with the counting rule and
with which articles are left in. These tests pin that contract.
"""

import csv
import tempfile
import unittest
from pathlib import Path

from publisher_reliability.errors import AppError
from publisher_reliability.importer import import_csv
from publisher_reliability.services import ResearchService
from publisher_reliability.storage import Storage

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


class PublisherAggregationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.storage = Storage(self.root / "data")

        # One publisher, three articles, all held out in fold 2. BERT reads the
        # publisher as class 1; RoBERTa disagrees on the last article.
        source = self.root / "dataset.csv"
        with source.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerow(prediction_row("https://outlet.example/a", 2, {"bert": 1, "roberta": 1}))
            writer.writerow(prediction_row("https://outlet.example/b", 2, {"bert": 1, "roberta": 1}))
            writer.writerow(prediction_row("https://outlet.example/c", 2, {"bert": 1, "roberta": 3}))
        import_csv(self.storage, source)

        self.service = ResearchService(self.storage, offline=True)
        self.publisher_id = self.storage.rows["prediction_runs"][0]["publisher_id"]

    def tearDown(self) -> None:
        self.storage.close()
        self.temporary.cleanup()

    def article_id(self, suffix: str) -> str:
        return next(
            run["article_id"]
            for run in self.storage.rows["prediction_runs"]
            if run["canonical_url"].endswith(suffix)
        )

    def test_each_model_is_reported_separately_and_never_merged(self) -> None:
        payload = self.service.publisher_aggregation(self.publisher_id)

        families = {row["family"] for row in payload["models"]}
        self.assertEqual(families, {"bert", "roberta"})
        by_family = {row["family"]: row for row in payload["models"]}
        # Two checkpoints are two measurements of the same publisher; averaging them
        # into one number would report something no model actually produced.
        self.assertEqual(by_family["bert"]["result_class"], 1)
        self.assertEqual(by_family["bert"]["used_count"], 3)
        self.assertEqual(by_family["roberta"]["used_count"], 3)

    def test_nothing_is_stored_when_a_publisher_class_is_read(self) -> None:
        before = len(self.storage.rows["prediction_runs"])
        self.service.publisher_aggregation(self.publisher_id)
        self.service.publisher_aggregation(self.publisher_id, method="ordinal_mean")

        self.assertEqual(len(self.storage.rows["prediction_runs"]), before)
        self.assertEqual(self.storage.rows["jobs"], [])

    def test_the_counting_rule_changes_the_result(self) -> None:
        majority = self.service.publisher_aggregation(self.publisher_id, method="majority_vote")
        ordinal = self.service.publisher_aggregation(self.publisher_id, method="ordinal_mean")

        roberta_majority = next(r for r in majority["models"] if r["family"] == "roberta")
        roberta_ordinal = next(r for r in ordinal["models"] if r["family"] == "roberta")
        # Classes 1, 1, 3: the most frequent class is 1, the mean of the indices is 5/3.
        self.assertEqual(roberta_majority["result_class"], 1)
        self.assertEqual(roberta_ordinal["result_class"], 2)

    def test_excluding_an_article_recounts_every_model(self) -> None:
        excluded = self.article_id("/c")

        payload = self.service.publisher_aggregation(
            self.publisher_id, excluded_article_ids=[excluded]
        )

        for row in payload["models"]:
            self.assertEqual(row["available_count"], 3)
            self.assertEqual(row["used_count"], 2)
            self.assertEqual(row["excluded_count"], 1)
        self.assertEqual(payload["excluded_article_ids"], [excluded])
        # Dropping the one disagreeing article makes RoBERTa read the publisher as 1.
        roberta = next(r for r in payload["models"] if r["family"] == "roberta")
        self.assertEqual(roberta["result_class"], 1)

    def test_the_full_article_set_is_returned_with_urls_and_exclusion_state(self) -> None:
        excluded = self.article_id("/b")

        payload = self.service.publisher_aggregation(
            self.publisher_id, excluded_article_ids=[excluded]
        )

        # The interface must not have to reconstruct this from a paginated run listing.
        self.assertEqual(len(payload["articles"]), 3)
        self.assertEqual(
            [item["canonical_url"] for item in payload["articles"]],
            [
                "https://outlet.example/a",
                "https://outlet.example/b",
                "https://outlet.example/c",
            ],
        )
        self.assertEqual(
            [item["excluded"] for item in payload["articles"]], [False, True, False]
        )

    def test_fewer_than_two_articles_yields_no_class_and_says_why(self) -> None:
        remaining = [self.article_id("/b"), self.article_id("/c")]

        payload = self.service.publisher_aggregation(
            self.publisher_id, excluded_article_ids=remaining
        )

        for row in payload["models"]:
            self.assertIsNone(row["result_class"])
            self.assertIn("at least two", str(row["unavailable_reason"]).lower())

    def test_unknown_method_and_unknown_publisher_are_refused(self) -> None:
        with self.assertRaises(AppError) as method:
            self.service.publisher_aggregation(self.publisher_id, method="mean_of_vibes")
        self.assertEqual(method.exception.code, "INVALID_INPUT")

        with self.assertRaises(AppError) as publisher:
            self.service.publisher_aggregation("00000000-0000-0000-0000-000000000000")
        self.assertEqual(publisher.exception.code, "NOT_FOUND")

    def test_leakage_unsafe_predictions_are_never_counted(self) -> None:
        # Re-import article /c under a different fold, making its membership ambiguous.
        conflicting = self.root / "conflicting.csv"
        with conflicting.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerow(
                prediction_row("https://outlet.example/c", 5, {"bert": 1, "roberta": 3})
            )
        import_csv(self.storage, conflicting)
        service = ResearchService(self.storage, offline=True)

        payload = service.publisher_aggregation(self.publisher_id)

        for row in payload["models"]:
            self.assertEqual(row["available_count"], 2)
        self.assertEqual(
            [item["canonical_url"] for item in payload["articles"]],
            ["https://outlet.example/a", "https://outlet.example/b"],
        )


if __name__ == "__main__":
    unittest.main()
