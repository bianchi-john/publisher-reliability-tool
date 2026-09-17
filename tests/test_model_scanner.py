import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from publisher_reliability.custom_models import directory_identity
from publisher_reliability.model_scan_cache import CACHE_FILENAME
from publisher_reliability.model_scanner import CHECKPOINT_SHAPES, scan_model_roots
from publisher_reliability.storage import HEADERS, Storage


class ModelScannerTest(unittest.TestCase):
    def test_scan_restores_custom_bundle_availability(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with Storage(root / "data") as storage:
                bundle = storage.data_dir / "managed-models" / "custom-model"
                bundle.mkdir()
                (bundle / "config.json").write_text("{}", encoding="utf-8")
                digest = directory_identity(bundle)[0]
                model = {field: "" for field in HEADERS["models"]}
                model.update(
                    model_id="custom-model",
                    family="custom_example",
                    fold_id=1,
                    display_name="Custom example",
                    artifact_kind="custom_transformer_bundle",
                    artifact_locator="managed-models/custom-model",
                    artifact_sha256=digest,
                    loader_recipe="custom_auto_sequence_classification_safetensors",
                    loader_recipe_version=2,
                    class_order_json="[0,1,2,3,4]",
                    max_tokens=256,
                    padding_policy="fixed_max_length",
                    runtime_scientific_json="{}",
                    status="artifact_missing",
                    artifact_available=False,
                    runnable=False,
                    registered_at="2026-07-24T00:00:00Z",
                    last_validated_at="2026-07-24T00:00:00Z",
                )
                storage.upsert("models", "model_id", model)

                scan_model_roots(storage, ())

                restored = storage.rows["models"][0]
                self.assertEqual(restored["status"], "compatible")
                self.assertEqual(restored["artifact_available"], "true")
                self.assertEqual(restored["runnable"], "true")

                (bundle / "unsafe-link").symlink_to(bundle / "config.json")
                scan_model_roots(storage, ())
                invalid = storage.rows["models"][0]
                self.assertEqual(invalid["status"], "invalid")
                self.assertEqual(invalid["artifact_available"], "false")
                self.assertEqual(invalid["runnable"], "false")

    def test_scan_registers_only_recognized_validated_checkpoints(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            models = root / "models"
            models.mkdir()
            (models / "bert_fold_1.pt").write_bytes(b"checkpoint")
            (models / "renamed.pt").write_bytes(b"ignored")

            with Storage(root / "data") as storage:
                with (
                    patch(
                        "publisher_reliability.model_scanner._sha256_file",
                        return_value="a" * 64,
                    ),
                    patch(
                        "publisher_reliability.model_scanner._validate_checkpoint",
                        return_value=(201, 109_486_085),
                    ),
                ):
                    result = scan_model_roots(storage, (models,))

                self.assertEqual(result["registered"], 1)
                self.assertEqual(result["rejected"], [])
                self.assertEqual(len(storage.rows["models"]), 1)
                model = storage.rows["models"][0]
                self.assertEqual(model["family"], "bert")
                self.assertEqual(model["fold_id"], "1")
                self.assertEqual(model["artifact_locator"], "root-1/bert_fold_1.pt")
                self.assertEqual(model["artifact_available"], "true")
                self.assertEqual(model["status"], "compatible")
                self.assertEqual(model["runnable"], "true")


class ScanCacheTest(unittest.TestCase):
    """The cache must save work without ever weakening what a scan asserts."""

    def setUp(self) -> None:
        self.verifications: list[Path] = []

    def _scan(self, storage: Storage, models: Path, *, digest: str = "a" * 64, **kwargs):
        """Scan with verification stubbed out, recording which files were verified."""

        def verify(path: Path, family: str) -> tuple[int, int]:
            self.verifications.append(path)
            return (201, 109_486_085)

        with (
            patch(
                "publisher_reliability.model_scanner._sha256_file",
                return_value=digest,
            ),
            patch(
                "publisher_reliability.model_scanner._validate_checkpoint",
                side_effect=verify,
            ),
        ):
            return scan_model_roots(storage, (models,), **kwargs)

    def test_unchanged_checkpoint_reuses_the_previous_verification(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            models = root / "models"
            models.mkdir()
            (models / "bert_fold_1.pt").write_bytes(b"checkpoint")

            with Storage(root / "data") as storage:
                self._scan(storage, models)
                first = dict(storage.rows["models"][0])
                self.assertEqual(len(self.verifications), 1)

                result = self._scan(storage, models)

                # Nothing was read a second time, and the registered identity is the same.
                self.assertEqual(len(self.verifications), 1)
                self.assertEqual(result["reused_from_cache"], 1)
                self.assertEqual(result["registered"], 1)
                self.assertEqual(
                    storage.rows["models"][0]["artifact_sha256"],
                    first["artifact_sha256"],
                )
                self.assertTrue((storage.data_dir / CACHE_FILENAME).exists())

    def test_modified_checkpoint_is_verified_again(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            models = root / "models"
            models.mkdir()
            checkpoint = models / "bert_fold_1.pt"
            checkpoint.write_bytes(b"checkpoint")

            with Storage(root / "data") as storage:
                self._scan(storage, models)
                checkpoint.write_bytes(b"a different checkpoint entirely")

                result = self._scan(storage, models, digest="b" * 64)

                self.assertEqual(len(self.verifications), 2)
                self.assertEqual(result["reused_from_cache"], 0)
                self.assertEqual(storage.rows["models"][0]["artifact_sha256"], "b" * 64)

    def test_full_scan_ignores_the_cache(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            models = root / "models"
            models.mkdir()
            (models / "bert_fold_1.pt").write_bytes(b"checkpoint")

            with Storage(root / "data") as storage:
                self._scan(storage, models)
                result = self._scan(storage, models, full=True)

                self.assertEqual(len(self.verifications), 2)
                self.assertEqual(result["reused_from_cache"], 0)

    def test_stricter_validation_rules_discard_the_cache(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            models = root / "models"
            models.mkdir()
            (models / "bert_fold_1.pt").write_bytes(b"checkpoint")

            with Storage(root / "data") as storage:
                self._scan(storage, models)

                # A checkpoint accepted under the old rules must not stay accepted
                # merely because it was cached before the rules were tightened.
                with patch.dict(CHECKPOINT_SHAPES["bert"], {"tensor_count": 202}):
                    result = self._scan(storage, models)

                self.assertEqual(len(self.verifications), 2)
                self.assertEqual(result["reused_from_cache"], 0)

    def test_rejected_checkpoint_is_never_remembered(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            models = root / "models"
            models.mkdir()
            (models / "bert_fold_1.pt").write_bytes(b"checkpoint")

            with Storage(root / "data") as storage:
                with (
                    patch(
                        "publisher_reliability.model_scanner._sha256_file",
                        return_value="a" * 64,
                    ),
                    patch(
                        "publisher_reliability.model_scanner._validate_checkpoint",
                        side_effect=ValueError("Unexpected tensor count."),
                    ) as validate,
                ):
                    first = scan_model_roots(storage, (models,))
                    second = scan_model_roots(storage, (models,))

                self.assertEqual(validate.call_count, 2)
                self.assertEqual(len(first["rejected"]), 1)
                self.assertEqual(len(second["rejected"]), 1)
                self.assertEqual(second["reused_from_cache"], 0)

    def test_corrupt_cache_file_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            models = root / "models"
            models.mkdir()
            (models / "bert_fold_1.pt").write_bytes(b"checkpoint")

            with Storage(root / "data") as storage:
                (storage.data_dir / CACHE_FILENAME).write_text("{not json", encoding="utf-8")

                result = self._scan(storage, models)

                self.assertEqual(result["registered"], 1)
                self.assertEqual(result["reused_from_cache"], 0)


class ReferencedModelRetentionTest(unittest.TestCase):
    """A scan may never orphan a prediction run by deleting the model it names.

    ``Storage`` refuses to reload a ledger whose runs point at a model that is gone,
    and the startup mirror sync refuses for the same reason. So a scan that drops a
    still-referenced row does not merely lose a table entry: it makes the whole
    workspace impossible to open again, with no way back short of editing CSVs by
    hand.
    """

    def _scan(self, storage: Storage, models: Path, digest: str):
        with (
            patch(
                "publisher_reliability.model_scanner._sha256_file",
                return_value=digest,
            ),
            patch(
                "publisher_reliability.model_scanner._validate_checkpoint",
                return_value=(201, 109_486_085),
            ),
        ):
            return scan_model_roots(storage, (models,))

    @staticmethod
    def _local_run(model_id: str) -> dict[str, object]:
        run = {field: "" for field in HEADERS["prediction_runs"]}
        run.update(
            prediction_run_id="run-1",
            article_id="article-1",
            canonical_url="https://outlet.example/a",
            publisher_id="publisher-1",
            normalized_hostname="outlet.example",
            model_id=model_id,
            predicted_class=3,
            origin="local_inference",
            action="missing_run_inference",
            input_source="https://outlet.example/a",
            content_retention="discard",
            software_versions_json="{}",
            recorded_at="2026-07-24T00:00:00Z",
        )
        for index in range(5):
            run[f"prob_class_{index}"] = "0.6" if index == 3 else "0.1"
        return run

    def test_renaming_a_checkpoint_keeps_the_model_its_predictions_name(self) -> None:
        # The same bytes under a new fold name are a new identity, so the old model_id
        # disappears from the scan while the run that used it does not.
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            models = root / "models"
            models.mkdir()
            (models / "bert_fold_1.pt").write_bytes(b"checkpoint")

            with Storage(root / "data") as storage:
                self._scan(storage, models, "a" * 64)
                original_id = storage.rows["models"][0]["model_id"]
                storage.append("prediction_runs", self._local_run(original_id))

                (models / "bert_fold_1.pt").rename(models / "bert_fold_3.pt")
                self._scan(storage, models, "a" * 64)

                by_id = {row["model_id"]: row for row in storage.rows["models"]}
                self.assertIn(original_id, by_id)
                self.assertEqual(by_id[original_id]["status"], "artifact_missing")
                self.assertEqual(by_id[original_id]["artifact_available"], "false")
                self.assertEqual(by_id[original_id]["runnable"], "false")
                # The new identity is registered alongside it, not instead of it.
                self.assertEqual(len(by_id), 2)
                # The decisive assertion: the workspace can still be opened.
                storage.reload()

    def test_an_unreferenced_renamed_checkpoint_is_still_dropped(self) -> None:
        # Nothing points at the old identity, so keeping it would only clutter the
        # models page with a checkpoint the user deliberately renamed.
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            models = root / "models"
            models.mkdir()
            (models / "bert_fold_1.pt").write_bytes(b"checkpoint")

            with Storage(root / "data") as storage:
                self._scan(storage, models, "a" * 64)
                original_id = storage.rows["models"][0]["model_id"]

                (models / "bert_fold_1.pt").rename(models / "bert_fold_3.pt")
                self._scan(storage, models, "a" * 64)

                by_id = {row["model_id"]: row for row in storage.rows["models"]}
                self.assertNotIn(original_id, by_id)
                self.assertEqual(len(by_id), 1)
                self.assertEqual(next(iter(by_id.values()))["fold_id"], "3")

    def test_a_deleted_checkpoint_is_still_reported_as_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            models = root / "models"
            models.mkdir()
            (models / "bert_fold_1.pt").write_bytes(b"checkpoint")

            with Storage(root / "data") as storage:
                self._scan(storage, models, "a" * 64)
                original_id = storage.rows["models"][0]["model_id"]

                (models / "bert_fold_1.pt").unlink()
                self._scan(storage, models, "a" * 64)

                remaining = storage.rows["models"][0]
                self.assertEqual(remaining["model_id"], original_id)
                self.assertEqual(remaining["status"], "artifact_missing")

    def test_a_restored_placeholder_gives_way_to_the_returning_artifact(self) -> None:
        """A checkpoint that comes back must not collide with its own placeholder.

        ``data/`` is disposable by design, and a local checkpoint's model_id is
        derived from its digest, family and fold, so it is identical before and
        after. If the artifact is absent when the mirror is restored,
        ``restore_user_predictions`` recreates that exact id as a historical
        placeholder. Should the artifact then reappear, a scan registers the same id
        as a local row, and emitting both writes a duplicate identifier that no later
        reload accepts -- leaving the workspace impossible to open.
        """

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            models = root / "models"
            models.mkdir()
            checkpoint = models / "bert_fold_1.pt"
            checkpoint.write_bytes(b"checkpoint")

            with Storage(root / "data") as storage:
                self._scan(storage, models, "a" * 64)
                model_id = storage.rows["models"][0]["model_id"]

                # Stand in for the placeholder restore_user_predictions would write
                # for a run whose checkpoint is missing: same id, historical kind.
                placeholder = {field: "" for field in HEADERS["models"]}
                placeholder.update(
                    model_id=model_id,
                    family="bert",
                    fold_id=1,
                    display_name="BERT fold 1 (local checkpoint)",
                    artifact_kind="historical_virtual",
                    loader_recipe="restored_user_prediction",
                    loader_recipe_version=1,
                    class_order_json="[0,1,2,3,4]",
                    runtime_scientific_json="{}",
                    status="historical_only",
                    artifact_available=False,
                    runnable=False,
                    registered_at="2026-07-24T00:00:00Z",
                    last_validated_at="2026-07-24T00:00:00Z",
                )
                storage.replace("models", [placeholder])

                # The artifact is present again, so this scan rediscovers the same id.
                self._scan(storage, models, "a" * 64)

                rows = storage.rows["models"]
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["model_id"], model_id)
                # The real artifact wins: it can actually run, the placeholder cannot.
                self.assertEqual(rows[0]["artifact_kind"], "pytorch_state_dict")
                self.assertEqual(rows[0]["runnable"], "true")
                storage.reload()

    def test_an_unrelated_historical_identity_is_untouched(self) -> None:
        # Imported dataset identities are hashed from a different identity document,
        # so they never collide with a scanned checkpoint and must always survive.
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            models = root / "models"
            models.mkdir()
            (models / "bert_fold_1.pt").write_bytes(b"checkpoint")

            with Storage(root / "data") as storage:
                imported = {field: "" for field in HEADERS["models"]}
                imported.update(
                    model_id="imported-dataset-identity",
                    family="roberta",
                    fold_id=4,
                    display_name="ROBERTA fold 4 (historical)",
                    artifact_kind="historical_virtual",
                    loader_recipe="historical_import",
                    loader_recipe_version=1,
                    class_order_json="[0,1,2,3,4]",
                    runtime_scientific_json="{}",
                    status="historical_only",
                    artifact_available=False,
                    runnable=False,
                    registered_at="2026-07-24T00:00:00Z",
                    last_validated_at="2026-07-24T00:00:00Z",
                )
                storage.replace("models", [imported])

                self._scan(storage, models, "a" * 64)

                ids = {row["model_id"] for row in storage.rows["models"]}
                self.assertIn("imported-dataset-identity", ids)
                self.assertEqual(len(ids), 2)


if __name__ == "__main__":
    unittest.main()
