"""Concrete request/response examples shown in the generated Swagger UI.

Every value here was captured from a real run of the shipped release
(``dataset/predictions``), not invented, so a reader can compare what they see in
`/api/docs` against what the same call returns against their own copy of the same
data. This is documentation only: nothing here is imported by application logic, and
editing a constant changes what Swagger *shows*, never what an endpoint *does*.

Kept in its own module rather than inline in ``api.py`` so a route's Python stays
short (one ``responses=EXAMPLE_NAME`` per endpoint) and the example payloads --
which are long, and change only when a response shape changes -- are easy to find
and update in one place instead of scattered through route bodies.
"""

from __future__ import annotations

# The one exception to "nothing here is application logic": the aggregation registry
# is re-used as its own example, because that endpoint returns it verbatim and a
# transcribed copy could only ever drift from it.
from .aggregation import DISPERSION_BANDS, METHODS

# ---------------------------------------------------------------------------
# Shared building blocks
# ---------------------------------------------------------------------------

_WARNING = (
    "Predictions are estimates, not fact checks. A publisher result depends on "
    "the selected articles, exact checkpoint/fold, and aggregation method."
)

# One real article, reused across several examples below so a reader can follow it
# from the article list, to its detail, to a single run, to the publisher it
# belongs to, and see the same identifiers line up everywhere. Exported (no leading
# underscore) because api.py also uses it as a query-parameter example.
ARTICLE_URL = (
    "http://floridapolitics.com/archives/241904-fiu-hotel-association-research-project"
)
_ARTICLE_ID = "a920b8a4-bc63-5051-820a-f3aa8d9ac235"
_ARTICLE_URL = ARTICLE_URL
_PUBLISHER_ID = "2e175e79-4cb0-5c80-ac98-1699b19603a1"
_RUN_ID = "75a8c77d-d22f-5e20-81fc-3b74f096bd23"
_ROBERTA_FOLD2_MODEL_ID = (
    "a1459f1ae8c7d7298ee27f835a7ce5a28441eb4771ea5fccaf7e125d00a71060"
)
_BERT_FOLD2_MODEL_ID = "5f057a6a5cee7f814c05c5531bda4264980441a8351fd6b51265bd4e5c0ceeb2"


def _error_example(code: str, message: str, details: dict | None = None) -> dict:
    """One error envelope, matching the registry in `errors.py` / api-contract.md §2."""

    return {
        "value": {
            "error": {
                "code": code,
                "message": message,
                "details": details or {},
                "request_id": "6f339a7f-d46c-4c5c-b918-beff07e220d0",
            }
        }
    }


NOT_FOUND_EXAMPLE = _error_example("NOT_FOUND", "Article was not found.")
INVALID_INPUT_EXAMPLE = _error_example(
    "INVALID_INPUT", "Request validation failed.", {"fields": ["query.method"]}
)

_PAGE_FIRST = {"limit": 25, "offset": 0, "next_offset": 25}
_PAGE_LAST = {"limit": 25, "offset": 0, "next_offset": None}

# ---------------------------------------------------------------------------
# 4. Health and status
# ---------------------------------------------------------------------------

STATUS_RESPONSES = {
    200: {
        "content": {
            "application/json": {
                "example": {
                    "application_version": "0.1.0",
                    "schema_version": "2",
                    "offline": False,
                    "device": "auto",
                    "bundled_import": {
                        "import_id": "44416bb6-ff89-579e-90ea-ee4dbc4f1898",
                        "source_kind": "bundled_manifest",
                        "source_name": "bundled-predictions-v1",
                        "content_sha256": "f492a7d30056d0588e93e81202299673229a7c980b881517fee2fe9df0e39451",
                        "status": "succeeded",
                        "accepted_rows": "17283",
                    },
                    "ledger_counts": {
                        "models": 20,
                        "prediction_runs": 34564,
                        "imports": 1,
                        "jobs": 0,
                        "local_content": 0,
                    },
                    "derived_counts": {
                        "articles": 17269,
                        "publishers": 372,
                        "historical_predictions": 34564,
                        "predictions_with_probabilities": 34564,
                    },
                    "model_state_counts": {"historical_only": 10, "compatible": 10},
                    "current_job": None,
                }
            }
        }
    }
}

