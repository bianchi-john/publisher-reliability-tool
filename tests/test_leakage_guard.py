"""The guard that stops a checkpoint from being scored on its own training data.

Every model family in the study was split the same way, with one publisher-disjoint
``StratifiedKFold(n_splits=5, shuffle=True, random_state=42)``. An article held out
in fold 3 is therefore held out in fold 3 for every family, and was training data for
the other four folds of every family. These tests pin that rule, including for the
families whose predictions the released dataset does not carry.
"""

import csv
import tempfile
import unittest
from pathlib import Path

from publisher_reliability.errors import AppError
from publisher_reliability.importer import import_csv
from publisher_reliability.services import ResearchService
from publisher_reliability.storage import Storage

FIELDS = [
    "url",
    "bert_predicted_label",
    "bert_fold_id",
    *[f"bert_prob_class_{index}" for index in range(5)],
]


def import_articles(storage: Storage, source: Path, articles: dict[str, int]) -> None:
    """Import one BERT prediction per article, holding it out in the given fold."""

    with source.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        for url, fold_id in articles.items():
            writer.writerow(
                {
                    "url": url,
                    "bert_predicted_label": "1",
                    "bert_fold_id": str(fold_id),
                    **{
                        f"bert_prob_class_{class_id}": "1" if class_id == 1 else "0"
                        for class_id in range(5)
                    },
                }
            )
    import_csv(storage, source)


def local_checkpoint(storage: Storage, family: str, fold_id: int) -> dict[str, object]:
    """Register a runnable local checkpoint of the given family and fold."""

    template = next(
        row for row in storage.rows["models"] if row["artifact_kind"] == "historical_virtual"
    )
    model = {
        **template,
        "model_id": f"local-{family}-fold-{fold_id}",
        "family": family,
        "fold_id": str(fold_id),
        "display_name": f"{family.upper()} fold {fold_id} (local checkpoint)",
        "artifact_kind": "pytorch_state_dict",
        "artifact_locator": f"models/{family}_fold_{fold_id}.pt",
        "artifact_sha256": f"{fold_id}" * 64,
        "status": "compatible",
        "artifact_available": True,
        "runnable": True,
    }
    storage.upsert("models", "model_id", model)
    return model


class LeakageGuardTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.storage = Storage(self.root / "data")
        import_articles(
            self.storage,
            self.root / "dataset.csv",
            {
                "https://example.com/held-out-in-fold-2": 2,
                "https://example.com/held-out-in-fold-4": 4,
            },
        )
        self.service = ResearchService(self.storage, offline=True)
        self.article_id = next(
            run["article_id"]
            for run in self.storage.rows["prediction_runs"]
            if run["canonical_url"].endswith("held-out-in-fold-2")
        )

    def tearDown(self) -> None:
        self.storage.close()
        self.temporary.cleanup()

    def test_checkpoint_trained_on_the_article_is_blocked(self) -> None:
        # The article was held out in fold 2, so every other fold trained on it.
        for fold_id in (1, 3, 4, 5):
            model = local_checkpoint(self.storage, "bert", fold_id)
            with self.assertRaises(AppError) as raised:
                self.service.assert_not_training_article(model, self.article_id)
            self.assertEqual(raised.exception.code, "TRAINING_DATA_LEAKAGE")
            self.assertEqual(raised.exception.details["article_test_folds"], [2])
            self.assertEqual(raised.exception.details["model_fold"], fold_id)

    def test_checkpoint_that_held_the_article_out_is_allowed(self) -> None:
        model = local_checkpoint(self.storage, "bert", 2)
        self.service.assert_not_training_article(model, self.article_id)

    def test_article_absent_from_the_dataset_is_allowed(self) -> None:
        model = local_checkpoint(self.storage, "bert", 1)
        self.service.assert_not_training_article(
            model, "00000000-0000-0000-0000-000000000000"
        )

    def test_guard_applies_to_families_absent_from_the_released_dataset(self) -> None:
        """The released dataset carries no Llama or Mistral predictions.

        Fold membership is recorded per article rather than per family precisely so
        that those checkpoints are still covered; keying it by family would leave them
        with no recorded folds and silently wave every article through.
        """

        for family in ("llama", "mistral"):
            blocked = local_checkpoint(self.storage, family, 1)
            with self.assertRaises(AppError) as raised:
                self.service.assert_not_training_article(blocked, self.article_id)
            self.assertEqual(raised.exception.code, "TRAINING_DATA_LEAKAGE")
            self.assertEqual(raised.exception.details["model_family"], family)

            allowed = local_checkpoint(self.storage, family, 2)
            self.service.assert_not_training_article(allowed, self.article_id)

    def test_available_models_offers_the_safe_fold_and_names_the_blocked_ones(self) -> None:
        for fold_id in (1, 2, 3):
            local_checkpoint(self.storage, "bert", fold_id)

        availability = self.service.available_models(
            url="https://example.com/held-out-in-fold-2",
        )

        eligible = [row for row in availability["items"] if row["eligible"]]
        self.assertTrue(eligible)
        self.assertEqual({int(row["fold_id"]) for row in eligible}, {2})

        blocked = availability["availability"]["blocked_training_models"]
        self.assertEqual({int(row["fold_id"]) for row in blocked}, {1, 3})

    def test_ambiguous_fold_membership_blocks_every_checkpoint(self) -> None:
        # The same article imported under two folds: no single held-out fold can be
        # established for it, so no checkpoint may be trusted with it.
        import_articles(
            self.storage,
            self.root / "conflicting.csv",
            {"https://example.com/held-out-in-fold-2": 5},
        )
        service = ResearchService(self.storage, offline=True)
        model = local_checkpoint(self.storage, "bert", 2)

        with self.assertRaises(AppError) as raised:
            service.assert_not_training_article(model, self.article_id)
        self.assertEqual(raised.exception.code, "TRAINING_DATA_LEAKAGE")
        self.assertEqual(raised.exception.details["article_test_folds"], [2, 5])


if __name__ == "__main__":
    unittest.main()
