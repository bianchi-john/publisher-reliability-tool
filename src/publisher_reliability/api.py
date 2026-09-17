"""FastAPI application exposing the local research service."""

from __future__ import annotations

import shutil
import uuid
from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Body, FastAPI, File, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from . import SCHEMA_VERSION, __version__
from .aggregation import DISPERSION_BANDS, METHODS
from .config import Config
from .errors import LLM_UNDER_DEVELOPMENT, AppError, HTTP_STATUS
from .importer import import_bundled_release
from .jobs import JobManager
from .model_scanner import scan_model_roots
from . import openapi_examples as examples
from .prediction_dataset import (
    restore_user_predictions,
    sync_user_predictions,
)
from .services import ResearchService, paginate
from .storage import Storage


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ArticleInput(StrictModel):
    type: Literal["article"]
    url: str = Field(max_length=8192)


class EvaluationRequest(StrictModel):
    """One evaluation request. Only a single article can be evaluated.

    A publisher-level class is not requested here: it is derived on demand from the
    articles already classified, through the publisher aggregation endpoint.
    """

    input: ArticleInput
    model_id: str
    prediction_action: Literal["reuse", "recompute"] = "reuse"
    content_retention: Literal["discard", "save_local"] = "discard"


class DeleteContentRequest(StrictModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"example": examples.DELETE_CONTENT_BODY_EXAMPLE},
    )

    confirm_canonical_url: str


class ClearUserDataRequest(StrictModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"example": examples.CLEAR_USER_DATA_BODY_EXAMPLE},
    )

    confirmation: str


class EmptyRequest(StrictModel):
    pass


def error_response(exc: AppError, request_id: str | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=HTTP_STATUS[exc.code],
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
                "request_id": request_id or str(uuid.uuid4()),
            }
        },
    )


@dataclass(frozen=True)
class Workspace:
    """Persistent state and services, opened once when the application starts."""

    storage: Storage
    service: ResearchService
    jobs: JobManager
    bundled_import: dict[str, str] | None
    startup_model_scan: dict[str, object]
    restored_user_predictions: object
    mirrored_user_predictions: object


def _open_workspace(
    settings: Config,
    on_scan_progress: Callable[[str], None] | None = None,
) -> Workspace:
    """Open the data directory and bring it in step with what is on disk.

    The order is deliberate. The bundled release is imported before checkpoints are
    scanned, so the scan reconciles local files against a ledger that already holds the
    historical model identities. User predictions are restored from their private
    mirror file before that mirror is rewritten from the ledger, so runs created in an
    earlier session survive a restart instead of being overwritten.

    Any failure closes the storage lock again: a half-opened workspace would keep the
    data directory locked against the next attempt.
    """

    storage = Storage(settings.data_dir)
    try:
        bundled_import = import_bundled_release(storage, settings.seed_dataset)
        startup_model_scan = scan_model_roots(
            storage, settings.models_dirs, on_progress=on_scan_progress
        )
        restored_user_predictions = restore_user_predictions(
            storage,
            settings.seed_dataset,
        )
        mirrored_user_predictions = sync_user_predictions(
            settings.seed_dataset,
            storage.rows["prediction_runs"],
            {row["model_id"]: row for row in storage.rows["models"]},
        )
        service = ResearchService(
            storage,
            offline=settings.offline,
            model_roots=settings.models_dirs,
            device=settings.device,
            prediction_dataset_dir=settings.seed_dataset,
        )
        jobs = JobManager(
            storage,
            service,
            model_roots=(
                *settings.models_dirs,
                storage.data_dir / "managed-models",
            ),
            dataset_upload_max_bytes=settings.dataset_upload_max_bytes,
            model_upload_max_bytes=settings.model_upload_max_bytes,
        )
    except Exception:
        storage.close()
        raise
    return Workspace(
        storage=storage,
        service=service,
        jobs=jobs,
        bundled_import=bundled_import,
        startup_model_scan=startup_model_scan,
        restored_user_predictions=restored_user_predictions,
        mirrored_user_predictions=mirrored_user_predictions,
    )