# ---------------------------------------------------------------------------
# 5. Articles and runs
# ---------------------------------------------------------------------------

_ARTICLE_SUMMARY = {
    "article_id": _ARTICLE_ID,
    "canonical_url": _ARTICLE_URL,
    "publisher_id": _PUBLISHER_ID,
    "normalized_hostname": "floridapolitics.com",
    "model_count": 2,
    "run_count": 2,
    "latest_prediction_run_id": _RUN_ID,
    "latest_model_id": _ROBERTA_FOLD2_MODEL_ID,
    "latest_predicted_class": 3,
    "source_type": "dataset",
    "dataset_run_count": 2,
    "local_run_count": 0,
    "has_user_evaluation": False,
    "content_saved": False,
    "first_seen_at": "2026-09-17T09:43:03Z",
    "updated_at": "2026-09-17T09:43:03Z",
}

ARTICLES_RESPONSES = {
    200: {
        "content": {
            "application/json": {
                "example": {
                    "items": [
                        _ARTICLE_SUMMARY,
                        {
                            "article_id": "1d48fd0c-e9c3-5979-abc4-6902e0a091b9",
                            "canonical_url": "http://nytimes.com/2016/03/18/dining/corned-beef-and-cabbage-not-so-irish-historians-say.html",
                            "publisher_id": "b1546a7e-fdc7-520d-af84-f02bbc5b9d6f",
                            "normalized_hostname": "nytimes.com",
                            "model_count": 2,
                            "run_count": 2,
                            "latest_prediction_run_id": "468a5aa0-f860-5b6d-9c90-3b3e382fa364",
                            "latest_model_id": "bfe73a4bd1ead95b094357b51c0710a93580f0ee5648204af22c6257500b1b54",
                            "latest_predicted_class": 4,
                            "source_type": "dataset",
                            "dataset_run_count": 2,
                            "local_run_count": 0,
                            "has_user_evaluation": False,
                            "content_saved": False,
                            "first_seen_at": "2026-09-17T09:43:03Z",
                            "updated_at": "2026-09-17T09:43:03Z",
                        },
                    ],
                    "page": _PAGE_FIRST,
                }
            }
        }
    }
}

_RUN_ROBERTA = {
    "prediction_run_id": _RUN_ID,
    "article_id": _ARTICLE_ID,
    "canonical_url": _ARTICLE_URL,
    "publisher_id": _PUBLISHER_ID,
    "normalized_hostname": "floridapolitics.com",
    "model_id": _ROBERTA_FOLD2_MODEL_ID,
    "predicted_class": 3,
    "prob_class_0": "0.00018344992713537067",
    "prob_class_1": "7.38673479645513e-05",
    "prob_class_2": "6.776329246349633e-05",
    "prob_class_3": "0.9989573955535889",
    "prob_class_4": "0.000717492017429322",
    "origin": "bundled_import",
    "action": "import",
    "input_source": "unavailable",
    "content_retention": "discard",
    "source_import_id": "44416bb6-ff89-579e-90ea-ee4dbc4f1898",
    "job_id": "",
    "recorded_at": "2026-09-17T09:43:03Z",
    "probabilities": [
        0.00018344992713537067,
        7.38673479645513e-05,
        6.776329246349633e-05,
        0.9989573955535889,
        0.000717492017429322,
    ],
    "family": "roberta",
    "fold_id": 2,
    "model_display_name": "ROBERTA fold 2 (historical)",
    "model_provenance": "paper_dataset",
}

