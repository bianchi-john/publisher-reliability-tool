import csv
import json
import tempfile
import unittest
from pathlib import Path

from scripts.prepare_public_dataset import (
    EXCLUDED_NEWSGUARD_COLUMNS,
    PUBLIC_COLUMNS,
    REDACTED_EDITORIAL_COLUMNS,
    prepare_release,
)
from scripts.verify_public_dataset import verify_release


class PreparePublicDatasetTest(unittest.TestCase):
    def test_creates_prediction_only_release(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            temp_dir = Path(temp_name)
            source = temp_dir / "source.csv"
            output = temp_dir / "release"
            source_columns = PUBLIC_COLUMNS + EXCLUDED_NEWSGUARD_COLUMNS

            base_row = {column: "" for column in source_columns}
            base_row.update(
                {
                    "url": "https://www.example.com/news/example?source=test",
                    "title": "Synthetic title",
                    "text": "Synthetic English article body.",
                    "authors": "Example Author",
                    "domain": "untrusted-input.example",
                    "score": "100",
                    "country": "US",
                    "language": "en",
                    "topics": "Example",
                    "paywall": "No",
                    "opinion_advocacy": "No",
                    "label": "4",
                    "bert_predicted_label": "3",
                    "bert_fold_id": "1",
                    "roberta_predicted_label": "3",
                    "roberta_fold_id": "1",
                    "llama_predicted_label": "3",
                    "llama_fold_id": "1",
                    "mistral_predicted_label": "3",
                    "mistral_fold_id": "1",
                }
            )
            for model in ("bert", "roberta"):
                for class_id in range(5):
                    base_row[f"{model}_prob_class_{class_id}"] = "0.2"

            with source.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=source_columns)
                writer.writeheader()
                for article_id in (10, 20):
                    row = dict(base_row)
                    row["article_id"] = str(article_id)
                    writer.writerow(row)

            prepare_release(source, output, 24.0, "first")

            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["source_records"], 2)
            self.assertEqual(manifest["records"], 1)
            self.assertEqual(manifest["unique_urls"], 1)
            self.assertEqual(manifest["duplicate_url_rows"], 0)
            self.assertEqual(manifest["duplicate_source_url_groups"], 1)
            self.assertEqual(manifest["skipped_duplicate_rows"], 1)
            self.assertEqual(
                manifest["redacted_editorial_columns"], REDACTED_EDITORIAL_COLUMNS
            )
            self.assertEqual(len(manifest["parts"]), 1)

            part = output / manifest["parts"][0]["file"]
            with part.open(encoding="utf-8", newline="") as stream:
                rows = list(csv.DictReader(stream))

            self.assertEqual(list(rows[0]), PUBLIC_COLUMNS)
            self.assertEqual([row["article_id"] for row in rows], ["0"])
            self.assertEqual(rows[0]["domain"], "example.com")
            for column in REDACTED_EDITORIAL_COLUMNS:
                self.assertEqual(rows[0][column], "")
            for excluded in EXCLUDED_NEWSGUARD_COLUMNS:
                self.assertNotIn(excluded, rows[0])

            result = verify_release(output, source)
            self.assertEqual(result["records"], 1)
            self.assertEqual(result["parts"], 1)
            self.assertEqual(result["skipped_duplicate_rows"], 1)


if __name__ == "__main__":
    unittest.main()
