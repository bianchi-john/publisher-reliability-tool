import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from publisher_reliability.model_scanner import scan_model_roots
from publisher_reliability.storage import Storage


class ModelScannerTest(unittest.TestCase):
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