_RUN_BERT = {
    **_RUN_ROBERTA,
    "prediction_run_id": "e12b0349-b609-527d-8527-aa3fd54aeca0",
    "model_id": _BERT_FOLD2_MODEL_ID,
    "prob_class_0": "0.002600757172331214",
    "prob_class_1": "0.011882263235747814",
    "prob_class_2": "0.012714340351521969",
    "prob_class_3": "0.9706977605819702",
    "prob_class_4": "0.002104870043694973",
    "probabilities": [
        0.002600757172331214,
        0.011882263235747814,
        0.012714340351521969,
        0.9706977605819702,
        0.002104870043694973,
    ],
    "family": "bert",
    "fold_id": 2,
    "model_display_name": "BERT fold 2 (historical)",
}

ARTICLE_DETAIL_RESPONSES = {
    200: {
        "content": {
            "application/json": {
                "example": {
                    **_ARTICLE_SUMMARY,
                    "runs": [_RUN_ROBERTA, _RUN_BERT],
                    "warning": _WARNING,
                }
            }
        }
    },
    404: {"content": {"application/json": {"example": NOT_FOUND_EXAMPLE["value"]}}},
}

PREDICTION_RUNS_RESPONSES = {
    200: {
        "content": {
            "application/json": {
                "example": {
                    "items": [
                        {
                            "prediction_run_id": "0001da8e-ee3e-523f-b853-881ae2f4dfb2",
                            "article_id": "cc56a9d9-6327-55a5-bb0e-72bf4828dafb",
                            "canonical_url": "https://www.troymessenger.com/2025/03/18/brundidge-historical-society-extends-invitation-to-piddle-around/",
                            "publisher_id": "448a8460-32fd-51d6-b654-6d5f03420165",
                            "normalized_hostname": "troymessenger.com",
                            "model_id": "d4d4f3369bb7164f5a39d639eb64f69c272bf0cb67005d931fdec54b943ff0c5",
                            "predicted_class": 2,
                            "prob_class_0": "4.7538305807393044e-05",
                            "prob_class_1": "0.00011191139492439106",
                            "prob_class_2": "0.9995527863502502",
                            "prob_class_3": "0.0001954185136128217",
                            "prob_class_4": "9.238076745532453e-05",
                            "origin": "bundled_import",
                            "family": "bert",
                            "fold_id": 1,
                            "model_display_name": "BERT fold 1 (historical)",
                            "model_provenance": "paper_dataset",
                            "recorded_at": "2026-09-17T09:43:03Z",
                        }
                    ],
                    "page": _PAGE_FIRST,
                }
            }
        }
    }
}

PREDICTION_RUN_RESPONSES = {
    200: {
        "content": {
            "application/json": {
                "example": {
                    **_RUN_ROBERTA,
                    "article": {
                        "article_id": _ARTICLE_ID,
                        "canonical_url": _ARTICLE_URL,
                        "publisher_id": _PUBLISHER_ID,
                        "normalized_hostname": "floridapolitics.com",
                    },
                    "model": {
                        "model_id": _ROBERTA_FOLD2_MODEL_ID,
                        "family": "roberta",
                        "fold_id": "2",
                        "display_name": "ROBERTA fold 2 (historical)",
                        "artifact_kind": "historical_virtual",
                        "status": "historical_only",
                        "artifact_available": "false",
                        "runnable": "false",
                        "status_detail": "Imported predictions can be browsed and aggregated; inference is unavailable.",
                    },
                    "warning": _WARNING,
                }
            }
        }
    },
    404: {"content": {"application/json": {"example": NOT_FOUND_EXAMPLE["value"]}}},
}

CONTENT_RESPONSES = {
    200: {
        "content": {
            "application/json": {
                "example": {
                    "article_id": _ARTICLE_ID,
                    "canonical_url": _ARTICLE_URL,
                    "title": "FIU Hotel Association research project",
                    "text": "The full validated article body the user retrieved and chose to save…",
                    "content_saved_at": "2026-09-17T09:50:12Z",
                }
            }
        }
    },
    404: {"content": {"application/json": {"example": NOT_FOUND_EXAMPLE["value"]}}},
}

