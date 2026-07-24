import csv
import tempfile
import unittest
from pathlib import Path

from publisher_reliability.importer import (
    PUBLIC_COLUMNS,
    _remove_previous_bundled_release,
    import_csv,
)
from publisher_reliability.services import ResearchService
from publisher_reliability.storage import Storage


def write_predictions(path: Path, urls: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=PUBLIC_COLUMNS)
        writer.writeheader()
        for index, url in enumerate(urls):
            writer.writerow(
                {
                    **{column: "" for column in PUBLIC_COLUMNS},
                    "article_id": str(index),
                    "url": url,
                    "domain": "example.com",
                    "bert_predicted_label": "1",
                    "bert_fold_id": "1",
                    "roberta_predicted_label": "2",
                    "roberta_fold_id": "1",
                    **{
                        f"{family}_prob_class_{class_id}": (
                            "1" if class_id == prediction else "0"
                        )
                        for family, prediction in (("bert", 1), ("roberta", 2))
                        for class_id in range(5)
                    },
                }
            )


class BundledReleaseMigrationTest(unittest.TestCase):
    def test_removes_only_obsolete_bundled_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundled = root / "bundled.csv"
            user = root / "user.csv"
            write_predictions(
                bundled,
                [
                    "https://example.com/old-1",
                    "https://example.com/old-2",
                ],
            )
            write_predictions(user, ["https://example.com/user"])

            with Storage(root / "data") as storage:
                import_csv(
                    storage,
                    bundled,
                    source_kind="bundled_manifest",
                    release_id="old-release",
                )
                import_csv(storage, user)
                bundled_model = next(
                    row
                    for row in storage.rows["models"]
                    if row["display_name"].startswith("BERT")
                    and any(
                        run["origin"] == "bundled_import"
                        and run["model_id"] == row["model_id"]
                        for run in storage.rows["prediction_runs"]
                    )
                )
                service = ResearchService(storage, offline=True)
                service.evaluate(
                    {
                        "input": {
                            "type": "publisher",
                            "url": "https://example.com/",
                            "requested_article_count": 2,
                            "allow_partial": False,
                        },
                        "model_id": bundled_model["model_id"],
                        "aggregation_method": "majority_vote",
                    },
                    "migration-test",
                )
                local = dict(bundled_model)
                local.update(
                    model_id="local-preserved",
                    artifact_kind="pytorch_state_dict",
                    artifact_locator="root-1/bert_fold_1.pt",
                    artifact_sha256="a" * 64,
                    status="validated_not_runnable",
                    artifact_available=True,
                    runnable=False,
                )
                storage.upsert("models", "model_id", local)

                _remove_previous_bundled_release(storage)

                self.assertFalse(
                    any(
                        run["origin"] == "bundled_import"
                        for run in storage.rows["prediction_runs"]
                    )
                )
                self.assertTrue(
                    any(
                        run["origin"] == "user_import"
                        for run in storage.rows["prediction_runs"]
                    )
                )
                self.assertEqual(storage.rows["evaluations"], [])
                self.assertTrue(
                    any(
                        model["model_id"] == "local-preserved"
                        for model in storage.rows["models"]
                    )
                )
                self.assertFalse(
                    any(
                        row["source_kind"] == "bundled_manifest"
                        for row in storage.rows["imports"]
                    )
                )


if __name__ == "__main__":
    unittest.main()
