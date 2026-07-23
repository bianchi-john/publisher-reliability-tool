import csv
import tempfile
import unittest
from pathlib import Path

from publisher_reliability.aggregation import aggregate
from publisher_reliability.errors import AppError
from publisher_reliability.identity import (
    article_id,
    normalize_url,
    normalized_hostname,
    publisher_id,
)
from publisher_reliability.storage import HEADERS, Storage


class IdentityTest(unittest.TestCase):
    def test_normalizes_url_without_changing_meaningful_query_components(self) -> None:
        canonical = normalize_url(
            " HTTPS://WWW.Example.COM:443/News/?x=1&utm_source=test&x=2+3#part "
        )
        self.assertEqual(canonical, "https://www.example.com/News/?x=1&x=2+3")
        self.assertEqual(normalized_hostname(canonical), "example.com")
        self.assertEqual(article_id(canonical), article_id(canonical))
        self.assertEqual(publisher_id("example.com"), publisher_id("example.com"))

    def test_rejects_malformed_percent_encoding(self) -> None:
        with self.assertRaises(AppError) as context:
            normalize_url("https://example.com/discount-20%")
        self.assertEqual(context.exception.code, "INVALID_URL")


class AggregationTest(unittest.TestCase):
    @staticmethod
    def runs(classes, probabilities=None):
        values = []
        for index, predicted_class in enumerate(classes):
            vector = probabilities[index] if probabilities else [None] * 5
            values.append(
                {
                    "predicted_class": str(predicted_class),
                    **{
                        f"prob_class_{class_id}": (
                            "" if vector[class_id] is None else str(vector[class_id])
                        )
                        for class_id in range(5)
                    },
                }
            )
        return values

    def test_majority_vote_uses_smallest_tie(self) -> None:
        result = aggregate(self.runs([1, 3]), "majority_vote")
        self.assertEqual(result["result_class"], 1)

    def test_ordinal_mean_rounds_half_up(self) -> None:
        result = aggregate(self.runs([0, 1, 4]), "ordinal_mean")
        self.assertAlmostEqual(result["ordinal_mean"], 5 / 3)
        self.assertEqual(result["result_class"], 2)

    def test_mean_probabilities(self) -> None:
        vectors = [[0.1, 0.5, 0.2, 0.1, 0.1], [0.2, 0.4, 0.2, 0.1, 0.1]]
        result = aggregate(self.runs([1, 1], vectors), "mean_probabilities")
        self.assertEqual(result["result_class"], 1)
        for actual, expected in zip(
            result["probabilities"], [0.15, 0.45, 0.2, 0.1, 0.1], strict=True
        ):
            self.assertAlmostEqual(actual, expected)

    def test_mean_probabilities_never_fabricates_missing_values(self) -> None:
        with self.assertRaises(AppError) as context:
            aggregate(self.runs([1, 2]), "mean_probabilities")
        self.assertEqual(context.exception.code, "PROBABILITIES_REQUIRED")


class StorageTest(unittest.TestCase):
    def test_fresh_store_contains_seven_exact_ledgers(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with Storage(Path(temporary) / "data") as storage:
                self.assertEqual(set(storage.rows), set(HEADERS))
                state_files = {
                    path.name for path in (Path(temporary) / "data" / "state").glob("*.csv")
                }
                self.assertEqual(
                    state_files, {f"{name}.csv" for name in HEADERS}
                )
                for name, header in HEADERS.items():
                    with storage.path(name).open(newline="", encoding="utf-8") as stream:
                        self.assertEqual(next(csv.reader(stream)), header)

    def test_second_writer_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            first = Storage(Path(temporary) / "data")
            try:
                with self.assertRaises(AppError) as context:
                    Storage(Path(temporary) / "data")
                self.assertEqual(context.exception.code, "STORAGE_ERROR")
            finally:
                first.close()


if __name__ == "__main__":
    unittest.main()