EXPORT_RESPONSES = {
    200: {
        "content": {
            "text/csv": {
                "example": (
                    "article_id,url,domain,publisher_id,prediction_origin,prediction_run_id,"
                    "model_id,prediction_family,prediction_fold_id,prediction_model_name,"
                    "prediction_model_provenance,prediction_official_manifest_entry_sha256,"
                    "predicted_label,prob_class_0,prob_class_1,prob_class_2,prob_class_3,"
                    "prob_class_4,prediction_action,input_source,content_retention,job_id,"
                    "inference_started_at,inference_completed_at,duration_ms,device,"
                    "software_versions_json,recorded_at\n"
                    f"{_ARTICLE_ID},{_ARTICLE_URL},floridapolitics.com,{_PUBLISHER_ID},"
                    "bundled_import,e12b0349-b609-527d-8527-aa3fd54aeca0,"
                    f"{_BERT_FOLD2_MODEL_ID},bert,2,BERT fold 2 (historical),paper_dataset,,3,"
                    "0.0026,0.0119,0.0127,0.9707,0.0021,import,unavailable,discard,,,,,,{},"
                    "2026-09-17T09:43:03Z\n"
                    f"{_ARTICLE_ID},{_ARTICLE_URL},floridapolitics.com,{_PUBLISHER_ID},"
                    f"bundled_import,{_RUN_ID},{_ROBERTA_FOLD2_MODEL_ID},roberta,2,"
                    "ROBERTA fold 2 (historical),paper_dataset,,3,0.0002,0.0001,0.0001,"
                    "0.9990,0.0007,import,unavailable,discard,,,,,,{},2026-09-17T09:43:03Z\n"
                )
            }
        },
        "description": (
            "Both rows describe the same article: one per model that judged it, "
            "with that model's own predicted label and full probability vector."
        ),
    }
}

# ---------------------------------------------------------------------------
# 6. Publishers
# ---------------------------------------------------------------------------

PUBLISHERS_RESPONSES = {
    200: {
        "content": {
            "application/json": {
                "example": {
                    "items": [
                        {
                            "publisher_id": "2289a982-3c76-585b-bf98-8f49ad0718ae",
                            "normalized_hostname": "aclu.org",
                            "article_count": 89,
                            "run_count": 178,
                            "model_count": 2,
                            "probability_run_count": 178,
                        },
                        {
                            "publisher_id": "ef5a5f6d-9e8e-55da-8bfc-ccddb6498e45",
                            "normalized_hostname": "aei.org",
                            "article_count": 108,
                            "run_count": 216,
                            "model_count": 2,
                            "probability_run_count": 216,
                        },
                    ],
                    "page": _PAGE_FIRST,
                }
            }
        }
    }
}

PUBLISHER_RESPONSES = {
    200: {
        "content": {
            "application/json": {
                "example": {
                    "publisher_id": _PUBLISHER_ID,
                    "normalized_hostname": "floridapolitics.com",
                    "article_count": 115,
                    "run_count": 230,
                    "model_count": 6,
                    "probability_run_count": 230,
                    "counts_by_model_class": {
                        "4a13349bb4d294ba5469d1da50bb844e59cbdf973bd0518788a0cacb351124ab": {
                            "0": 5,
                            "1": 33,
                            "2": 8,
                            "3": 32,
                            "4": 35,
                        }
                    },
                }
            }
        }
    },
    404: {"content": {"application/json": {"example": NOT_FOUND_EXAMPLE["value"]}}},
}

_INSUFFICIENT = "At least two leakage-safe articles are required for an aggregate."

# The shared article list. Long arrays are abbreviated with a sentence rather than
# trimmed silently, so nobody reads the example as the real length.
_AGGREGATION_ARTICLES = [
    {"article_id": _ARTICLE_ID, "canonical_url": _ARTICLE_URL, "excluded": False},
    {
        "article_id": "d0f624d2-1b5c-52bb-af10-9c03c2c15be8",
        "canonical_url": "https://floridapolitics.com/archives/275488-personnel-note-james-blair-enterprise-florida-board/",
        "excluded": False,
    },
    "… 113 more, one per leakage-safe article this publisher has",
]