def create_app(
    config: Config | None = None,
    *,
    on_scan_progress: Callable[[str], None] | None = None,
) -> FastAPI:
    """Build the loopback-only application over a freshly opened workspace."""

    settings = config or Config.from_env()
    workspace = _open_workspace(settings, on_scan_progress)
    storage = workspace.storage
    service = workspace.service
    jobs = workspace.jobs

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        jobs.stop()
        storage.close()

    app = FastAPI(
        title="Publisher Reliability Tool",
        version=__version__,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )
    app.state.config = settings
    app.state.storage = storage
    app.state.service = service
    app.state.jobs = jobs
    app.state.bundled_import = workspace.bundled_import
    app.state.startup_model_scan = workspace.startup_model_scan
    app.state.restored_user_predictions = workspace.restored_user_predictions
    app.state.mirrored_user_predictions = workspace.mirrored_user_predictions

    @app.middleware("http")
    async def local_host_boundary(request: Request, call_next):
        # The socket already listens on loopback only; matching the Host header as well
        # defeats DNS rebinding, where a public name resolves to 127.0.0.1 and a remote
        # page then drives this API through the user's own browser.
        host = request.headers.get("host", "")
        expected = f"127.0.0.1:{settings.port}"
        if host != expected:
            return error_response(
                AppError("INVALID_HOST", "Request Host does not match the local origin.")
            )
        request.state.request_id = str(uuid.uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    @app.middleware("http")
    async def revalidate_frontend_assets(request: Request, call_next):
        # The frontend is plain files with stable names and no build step. Without an
        # explicit policy a browser caches them heuristically, so it can keep running a
        # previous page shell — and then request a script the current one no longer has.
        # "no-cache" does not forbid storing the file, only serving it without asking
        # first, so the ETag round-trip still makes the reload cheap.
        response = await call_next(request)
        if request.url.path == "/" or request.url.path.startswith("/assets/"):
            response.headers["Cache-Control"] = "no-cache"
        return response

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        return error_response(exc, getattr(request.state, "request_id", None))

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        fields = [
            ".".join(str(part) for part in error["loc"] if part != "body")
            for error in exc.errors()
        ]
        return error_response(
            AppError("INVALID_INPUT", "Request validation failed.", {"fields": fields}),
            getattr(request.state, "request_id", None),
        )

    @app.exception_handler(Exception)
    async def internal_error_handler(request: Request, _exc: Exception):
        # The cause is deliberately dropped: a traceback or path would leak local
        # filesystem layout into an HTTP response.
        return error_response(
            AppError("INTERNAL_ERROR", "The request failed unexpectedly."),
            getattr(request.state, "request_id", None),
        )

    @app.get("/health/live", summary="Liveness probe")
    async def live():
        return {"status": "alive"}

    @app.get("/health/ready", summary="Readiness probe")
    async def ready():
        return {"status": "ready"}

    @app.get(
        "/api/v1/status",
        summary="Workspace overview: versions, ledger counts, current job",
        responses=examples.STATUS_RESPONSES,
    )
    async def status():
        counts = {
            key: len(value)
            for key, value in storage.rows.items()
            if key != "meta"
        }
        model_states: dict[str, int] = {}
        for model in storage.rows["models"]:
            model_states[model["status"]] = model_states.get(model["status"], 0) + 1
        # One FIFO worker runs at most one job, so "current" means the running one
        # whenever there is one. Ledger order is least-recently-updated first, which
        # would otherwise surface a job still waiting in the queue ahead of the job
        # actually executing. Among queued jobs the oldest is the one running next.
        waiting = sorted(
            (row for row in storage.rows["jobs"] if row["status"] in {"queued", "running"}),
            key=lambda row: (row["status"] != "running", row["created_at"], row["job_id"]),
        )
        active = jobs._public(waiting[0]) if waiting else None
        return {
            "application_version": __version__,
            "schema_version": SCHEMA_VERSION,
            "offline": settings.offline,
            "device": settings.device,
            "bundled_import": workspace.bundled_import,
            "ledger_counts": counts,
            "derived_counts": {
                "articles": len(
                    {
                        row["article_id"]
                        for row in storage.rows["prediction_runs"]
                    }
                ),
                "publishers": len(
                    {
                        row["publisher_id"]
                        for row in storage.rows["prediction_runs"]
                    }
                ),
                "historical_predictions": sum(
                    row["origin"] in {"bundled_import", "user_import"}
                    for row in storage.rows["prediction_runs"]
                ),
                "predictions_with_probabilities": sum(
                    bool(row["prob_class_0"])
                    for row in storage.rows["prediction_runs"]
                ),
            },
            "model_state_counts": model_states,
            "current_job": active,
        }

    @app.get(
        "/api/v1/articles/export",
        response_class=PlainTextResponse,
        summary="Download predictions as CSV, one row per model per article",
        responses=examples.EXPORT_RESPONSES,
    )
    async def export_articles(
        q: str | None = None,
        publisher: str | None = None,
        model_id: str | None = None,
        predicted_class: int | None = Query(default=None, ge=0, le=4),
        origin: str | None = None,
        article_source: Literal["dataset", "user_evaluation"] | None = None,
        sort: Literal["updated_desc", "url_asc"] = "updated_desc",
    ):
        return PlainTextResponse(
            service.export_predictions(
                q=q,
                publisher=publisher,
                model_id=model_id,
                predicted_class=predicted_class,
                origin=origin,
                article_source=article_source,
                sort=sort,
            ),
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": 'attachment; filename="article-predictions.csv"'
            },
        )

    @app.delete(
        "/api/v1/user-data",
        summary="Permanently delete every local evaluation, its content and its mirror",
        responses=examples.CLEAR_USER_DATA_RESPONSES,
    )
    async def clear_user_data(body: ClearUserDataRequest):
        # A publisher's stored predictions are never touched here: this deletes only
        # what a user created locally, not the shared research dataset.
        return service.clear_user_data(confirmation=body.confirmation)

    @app.get(
        "/api/v1/articles",
        summary="List articles derived from stored prediction runs",
        responses=examples.ARTICLES_RESPONSES,
    )
    async def articles(
        limit: int = 25,
        offset: int = 0,
        q: str | None = None,
        publisher: str | None = None,
        model_id: str | None = None,
        predicted_class: int | None = Query(default=None, ge=0, le=4),
        origin: str | None = None,
        article_source: Literal["dataset", "user_evaluation"] | None = None,
        sort: Literal["updated_desc", "url_asc"] = "updated_desc",
    ):
        return paginate(
            service.article_summaries(
                q=q,
                publisher=publisher,
                model_id=model_id,
                predicted_class=predicted_class,
                origin=origin,
                article_source=article_source,
                sort=sort,
            ),
            limit,
            offset,
        )

    @app.get(
        "/api/v1/articles/{article_identifier}/content",
        summary="Read explicitly saved title/body for one article",
        responses=examples.CONTENT_RESPONSES,
    )
    async def article_content(article_identifier: str):
        return JSONResponse(
            service.content(article_identifier),
            headers={"Cache-Control": "no-store"},
        )

    @app.delete(
        "/api/v1/articles/{article_identifier}/content",
        summary="Delete saved content for one article",
        responses=examples.DELETE_CONTENT_RESPONSES,
    )
    async def delete_article_content(article_identifier: str, body: DeleteContentRequest):
        return service.delete_content(article_identifier, body.confirm_canonical_url)

    @app.get(
        "/api/v1/articles/{article_identifier}",
        summary="One article with every model's prediction for it",
        responses=examples.ARTICLE_DETAIL_RESPONSES,
    )
    async def article(article_identifier: str):
        return service.article(article_identifier)

    @app.get(
        "/api/v1/prediction-runs",
        summary="List immutable prediction runs",
        responses=examples.PREDICTION_RUNS_RESPONSES,
    )
    async def prediction_runs(
        limit: int = 25,
        offset: int = 0,
        article_id: str | None = None,
        publisher_id: str | None = None,
        model_id: str | None = None,
        family: str | None = None,
        origin: str | None = None,
    ):
        return paginate(
            service.prediction_runs(
                article_id=article_id,
                publisher_id=publisher_id,
                model_id=model_id,
                family=family,
                origin=origin,
            ),
            limit,
            offset,
        )

    @app.get(
        "/api/v1/prediction-runs/{run_identifier}",
        summary="One immutable run, with its article and model details",
        responses=examples.PREDICTION_RUN_RESPONSES,
    )
    async def prediction_run(run_identifier: str):
        return service.prediction_run(run_identifier)

    @app.get(
        "/api/v1/publishers",
        summary="List publishers derived from stored prediction runs",
        responses=examples.PUBLISHERS_RESPONSES,
    )
    async def publishers(
        limit: int = 25,
        offset: int = 0,
        q: str | None = None,
        model_id: str | None = None,
    ):
        return paginate(
            service.publisher_summaries(q=q, model_id=model_id), limit, offset
        )

    @app.get(
        "/api/v1/publishers/{publisher_identifier}",
        summary="One publisher's article/run counts and class breakdown",
        responses=examples.PUBLISHER_RESPONSES,
    )
    async def publisher(publisher_identifier: str):
        return service.publisher(publisher_identifier)

    @app.get(
        "/api/v1/publishers/{publisher_identifier}/aggregation",
        summary="Derive a publisher's class from its article predictions (read-only)",
        responses=examples.AGGREGATION_RESPONSES,
    )
    async def publisher_aggregation(
        publisher_identifier: str,
        method: Annotated[
            Literal[
                "majority_vote",
                "ordinal_mean",
                "median_class",
                "mean_probabilities",
                "expected_class",
                "confidence_weighted_vote",
            ],
            Query(examples=["majority_vote", "expected_class"]),
        ] = "majority_vote",
        exclude: Annotated[
            list[str] | None,
            Query(
                description="Repeat to leave more than one article out of the count.",
                examples=[["d0f624d2-1b5c-52bb-af10-9c03c2c15be8"]],
            ),
        ] = None,
    ):
        # Read-only: the publisher class is derived from stored article predictions on
        # every request and never persisted, so changing the rule or the excluded
        # articles simply asks the same data a different question.
        return service.publisher_aggregation(
            publisher_identifier,
            method=method,
            excluded_article_ids=exclude or (),
        )

    @app.get(
        "/api/v1/models",
        summary="List local checkpoints and historical dataset identities",
        responses=examples.MODELS_RESPONSES,
    )
    async def models(family: str | None = None, status: str | None = None):
        return {"items": service.models(family=family, status=status)}

    @app.get(
        "/api/v1/models/available",
        summary="Which local checkpoints may classify this article, and why not the rest",
        responses=examples.AVAILABLE_MODELS_RESPONSES,
    )
    async def available_models(
        url: Annotated[str, Query(examples=[examples.ARTICLE_URL])],
    ):
        # One article URL is the only question this answers: a publisher class is read
        # from the articles already classified, never evaluated.
        return service.available_models(url=url)

    @app.post(
        "/api/v1/models/scan",
        status_code=202,
        summary="Scan configured model directories for checkpoints",
        responses=examples.MODEL_SCAN_RESPONSES,
    )
    async def model_scan(_body: EmptyRequest):
        return {"job_id": jobs.submit("model_validation", {})}

    @app.post(
        "/api/v1/models/upload",
        status_code=202,
        summary="Import a custom five-class Transformer bundle (.zip)",
        responses=examples.MODEL_UPLOAD_RESPONSES,
    )
    async def model_upload(file: UploadFile = File(...)):
        filename = Path(file.filename or "").name
        if not filename.lower().endswith(".zip"):
            raise AppError(
                "INVALID_INPUT",
                "Custom model upload must be a self-contained .zip bundle.",
            )
        # A generated token, never the client's filename, names the temporary file.
        token = f"{uuid.uuid4()}.model.zip"
        destination = storage.data_dir / "uploads" / token
        # Counted while streaming: the declared Content-Length cannot be trusted, and
        # the upload must stop at the limit rather than after the disk is full.
        total = 0
        try:
            with destination.open("xb") as output:
                while chunk := await file.read(1024 * 1024):
                    total += len(chunk)
                    if total > settings.model_upload_max_bytes:
                        raise AppError(
                            "PAYLOAD_TOO_LARGE",
                            "Custom model upload exceeds the byte limit.",
                        )
                    output.write(chunk)
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        finally:
            await file.close()
        try:
            # If the job cannot be queued, the acquired file would otherwise be orphaned.
            job_id = jobs.submit(
                "model_validation",
                {
                    "source_upload_id": token,
                    "source_name": filename,
                    "bundle_kind": "custom_transformer",
                },
            )
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        return {"job_id": job_id}

    @app.post(
        "/api/v1/models/official-upload",
        status_code=202,
        summary="Import an official Llama/Mistral checkpoint (not available yet)",
        responses=examples.OFFICIAL_UPLOAD_RESPONSES,
    )
    async def official_model_upload(files: list[UploadFile] = File(...)):
        # Refused before a single byte is read, so a multi-gigabyte upload is not
        # spooled to disk only to be rejected afterwards.
        for uploaded in files:
            await uploaded.close()
        raise AppError("FEATURE_UNAVAILABLE", LLM_UNDER_DEVELOPMENT)

    @app.post(
        "/api/v1/evaluation-jobs",
        status_code=202,
        summary="Classify one article, or reuse its stored prediction",
        responses=examples.EVALUATION_JOB_RESPONSES,
    )
    async def evaluation_job(
        body: Annotated[
            EvaluationRequest, Body(openapi_examples=examples.EVALUATION_BODY_EXAMPLES)
        ],
    ):
        return {"job_id": jobs.submit("evaluation", body.model_dump(mode="json"))}

    @app.get(
        "/api/v1/jobs",
        summary="List background jobs, newest first",
        responses=examples.JOBS_RESPONSES,
    )
    async def list_jobs(
        limit: int = 25,
        offset: int = 0,
        status: str | None = None,
        job_type: str | None = None,
    ):
        return paginate(jobs.list(status=status, job_type=job_type), limit, offset)

    @app.get(
        "/api/v1/jobs/{job_identifier}",
        summary="Poll one job's phase, progress and result or error",
        responses=examples.GET_JOB_RESPONSES,
    )
    async def get_job(job_identifier: str):
        return jobs.get(job_identifier)

    @app.delete(
        "/api/v1/jobs",
        summary="Delete every job row (no confirmation; refuses if one is active)",
        responses=examples.CLEAR_JOBS_RESPONSES,
    )
    async def clear_jobs():
        return {"deleted": jobs.clear()}

    @app.get(
        "/api/v1/imports",
        summary="List completed and failed dataset imports",
        responses=examples.IMPORTS_RESPONSES,
    )
    async def imports(limit: int = 25, offset: int = 0):
        return paginate(service.imports(), limit, offset)

    @app.get(
        "/api/v1/imports/{import_identifier}",
        summary="One import's source, counts and warnings",
        responses=examples.IMPORT_RESPONSES,
    )
    async def get_import(import_identifier: str):
        result = next(
            (row for row in service.imports() if row["import_id"] == import_identifier),
            None,
        )
        if result is None:
            raise AppError("NOT_FOUND", "Import was not found.")
        return result

    @app.post(
        "/api/v1/imports/upload",
        status_code=202,
        summary="Import a user CSV/CSV.GZ of BERT/RoBERTa predictions",
        responses=examples.IMPORT_UPLOAD_RESPONSES,
    )
    async def upload_import(file: UploadFile = File(...)):
        filename = Path(file.filename or "").name
        if not (
            filename.lower().endswith(".csv")
            or filename.lower().endswith(".csv.gz")
        ):
            raise AppError("INVALID_INPUT", "Upload must be CSV or CSV.GZ.")
        token = f"{uuid.uuid4()}{'.csv.gz' if filename.lower().endswith('.gz') else '.csv'}"
        destination = storage.data_dir / "uploads" / token
        total = 0
        try:
            with destination.open("xb") as output:
                while chunk := await file.read(1024 * 1024):
                    total += len(chunk)
                    if total > settings.dataset_upload_max_bytes:
                        raise AppError(
                            "PAYLOAD_TOO_LARGE", "Dataset upload exceeds the byte limit."
                        )
                    output.write(chunk)
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        finally:
            await file.close()
        try:
            job_id = jobs.submit(
                "dataset_import",
                {"source_upload_id": token, "source_name": filename},
            )
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        return {"job_id": job_id}

    @app.get(
        "/api/v1/aggregation-methods",
        summary="Formulas, minimum count and warning for each aggregation method",
        responses=examples.AGGREGATION_METHODS_RESPONSES,
    )
    async def aggregation_methods():
        # The dispersion bands travel with the methods so the interface can label a
        # variance without hard-coding thresholds that were derived from measurements.
        # The last band is open-ended and simply omits ``upper_bound``: a null would be
        # stripped from the generated Swagger example, leaving the documentation
        # showing a different shape from the live response.
        return {
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

    frontend = Path(__file__).with_name("frontend")
    app.mount("/assets", StaticFiles(directory=frontend), name="assets")

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def index():
        return FileResponse(frontend / "index.html")

    return app
