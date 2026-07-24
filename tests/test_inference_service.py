import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from publisher_reliability.inference import (
    ENGLISH_REQUEST_HEADERS,
    Prediction,
    RetrievedArticle,
    extract_english_article,
)
from publisher_reliability.errors import AppError
from publisher_reliability.services import ResearchService
from publisher_reliability.storage import HEADERS, Storage


class FakeInferenceEngine:
    def predict(self, _model: dict[str, str], text: str) -> Prediction:
        if "article body" not in text:
            raise AssertionError("unexpected extracted text")
        return Prediction(
            predicted_class=2,
            probabilities=(0.05, 0.1, 0.7, 0.1, 0.05),
            device="cpu",
            software_versions={"test": "1"},
        )


class InferenceServiceTest(unittest.TestCase):
    def test_newspaper_is_configured_for_english(self) -> None:
        captured: dict[str, object] = {}

        class FakeArticle:
            def __init__(self, url: str, *, language: str):
                captured.update(url=url, language=language)
                self.text = "English article body " * 40
                self.title = "Example title"

            def set_html(self, _html: str) -> None:
                return None

            def parse(self) -> None:
                return None

        html = b"<html lang='en'><body><article><p>English article body.</p></article></body></html>"
        with patch("newspaper.Article", FakeArticle):
            result = extract_english_article(html, "https://example.com/article")

        self.assertEqual(captured["language"], "en")
        self.assertEqual(
            ENGLISH_REQUEST_HEADERS["Accept-Language"],
            "en-US,en;q=0.9",
        )
        self.assertEqual(result.title, "Example title")

    def test_newspaper_failure_has_no_secondary_extractor(self) -> None:
        class FailingArticle:
            def __init__(self, _url: str, *, language: str):
                self.text = ""
                self.title = ""

            def set_html(self, _html: str) -> None:
                return None

            def parse(self) -> None:
                raise ValueError("unsupported layout")

        with patch("newspaper.Article", FailingArticle):
            with self.assertRaises(AppError) as raised:
                extract_english_article(
                    b"<html><body><p>Secondary text must not be used.</p></body></html>",
                    "https://example.com/live",
                )

        self.assertEqual(raised.exception.code, "EXTRACTION_FAILED")

    def test_unknown_article_is_available_and_creates_local_run(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with Storage(root / "data") as storage:
                model = {field: "" for field in HEADERS["models"]}
                model.update(
                    model_id="local-bert-fold-1",
                    family="bert",
                    fold_id=1,
                    display_name="BERT fold 1",
                    artifact_kind="pytorch_state_dict",
                    artifact_locator="root-1/bert_fold_1.pt",
                    artifact_sha256="a" * 64,
                    loader_recipe="bert_state_dict",
                    loader_recipe_version=2,
                    base_model="google-bert/bert-base-uncased",
                    base_revision="revision",
                    tokenizer_source="google-bert/bert-base-uncased",
                    tokenizer_revision="revision",
                    class_order_json="[0,1,2,3,4]",
                    max_tokens=256,
                    padding_policy="fixed_max_length",
                    runtime_scientific_json="{}",
                    status="compatible",
                    artifact_available=True,
                    runnable=True,
                    status_detail="ready",
                    registered_at="2026-07-24T00:00:00Z",
                    last_validated_at="2026-07-24T00:00:00Z",
                )
                storage.upsert("models", "model_id", model)
                service = ResearchService(
                    storage,
                    inference_engine=FakeInferenceEngine(),
                )

                availability = service.available_models(
                    input_type="article",
                    url="https://example.com/new",
                )
                self.assertEqual(availability["availability"]["code"], "AVAILABLE")
                self.assertEqual(availability["items"][0]["mode"], "new_inference")
                self.assertTrue(availability["items"][0]["eligible"])

                retrieved = RetrievedArticle(
                    canonical_url="https://example.com/new",
                    title="Example",
                    text="English article body " * 40,
                )
                with patch(
                    "publisher_reliability.services.fetch_article",
                    return_value=retrieved,
                ):
                    result = service.evaluate(
                        {
                            "input": {
                                "type": "article",
                                "url": "https://example.com/new",
                            },
                            "model_id": model["model_id"],
                            "prediction_action": "reuse",
                            "content_retention": "discard",
                        },
                        "inference-job",
                    )

                self.assertFalse(result["reused"])
                self.assertEqual(result["predicted_class"], 2)
                self.assertEqual(result["probabilities"], [0.05, 0.1, 0.7, 0.1, 0.05])
                self.assertEqual(result["family"], "bert")
                self.assertEqual(result["fold_id"], 1)
                self.assertEqual(result["origin"], "local_inference")
                self.assertEqual(len(storage.rows["prediction_runs"]), 1)
                run = storage.rows["prediction_runs"][0]
                self.assertEqual(run["origin"], "local_inference")
                self.assertEqual(run["model_id"], model["model_id"])
                self.assertEqual(run["job_id"], "inference-job")
                summary = service.article_summaries()[0]
                self.assertEqual(summary["source_type"], "user_evaluation")
                self.assertEqual(summary["dataset_run_count"], 0)
                self.assertEqual(summary["local_run_count"], 1)
                self.assertTrue(summary["has_user_evaluation"])
                self.assertEqual(
                    service.article_summaries(article_source="dataset"),
                    [],
                )


if __name__ == "__main__":
    unittest.main()
