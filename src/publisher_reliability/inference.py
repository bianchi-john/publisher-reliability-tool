"""Safe article retrieval and local Transformers inference."""

from __future__ import annotations

import gc
import importlib.metadata
import ipaddress
import json
import re
import socket
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import httpx

from . import __version__
from .errors import AppError
from .identity import normalize_url
from .storage import Storage


CORE_MODELS = {
    "bert": {
        "base_model": "google-bert/bert-base-uncased",
        "revision": "86b5e0934494bd15c9632b12f734a8a67f723594",
    },
    "roberta": {
        "base_model": "FacebookAI/roberta-large",
        "revision": "722cf37b1afa9454edce342e7895e588b6ff1d59",
    },
}
ROOT_LOCATOR = re.compile(r"root-([1-9][0-9]*)/(.+)")
MAX_HTML_BYTES = 8 * 1024 * 1024
MAX_REDIRECTS = 5


@dataclass(frozen=True, slots=True)
class RetrievedArticle:
    canonical_url: str
    title: str
    text: str


@dataclass(frozen=True, slots=True)
class Prediction:
    predicted_class: int
    probabilities: tuple[float, float, float, float, float]
    device: str
    software_versions: dict[str, str | None]


def _require_public_destination(canonical_url: str) -> None:
    parts = urlsplit(canonical_url)
    hostname = parts.hostname
    if hostname is None:
        raise AppError("INVALID_URL", "URL has no hostname.")
    port = parts.port or (443 if parts.scheme == "https" else 80)
    try:
        records = socket.getaddrinfo(
            hostname,
            port,
            family=socket.AF_UNSPEC,
            type=socket.SOCK_STREAM,
        )
    except OSError as exc:
        raise AppError("NETWORK_ERROR", "Article hostname could not be resolved.") from exc
    addresses = {
        ipaddress.ip_address(record[4][0].split("%", 1)[0])
        for record in records
    }
    if not addresses or any(not address.is_global for address in addresses):
        raise AppError(
            "INVALID_URL",
            "Article URL resolves to a private, local, or reserved address.",
        )


def _response_bytes(response: httpx.Response) -> bytes:
    content_type = response.headers.get("content-type", "").lower()
    if content_type and "text/html" not in content_type and "application/xhtml" not in content_type:
        raise AppError("EXTRACTION_FAILED", "Article response is not HTML.")
    output = bytearray()
    for block in response.iter_bytes():
        output.extend(block)
        if len(output) > MAX_HTML_BYTES:
            raise AppError("PAYLOAD_TOO_LARGE", "Article HTML exceeds 8 MiB.")
    return bytes(output)


def fetch_article(raw_url: str, *, offline: bool = False) -> RetrievedArticle:
    """Retrieve one public page and extract stable visible article text."""

    if offline:
        raise AppError("NETWORK_REQUIRED", "Article retrieval is disabled offline.")
    current = normalize_url(raw_url)
    headers = {
        "Accept": "text/html,application/xhtml+xml",
        "User-Agent": "PublisherReliabilityTool/0.1 local-research",
    }
    try:
        with httpx.Client(
            follow_redirects=False,
            timeout=httpx.Timeout(20.0, connect=10.0),
            trust_env=False,
            headers=headers,
        ) as client:
            for redirect_count in range(MAX_REDIRECTS + 1):
                _require_public_destination(current)
                with client.stream("GET", current) as response:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        location = response.headers.get("location")
                        if not location:
                            raise AppError(
                                "NETWORK_ERROR",
                                "Article redirect has no destination.",
                            )
                        if redirect_count == MAX_REDIRECTS:
                            raise AppError(
                                "NETWORK_ERROR",
                                "Article exceeded the redirect limit.",
                            )
                        current = normalize_url(urljoin(current, location))
                        continue
                    if response.status_code >= 400:
                        raise AppError(
                            "NETWORK_ERROR",
                            f"Article server returned HTTP {response.status_code}.",
                        )
                    html = _response_bytes(response)
                    final_url = normalize_url(str(response.url))
                    break
            else:  # pragma: no cover - loop always breaks or raises
                raise AppError("NETWORK_ERROR", "Article retrieval did not complete.")
    except AppError:
        raise
    except httpx.HTTPError as exc:
        raise AppError("NETWORK_ERROR", "Article could not be retrieved.") from exc

    try:
        from bs4 import BeautifulSoup
        from langdetect import DetectorFactory, LangDetectException, detect
    except ImportError as exc:
        raise AppError(
            "MODEL_NOT_RUNNABLE",
            "Install the project 'models' extra to extract article text.",
        ) from exc

    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception as exc:
        raise AppError("EXTRACTION_FAILED", "Article HTML could not be parsed.") from exc
    for node in soup.select("script,style,noscript,svg,nav,footer,aside"):
        node.decompose()

    def block_text(nodes: list[object]) -> str:
        parts: list[str] = []
        for node in nodes:
            blocks = node.select("h1,h2,h3,p,li")
            values = blocks or [node]
            for block in values:
                value = " ".join(block.get_text(" ", strip=True).split())
                if value and (not parts or value != parts[-1]):
                    parts.append(value)
        return "\n\n".join(parts)

    article_nodes = list(soup.select("article"))
    text = block_text(article_nodes)
    if len(text.strip()) < 200:
        text = block_text(list(soup.select("main")))
    if len(text.strip()) < 200:
        text = block_text(list(soup.select("p")))
    stripped = text.strip()
    if len(stripped) < 200 or len(stripped.split()) < 30:
        raise AppError(
            "TEXT_TOO_SHORT",
            "Extracted article text is shorter than 200 characters or 30 words.",
        )

    title_node = soup.select_one('meta[property="og:title"]')
    title = (
        str(title_node.get("content", "")).strip()
        if title_node is not None
        else ""
    )
    if not title:
        heading = soup.select_one("h1")
        title = " ".join(heading.get_text(" ", strip=True).split()) if heading else ""

    DetectorFactory.seed = 0
    try:
        language = detect(stripped)
    except LangDetectException as exc:
        raise AppError("NON_ENGLISH", "Article language could not be determined.") from exc
    if language != "en":
        raise AppError(
            "NON_ENGLISH",
            f"Article language is '{language}', but the models require English.",
        )
    return RetrievedArticle(final_url, title, stripped)