# Real numbers from floridapolitics.com, whose articles are spread across three
# folds: a good example because the two families genuinely disagree and the
# dispersion is high enough that the verdict must not be read as a fact.
# Real numbers from floridapolitics.com. A good example because the two families
# genuinely disagree, the dispersion is high enough that neither verdict should be
# read as settled, and one checkpoint holds a single article and so reports nothing.
AGGREGATION_RESPONSES = {
    200: {
        "content": {
            "application/json": {
                "example": {
                    "publisher_id": _PUBLISHER_ID,
                    "normalized_hostname": "floridapolitics.com",
                    "method": "majority_vote",
                    "excluded_article_ids": [],
                    "articles": _AGGREGATION_ARTICLES,
                    "models": [
                        {
                            "model_id": "4a13349bb4d294ba5469d1da50bb844e59cbdf973bd0518788a0cacb351124ab",
                            "family": "bert",
                            "fold_id": 3,
                            "display_name": "BERT fold 3 (historical)",
                            "provenance": "paper_dataset",
                            "available_count": 113,
                            "used_count": 113,
                            "excluded_count": 0,
                            "result_class": 4,
                            "ordinal_mean": None,
                            "probabilities": None,
                            "mean_probabilities": [
                                0.05723994771956906,
                                0.2706397402607684,
                                0.07519815548262357,
                                0.27057518942190495,
                                0.3263469682181375,
                            ],
                            "class_counts": {"0": 5, "1": 33, "2": 8, "3": 32, "4": 35},
                            "weighted_counts": None,
                            "mean_class": 2.5304347826086957,
                            "variance": 1.6925519848771267,
                            "tolerant_variance": 1.608695652173913,
                            "agreement": 0.30434782608695654,
                            "tolerant_agreement": 0.6,
                            "dispersion_band": "high",
                            "dispersion_note": (
                                "The articles disagree severely, so no single class "
                                "represents this publisher well. On the study corpus "
                                "this band carried a 64-82% publisher-level error "
                                "rate, 22-43% when adjacent classes are allowed."
                            ),
                            "unavailable_reason": None,
                            "articles": [
                                {
                                    "article_id": _ARTICLE_ID,
                                    "predicted_class": 4,
                                    "confidence": 0.895137369632721,
                                    "excluded": False,
                                },
                                "\u2026 112 more, one per counted article",
                            ],
                            "article_ids": ["\u2026 113 article IDs"],
                        },
                        {
                            "model_id": _BERT_FOLD2_MODEL_ID,
                            "family": "bert",
                            "fold_id": 2,
                            "display_name": "BERT fold 2 (historical)",
                            "provenance": "paper_dataset",
                            "available_count": 1,
                            "used_count": 1,
                            "excluded_count": 0,
                            "result_class": None,
                            "ordinal_mean": None,
                            "probabilities": None,
                            "mean_probabilities": None,
                            "class_counts": {"0": 0, "1": 0, "2": 0, "3": 0, "4": 0},
                            "weighted_counts": None,
                            "mean_class": None,
                            "variance": None,
                            "tolerant_variance": None,
                            "agreement": None,
                            "tolerant_agreement": None,
                            "dispersion_band": None,
                            "dispersion_note": None,
                            "unavailable_reason": _INSUFFICIENT,
                            "articles": [
                                {
                                    "article_id": _ARTICLE_ID,
                                    "predicted_class": 4,
                                    "confidence": 0.895137369632721,
                                    "excluded": False,
                                }
                            ],
                            "article_ids": [_ARTICLE_ID],
                        },
                        "\u2026 four more entries, one per checkpoint that scored this publisher",
                    ],
                    "warning": _WARNING,
                }
            }
        }
    },
    404: {"content": {"application/json": {"example": NOT_FOUND_EXAMPLE["value"]}}},
    422: {"content": {"application/json": {"example": INVALID_INPUT_EXAMPLE["value"]}}},
}

# ---------------------------------------------------------------------------
# 7. Models
# ---------------------------------------------------------------------------

