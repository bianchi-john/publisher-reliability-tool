import csv
import json
import tempfile
import unittest
from pathlib import Path

from publisher_reliability.importer import import_csv
from publisher_reliability.services import ResearchService
from publisher_reliability.storage import Storage


class ImporterServiceTest(unittest.TestCase):
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

                service = ResearchService(storage, offline=True)
                model_id = storage.rows["models"][0]["model_id"]
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

