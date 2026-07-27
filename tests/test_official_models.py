import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from publisher_reliability.official_models import (
    import_official_model,
    verify_managed_model,
)
from publisher_reliability.storage import Storage


class OfficialModelImportTest(unittest.TestCase):
    def test_authenticates_and_marks_paper_mistral_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "uploaded-token"
            adapter = {
                "base_model_name_or_path": "mistralai/Mistral-Small-24B-Base-2501",
                "peft_type": "LORA",
                "task_type": "SEQ_CLS",
                "r": 16,
                "lora_alpha": 32,
                "target_modules": ["q_proj", "k_proj", "v_proj", "o_proj"],
            }
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("fold_1/adapter_config.json", json.dumps(adapter))
                archive.writestr("fold_1/adapter_model.safetensors", b"safe")
                archive.writestr("fold_1/tokenizer_config.json", "{}")
                archive.writestr("fold_1/tokenizer.json", "{}")
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            entry = {
                "family": "mistral",
                "fold_id": 1,
                "display_name": "Mistral 24B — paper original — fold 1",
                "artifact_format": "peft_adapter_zip",
                "loader_recipe": "paper_mistral_24b_qlora_adapter",
                "loader_recipe_version": "1",
                "base_model": "mistralai/Mistral-Small-24B-Base-2501",
                "base_revision": "b" * 40,
                "tokenizer_source": "local_adapter_bundle",
                "tokenizer_revision": "osf-archive",
                "max_tokens": 1024,
                "padding_policy": "dynamic_longest",
                "recipe": {
                    "quantization": "bitsandbytes-nf4-double-quant-bfloat16",
                    "lora_r": 16,
                    "lora_alpha": 32,
                    "lora_dropout": 0.0,
                    "target_modules": ["q_proj", "k_proj", "v_proj", "o_proj"],
                },
                "files": [
                    {
                        "name": "mistral_fold_1.zip",
                        "size": source.stat().st_size,
                        "sha256": digest,
                        "download_url": "https://osf.example/file",
                    }
                ],
            }
            manifest = {"schema_version": 1, "models": [entry]}

            with Storage(root / "data") as storage:
                with (
                    patch(
                        "publisher_reliability.official_models.official_manifest",
                        return_value=manifest,
                    ),
                    patch(
                        "publisher_reliability.official_models.llm_runtime_status",
                        return_value=("resource_unavailable", False, "CUDA required."),
                    ),
                ):
                    result = import_official_model(
                        storage,
                        [source],
                        source_names=["mistral_fold_1.zip"],
                        max_uncompressed_bytes=1024 * 1024,
                    )

                model = storage.rows["models"][0]
                self.assertEqual(result["provenance"], "paper_official")
                self.assertEqual(model["artifact_kind"], "paper_mistral_adapter_bundle")
                self.assertTrue(model["official_manifest_entry_sha256"])
                self.assertEqual(model["status"], "resource_unavailable")
                self.assertEqual(model["runnable"], "false")
                self.assertEqual(verify_managed_model(storage, model), (True, ""))


if __name__ == "__main__":
    unittest.main()