_MODEL_LOCAL = {
    "model_id": "6408a6071845b3cd1c44d3e1e5331c2bef29d3e69302f48442c5c18d2c93c2df",
    "family": "bert",
    "fold_id": 1,
    "display_name": "BERT fold 1 (local checkpoint)",
    "artifact_kind": "pytorch_state_dict",
    "artifact_locator": "root-1/bert_fold_1.pt",
    "artifact_sha256": "fb5e945eedfa17b7a1e76bba1681c1828baa5683ac63be5ef185fcc2801bbb84",
    "base_model": "google-bert/bert-base-uncased",
    "status": "compatible",
    "artifact_available": True,
    "runnable": True,
    "status_detail": "Checkpoint is valid and local inference is available. The pinned tokenizer is cached on first online use.",
    "identity_kind": "local",
    "provenance": "local_checkpoint",
}
_MODEL_HISTORICAL = {
    "model_id": "d4d4f3369bb7164f5a39d639eb64f69c272bf0cb67005d931fdec54b943ff0c5",
    "family": "bert",
    "fold_id": 1,
    "display_name": "BERT fold 1 (historical)",
    "artifact_kind": "historical_virtual",
    "status": "historical_only",
    "artifact_available": False,
    "runnable": False,
    "status_detail": "Imported predictions can be browsed and aggregated; inference is unavailable.",
    "identity_kind": "historical",
    "provenance": "paper_dataset",
}

MODELS_RESPONSES = {
    200: {
        "content": {
            "application/json": {"example": {"items": [_MODEL_LOCAL, _MODEL_HISTORICAL]}}
        }
    }
}

MODEL_SCAN_RESPONSES = {202: {"content": {"application/json": {"example": {"job_id": "6d291241-286d-4426-b213-3a08c055c871"}}}}}

# Real availability for the article used throughout this module: two folds (the
# ones actually held out for it) are eligible, and every other installed fold is
# named and explained rather than silently omitted.
AVAILABLE_MODELS_RESPONSES = {
    200: {
        "content": {
            "application/json": {
                "example": {
                    "items": [
                        {
                            "model_id": _BERT_FOLD2_MODEL_ID,
                            "local_model_id": "fac3bf32542acfb9ded97157bbf2335f5184e882852270714c0abf6793f75cb8",
                            "family": "bert",
                            "fold_id": 2,
                            "display_name": "BERT fold 2 (historical)",
                            "provenance": "local_checkpoint",
                            "local_status": "compatible",
                            "local_runnable": True,
                            "article_count": 1,
                            "run_count": 1,
                            "probability_count": 1,
                            "eligible": True,
                            "mode": "stored_prediction",
                        },
                        {
                            "model_id": _ROBERTA_FOLD2_MODEL_ID,
                            "local_model_id": "af1bd0dc549f3a23297526fc1f58200549838c8dfd6492e93916d0ef6bd7d382",
                            "family": "roberta",
                            "fold_id": 2,
                            "display_name": "ROBERTA fold 2 (historical)",
                            "provenance": "local_checkpoint",
                            "local_status": "compatible",
                            "local_runnable": True,
                            "article_count": 1,
                            "run_count": 1,
                            "probability_count": 1,
                            "eligible": True,
                            "mode": "stored_prediction",
                        },
                    ],
                    "availability": {
                        "code": "AVAILABLE",
                        "message": "2 local checkpoint(s) have enough leakage-safe stored predictions for this request.",
                        "input_known": True,
                        "local_checkpoint_count": 10,
                        "eligible_model_count": 2,
                        "blocked_training_models": [
                            {
                                "family": "bert",
                                "fold_id": 1,
                                "reason": "The article belongs to another held-out fold, so this checkpoint was trained on it.",
                            },
                            {
                                "family": "bert",
                                "fold_id": 3,
                                "reason": "The article belongs to another held-out fold, so this checkpoint was trained on it.",
                            },
                            "… every other installed fold, each named the same way",
                        ],
                    },
                }
            }
        }
    }
}

MODEL_UPLOAD_RESPONSES = {202: {"content": {"application/json": {"example": {"job_id": "9b1c2e4a-5f6d-4e8b-9a3c-1d2e3f4a5b6c"}}}}}