class InferenceEngine:
    """Load at most one exact local model and run deterministic inference."""

    def __init__(
        self,
        storage: Storage,
        *,
        model_roots: tuple[Path, ...] = (),
        offline: bool = False,
        device: str = "auto",
    ):
        self.storage = storage
        self.model_roots = tuple(path.resolve() for path in model_roots)
        self.offline = offline
        self.device = device
        self._loaded_model_id = ""
        self._model = None
        self._tokenizer = None
        self._loaded_device = "cpu"

    def _artifact_path(self, model: dict[str, str]) -> Path:
        if model["artifact_kind"] == "custom_transformer_bundle":
            path = (self.storage.data_dir / model["artifact_locator"]).resolve()
            managed = (self.storage.data_dir / "managed-models").resolve()
            if path.parent != managed or not path.is_dir() or path.is_symlink():
                raise AppError("MODEL_NOT_AVAILABLE", "Custom model bundle is missing.")
            return path
        match = ROOT_LOCATOR.fullmatch(model["artifact_locator"])
        if match is None:
            raise AppError("MODEL_NOT_AVAILABLE", "Model artifact locator is invalid.")
        root_index = int(match.group(1)) - 1
        if root_index not in range(len(self.model_roots)):
            raise AppError("MODEL_NOT_AVAILABLE", "Model root is no longer configured.")
        root = self.model_roots[root_index]
        path = (root / match.group(2)).resolve()
        if path.parent != root or not path.is_file() or path.is_symlink():
            raise AppError("MODEL_NOT_AVAILABLE", "Model checkpoint is missing.")
        return path

    @staticmethod
    def _materialize_transformer_buffers(model: object, config: object) -> None:
        base = getattr(model, "bert", None) or getattr(model, "roberta", None)
        if base is None:
            return
        embeddings = base.embeddings
        import torch

        embeddings.register_buffer(
            "position_ids",
            torch.arange(config.max_position_embeddings).expand((1, -1)),
            persistent=False,
        )
        if hasattr(embeddings, "token_type_ids"):
            embeddings.register_buffer(
                "token_type_ids",
                torch.zeros(
                    (1, config.max_position_embeddings),
                    dtype=torch.long,
                ),
                persistent=False,
            )

    def _selected_device(self, torch: object) -> str:
        if self.device == "cuda":
            if not torch.cuda.is_available():
                raise AppError("MODEL_NOT_RUNNABLE", "CUDA was requested but is unavailable.")
            return "cuda"
        if self.device == "auto" and torch.cuda.is_available():
            return "cuda"
        return "cpu"

    def _load(self, model_row: dict[str, str]) -> tuple[object, object, str]:
        if self._loaded_model_id == model_row["model_id"]:
            return self._model, self._tokenizer, self._loaded_device
        try:
            import torch
            from transformers import (
                AutoModelForSequenceClassification,
                AutoTokenizer,
                BertConfig,
                BertForSequenceClassification,
                RobertaConfig,
                RobertaForSequenceClassification,
            )
        except ImportError as exc:
            raise AppError(
                "MODEL_NOT_RUNNABLE",
                "Install the project 'models' extra to run local inference.",
            ) from exc

        self._model = None
        self._tokenizer = None
        self._loaded_model_id = ""
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        path = self._artifact_path(model_row)
        family = model_row["family"]
        try:
            if model_row["artifact_kind"] == "custom_transformer_bundle":
                tokenizer = AutoTokenizer.from_pretrained(
                    path,
                    local_files_only=True,
                    trust_remote_code=False,
                )
                loaded_model = AutoModelForSequenceClassification.from_pretrained(
                    path,
                    local_files_only=True,
                    trust_remote_code=False,
                    use_safetensors=True,
                )
            elif family in CORE_MODELS:
                recipe = CORE_MODELS[family]
                dependency_cache = self.storage.data_dir / "model-dependencies"
                dependency_cache.mkdir(exist_ok=True)
                tokenizer = AutoTokenizer.from_pretrained(
                    recipe["base_model"],
                    revision=recipe["revision"],
                    cache_dir=dependency_cache,
                    local_files_only=self.offline,
                    trust_remote_code=False,
                )
                if family == "bert":
                    config = BertConfig(num_labels=5)
                    model_class = BertForSequenceClassification
                else:
                    config = RobertaConfig(
                        vocab_size=50265,
                        hidden_size=1024,
                        num_hidden_layers=24,
                        num_attention_heads=16,
                        intermediate_size=4096,
                        max_position_embeddings=514,
                        type_vocab_size=1,
                        num_labels=5,
                    )
                    model_class = RobertaForSequenceClassification
                with torch.device("meta"):
                    loaded_model = model_class(config)
                state = torch.load(
                    path,
                    map_location="cpu",
                    weights_only=True,
                    mmap=True,
                )
                loaded_model.load_state_dict(state, strict=True, assign=True)
                self._materialize_transformer_buffers(loaded_model, config)
            else:
                raise AppError(
                    "MODEL_NOT_RUNNABLE",
                    "No inference loader is registered for this model family.",
                )
        except AppError:
            raise
        except OSError as exc:
            code = "NETWORK_REQUIRED" if self.offline else "NETWORK_ERROR"
            raise AppError(
                code,
                "The pinned tokenizer is unavailable locally."
                if self.offline
                else "The pinned tokenizer could not be acquired.",
            ) from exc
        except Exception as exc:
            raise AppError("MODEL_NOT_RUNNABLE", f"Model loading failed: {exc}") from exc

        selected_device = self._selected_device(torch)
        if selected_device != "cpu":
            loaded_model = loaded_model.to(selected_device)
        loaded_model.eval()
        self._model = loaded_model
        self._tokenizer = tokenizer
        self._loaded_model_id = model_row["model_id"]
        self._loaded_device = selected_device
        return loaded_model, tokenizer, selected_device

    def predict(self, model_row: dict[str, str], text: str) -> Prediction:
        model, tokenizer, device = self._load(model_row)
        import torch

        max_tokens = int(model_row.get("max_tokens") or 256)
        padding = (
            "max_length"
            if model_row.get("padding_policy") == "fixed_max_length"
            else True
        )
        encoded = tokenizer(
            text,
            max_length=max_tokens,
            padding=padding,
            truncation=True,
            return_tensors="pt",
        )
        if device != "cpu":
            encoded = {key: value.to(device) for key, value in encoded.items()}
        try:
            with torch.inference_mode():
                logits = model(**encoded).logits
                values = torch.softmax(logits, dim=-1)[0].detach().cpu()
        except Exception as exc:
            raise AppError("MODEL_NOT_RUNNABLE", "Model inference failed.") from exc
        if values.numel() != 5 or not bool(torch.isfinite(values).all()):
            raise AppError(
                "MODEL_NOT_RUNNABLE",
                "Model did not return five finite class probabilities.",
            )
        probabilities = tuple(float(value) for value in values)
        if abs(sum(probabilities) - 1.0) > 1e-5:
            raise AppError("MODEL_NOT_RUNNABLE", "Model probabilities do not sum to one.")
        versions: dict[str, str | None] = {
            "publisher_reliability": __version__,
            "python": sys.version.split()[0],
        }
        for package in ("torch", "transformers", "tokenizers", "beautifulsoup4", "langdetect"):
            try:
                versions[package] = importlib.metadata.version(package)
            except importlib.metadata.PackageNotFoundError:
                versions[package] = None
        return Prediction(
            predicted_class=max(range(5), key=lambda index: probabilities[index]),
            probabilities=probabilities,
            device=device,
            software_versions=versions,
        )
