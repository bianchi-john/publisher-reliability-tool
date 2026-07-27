import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from publisher_reliability.custom_models import (
    _require_supported_model_type,
    _safe_extract,
    import_custom_transformer_bundle,
)
from publisher_reliability.errors import AppError
from publisher_reliability.storage import Storage


class CustomModelImportTest(unittest.TestCase):
    def test_rejects_decoder_only_llm_architectures(self) -> None:
        for model_type in ("llama", "mistral", "mixtral"):
            with self.subTest(model_type=model_type):
                with self.assertRaises(AppError) as raised:
                    _require_supported_model_type(model_type)
                self.assertEqual(raised.exception.code, "INVALID_INPUT")
        self.assertEqual(_require_supported_model_type("deberta-v2"), "deberta-v2")

    def test_rejects_zip_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "unsafe.zip"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("../outside.json", "{}")
            destination = root / "output"
            destination.mkdir()
            with self.assertRaises(AppError) as raised:
                _safe_extract(
                    source,
                    destination,
                    max_uncompressed_bytes=1024,
                )
            self.assertEqual(raised.exception.code, "INVALID_INPUT")
            self.assertFalse((root / "outside.json").exists())

    def test_imports_validated_custom_transformer_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "custom.zip"
            manifest = {
                "schema_version": 1,
                "display_name": "Custom News Classifier",
                "family": "custom_news",
                "fold_id": 2,
                "class_order": [0, 1, 2, 3, 4],
                "max_tokens": 256,
                "padding_policy": "fixed_max_length",
                "base_model": "local-test-model",
                "base_revision": "test-revision",
                "training_data": {"kind": "five_fold", "held_out_fold": 2},
            }
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("prt-model.json", json.dumps(manifest))
                archive.writestr("config.json", '{"model_type":"bert","num_labels":5}')
                archive.writestr("tokenizer_config.json", '{"tokenizer_class":"BertTokenizer"}')
                archive.writestr("vocab.txt", "[PAD]\n[UNK]\n[CLS]\n[SEP]\n[MASK]\n")
                archive.writestr("model.safetensors", b"safe-placeholder")

            with Storage(root / "data") as storage:
                with patch(
                    "publisher_reliability.custom_models._validate_transformer",
                    return_value={
                        "architecture": "BertForSequenceClassification",
                        "model_type": "bert",
                        "parameter_count": 100,
                        "tensor_count": 10,
                    },
                ):
                    result = import_custom_transformer_bundle(
                        storage,
                        source,
                        max_uncompressed_bytes=1024 * 1024,
                    )

                self.assertEqual(result["family"], "custom_news")
                self.assertEqual(result["fold_id"], 2)
                self.assertEqual(len(storage.rows["models"]), 1)
                model = storage.rows["models"][0]
                self.assertEqual(model["artifact_kind"], "custom_transformer_bundle")
                self.assertEqual(model["artifact_available"], "true")
                self.assertEqual(model["status"], "compatible")
                self.assertEqual(model["runnable"], "true")
                installed = storage.data_dir / model["artifact_locator"]
                self.assertTrue((installed / "model.safetensors").is_file())
                self.assertTrue((installed / "prt-model.json").is_file())


if __name__ == "__main__":
    unittest.main()