# ---------------------------------------------------------------------------
# 8. Evaluation
# ---------------------------------------------------------------------------

EVALUATION_BODY_EXAMPLES = {
    "reuse_a_dataset_article": {
        "summary": "Reuse the stored prediction for a known dataset article",
        "description": (
            "`model_id` here is the exact historical identity that already produced "
            "a run for this article; `reuse` finds it and creates nothing new."
        ),
        "value": {
            "input": {"type": "article", "url": _ARTICLE_URL},
            "model_id": _ROBERTA_FOLD2_MODEL_ID,
            "prediction_action": "reuse",
            "content_retention": "discard",
        },
    },
    "classify_a_new_article": {
        "summary": "Classify a new article with a runnable local checkpoint",
        "description": (
            "`recompute` always retrieves the page and creates a new run, even if "
            "one already exists."
        ),
        "value": {
            "input": {"type": "article", "url": "https://publisher.example/2026/some-article"},
            "model_id": "6408a6071845b3cd1c44d3e1e5331c2bef29d3e69302f48442c5c18d2c93c2df",
            "prediction_action": "recompute",
            "content_retention": "save_local",
        },
    },
}

EVALUATION_JOB_RESPONSES = {202: {"content": {"application/json": {"example": {"job_id": "0edd367c-7f5c-4a72-860f-681686590eb8"}}}}}

# ---------------------------------------------------------------------------
# 9. Jobs
# ---------------------------------------------------------------------------

JOBS_RESPONSES = {
    200: {
        "content": {
            "application/json": {
                "example": {
                    "items": [
                        {
                            "job_id": "0edd367c-7f5c-4a72-860f-681686590eb8",
                            "job_type": "evaluation",
                            "status": "succeeded",
                            "phase": "saving",
                            "progress": 100,
                            "created_at": "2026-09-17T09:48:11Z",
                            "finished_at": "2026-09-17T09:48:12Z",
                        }
                    ],
                    "page": _PAGE_FIRST,
                }
            }
        }
    }
}

# Two real outcomes for the *same* article/model pair, so a reader sees both a
# succeeded reuse and the leakage guard refusing a different, untrained fold --
# without having to imagine what the failure shape looks like.
GET_JOB_RESPONSES = {
    200: {
        "content": {
            "application/json": {
                "examples": {
                    "succeeded_reuse": {
                        "summary": "reuse succeeded: an existing run was returned",
                        "value": {
                            "job_id": "8cd26a44-3636-4764-afc5-1991cac5174a",
                            "job_type": "evaluation",
                            "status": "succeeded",
                            "phase": "saving",
                            "progress": 100,
                            "request": {
                                "input": {"type": "article", "url": _ARTICLE_URL},
                                "model_id": _ROBERTA_FOLD2_MODEL_ID,
                                "prediction_action": "reuse",
                                "content_retention": "discard",
                            },
                            "result": {
                                "article_id": _ARTICLE_ID,
                                "canonical_url": _ARTICLE_URL,
                                "family": "roberta",
                                "fold_id": 2,
                                "model_display_name": "ROBERTA fold 2 (historical)",
                                "model_id": _ROBERTA_FOLD2_MODEL_ID,
                                "predicted_class": 3,
                                "prediction_run_id": _RUN_ID,
                                "probabilities": [
                                    0.00018344992713537067,
                                    7.38673479645513e-05,
                                    6.776329246349633e-05,
                                    0.9989573955535889,
                                    0.000717492017429322,
                                ],
                                "reused": True,
                            },
                            "error_code": "",
                            "error_message": "",
                            "created_at": "2026-09-17T09:48:25Z",
                            "finished_at": "2026-09-17T09:48:26Z",
                        },
                    },
                    "failed_leakage_guard": {
                        "summary": "blocked: this checkpoint was trained on the article",
                        "description": (
                            "Same article, a different local fold (BERT fold 1) that "
                            "the study's publisher-disjoint split actually trained on it."
                        ),
                        "value": {
                            "job_id": "0cd79dac-dcbe-49f7-9124-c214e3ce496c",
                            "job_type": "evaluation",
                            "status": "failed",
                            "phase": "",
                            "progress": 100,
                            "request": {
                                "input": {"type": "article", "url": _ARTICLE_URL},
                                "model_id": "6408a6071845b3cd1c44d3e1e5331c2bef29d3e69302f48442c5c18d2c93c2df",
                                "prediction_action": "reuse",
                                "content_retention": "discard",
                            },
                            "result": {},
                            "error_code": "TRAINING_DATA_LEAKAGE",
                            "error_message": "The selected checkpoint was trained on this dataset article.",
                            "created_at": "2026-09-17T09:47:57Z",
                            "finished_at": "2026-09-17T09:47:57Z",
                        },
                    },
                    "running": {
                        "summary": "still running: poll again in about a second",
                        "description": (
                            "Progress only ever moves forward; phases are the exact "
                            "strings this job type reports, not codes to translate."
                        ),
                        "value": {
                            "job_id": "0edd367c-7f5c-4a72-860f-681686590eb8",
                            "job_type": "evaluation",
                            "status": "running",
                            "phase": "classifying the article text",
                            "progress": 60,
                            "request": {
                                "input": {"type": "article", "url": _ARTICLE_URL},
                                "model_id": "6408a6071845b3cd1c44d3e1e5331c2bef29d3e69302f48442c5c18d2c93c2df",
                                "prediction_action": "recompute",
                                "content_retention": "discard",
                            },
                            "result": {},
                            "error_code": "",
                            "error_message": "",
                            "created_at": "2026-09-17T09:48:11Z",
                            "finished_at": "",
                        },
                    },
                }
            }
        }
    },
    404: {"content": {"application/json": {"example": NOT_FOUND_EXAMPLE["value"]}}},
}

