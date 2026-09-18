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
    def test_allowlist_is_closed_against_non_encoder_architectures(self) -> None:
        """Only the listed encoder architectures load; the allowlist is not advisory.

        Decoder and sequence-to-sequence families are refused because they are absent
        from it, so the guarantee holds for any architecture nobody thought to name.
        """

        for model_type in ("gpt2", "falcon", "t5"):
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

    def test_refuses_any_bundle_that_is_not_a_five_class_encoder(self) -> None:
        """Only the five-class encoder bundle exists; anything else is invalid input.

        An adapter bundle was once a second supported schema. That path is gone, so a
        bundle declaring it must be refused by the manifest check as malformed, not
        deferred as an unfinished feature, and nothing may be installed.
        """

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "withdrawn-schema.zip"
            # The schema is checked first, so nothing else in the manifest matters:
            # a bundle written for the withdrawn contract never reaches the rest.
            manifest = {
                "schema_version": 2,
                "model_kind": "peft_sequence_classifier",
                "architecture": "gpt2",
                "display_name": "Adapter bundle for a withdrawn schema",
                "family": "custom_adapter_experiment",
                "fold_id": 3,
                "class_order": [0, 1, 2, 3, 4],
                "max_tokens": 1024,
                "padding_policy": "dynamic_longest",
                "base_model": "example-org/example-base",
                "base_revision": "a" * 40,
                "training_data": {"kind": "five_fold", "held_out_fold": 3},
            }
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("prt-model.json", json.dumps(manifest))
                archive.writestr("adapter_config.json", "{}")
                archive.writestr("adapter_model.safetensors", b"safe-placeholder")
                archive.writestr("tokenizer_config.json", "{}")
                archive.writestr("tokenizer.json", "{}")

            with Storage(root / "data") as storage:
                with self.assertRaises(AppError) as refused:
                    import_custom_transformer_bundle(
                        storage,
                        source,
                        max_uncompressed_bytes=1024 * 1024,
                    )
                # The adapter contract is gone: only schema 1 encoder bundles exist,
                # so this is an invalid bundle rather than a deferred feature.
                self.assertEqual(refused.exception.code, "INVALID_INPUT")
                self.assertIn("schema_version 1", refused.exception.message)
                self.assertEqual(storage.rows["models"], [])


if __name__ == "__main__":
    unittest.main()
