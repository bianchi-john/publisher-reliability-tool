import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from publisher_reliability.custom_models import directory_identity
from publisher_reliability.model_scanner import scan_model_roots
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


if __name__ == "__main__":
    unittest.main()