# ---------------------------------------------------------------------------
# 10. Imports
# ---------------------------------------------------------------------------

_IMPORT_SUMMARY = {
    "import_id": "44416bb6-ff89-579e-90ea-ee4dbc4f1898",
    "source_kind": "bundled_manifest",
    "source_name": "bundled-predictions-v1",
    "content_sha256": "f492a7d30056d0588e93e81202299673229a7c980b881517fee2fe9df0e39451",
    "schema_version": "1",
    "status": "succeeded",
    "source_rows": 17283,
    "accepted_rows": 17283,
    "rejected_rows": 0,
    "duplicate_rows": 2,
    "protected_columns": [],
    "warnings": [],
    "started_at": "2026-09-17T09:43:01Z",
    "completed_at": "2026-09-17T09:43:03Z",
}

IMPORTS_RESPONSES = {
    200: {
        "content": {
            "application/json": {
                "example": {"items": [_IMPORT_SUMMARY], "page": _PAGE_LAST}
            }
        }
    }
}
IMPORT_RESPONSES = {
    200: {"content": {"application/json": {"example": _IMPORT_SUMMARY}}},
    404: {"content": {"application/json": {"example": NOT_FOUND_EXAMPLE["value"]}}},
}
IMPORT_UPLOAD_RESPONSES = {202: {"content": {"application/json": {"example": {"job_id": "3c9d1e2f-4a5b-6c7d-8e9f-0a1b2c3d4e5f"}}}}}

# ---------------------------------------------------------------------------
# 11. Aggregation metadata
# ---------------------------------------------------------------------------

# Built from the real registry rather than transcribed. This endpoint returns the
# registry verbatim, so a hand-written example could only ever be a copy waiting to
# fall out of date the next time a method or a band is added.
AGGREGATION_METHODS_RESPONSES = {
    200: {
        "content": {
            "application/json": {
                "example": {
                    "items": METHODS,
                    "dispersion_bands": [
                        {
                            "band": band,
                            "description": description,
                            **({} if upper is None else {"upper_bound": upper}),
                        }
                        for upper, band, description in DISPERSION_BANDS
                    ],
                }
            }
        }
    }
}
