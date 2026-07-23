"""FastAPI application exposing the local research service."""

from __future__ import annotations

import shutil
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal, Union

from fastapi import Body, FastAPI, File, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from . import SCHEMA_VERSION, __version__
from .aggregation import METHODS
from .config import Config
from .errors import AppError, HTTP_STATUS
from .importer import import_bundled_release
from .jobs import JobManager
from .services import ResearchService, paginate
from .storage import Storage


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ArticleInput(StrictModel):
    type: Literal["article"]
    url: str = Field(max_length=8192)


class ArticleListInput(StrictModel):
    type: Literal["article_list"]
    urls: list[str] = Field(min_length=2, max_length=50)


class PublisherInput(StrictModel):
    type: Literal["publisher"]
    url: str = Field(max_length=8192)
    requested_article_count: int = Field(ge=2, le=50)
    allow_partial: bool = False


EvaluationInput = Annotated[
    Union[ArticleInput, ArticleListInput, PublisherInput],
    Field(discriminator="type"),
]


class EvaluationRequest(StrictModel):
    input: EvaluationInput
    model_id: str
    aggregation_method: Literal[
        "majority_vote", "ordinal_mean", "mean_probabilities"
    ] | None = None
    prediction_action: Literal["reuse", "recompute"] = "reuse"
    content_retention: Literal["discard", "save_local"] = "discard"


class DeleteContentRequest(StrictModel):
    confirm_canonical_url: str


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


def create_app(config: Config | None = None) -> FastAPI:
    settings = config or Config.from_env()
    storage = Storage(settings.data_dir)
    bundled_import = import_bundled_release(storage, settings.seed_dataset)
    service = ResearchService(storage, offline=settings.offline)
    jobs = JobManager(storage, service)

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
    app.state.bundled_import = bundled_import

    @app.middleware("http")
    async def local_host_boundary(request: Request, call_next):
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
        return error_response(
            AppError("INTERNAL_ERROR", "The request failed unexpectedly."),
            getattr(request.state, "request_id", None),
        )

    @app.get("/health/live")
    async def live():
        return {"status": "alive"}

    @app.get("/health/ready")
    async def ready():
        return {"status": "ready"}

    @app.get("/api/v1/status")
    async def status():
        counts = {
            key: len(value)
            for key, value in storage.rows.items()
            if key != "meta"
        }
        model_states: dict[str, int] = {}
        for model in storage.rows["models"]:
            model_states[model["status"]] = model_states.get(model["status"], 0) + 1
        active = next(
            (
                jobs._public(row)
                for row in storage.rows["jobs"]
                if row["status"] in {"queued", "running"}
            ),
            None,
        )
        return {
            "application_version": __version__,
            "schema_version": SCHEMA_VERSION,
            "offline": settings.offline,
            "device": settings.device,
            "bundled_import": bundled_import,
            "ledger_counts": counts,
            "model_state_counts": model_states,
            "current_job": active,
        }

    @app.get("/api/v1/articles/export", response_class=PlainTextResponse)
    async def export_articles(
        q: str | None = None,
        publisher: str | None = None,
        model_id: str | None = None,
        predicted_class: int | None = Query(default=None, ge=0, le=4),
        origin: str | None = None,
        sort: Literal["updated_desc", "url_asc"] = "updated_desc",
    ):
        return PlainTextResponse(
            service.export_articles(
                q=q,
                publisher=publisher,
                model_id=model_id,
                predicted_class=predicted_class,
                origin=origin,
                sort=sort,
            ),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="articles.csv"'},
        )

    @app.get("/api/v1/articles")
    async def articles(
        limit: int = 25,
        offset: int = 0,
        q: str | None = None,
        publisher: str | None = None,
        model_id: str | None = None,
        predicted_class: int | None = Query(default=None, ge=0, le=4),
        origin: str | None = None,
        sort: Literal["updated_desc", "url_asc"] = "updated_desc",
    ):
        return paginate(
            service.article_summaries(
                q=q,
                publisher=publisher,
                model_id=model_id,
                predicted_class=predicted_class,
                origin=origin,
                sort=sort,
            ),
            limit,
            offset,
        )

    @app.get("/api/v1/articles/{article_identifier}/content")
    async def article_content(article_identifier: str):
        return JSONResponse(
            service.content(article_identifier),
            headers={"Cache-Control": "no-store"},
        )

    @app.delete("/api/v1/articles/{article_identifier}/content")
    async def delete_article_content(article_identifier: str, body: DeleteContentRequest):
        return service.delete_content(article_identifier, body.confirm_canonical_url)

    @app.get("/api/v1/articles/{article_identifier}")
    async def article(article_identifier: str):
        return service.article(article_identifier)

    @app.get("/api/v1/prediction-runs")
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

    @app.get("/api/v1/prediction-runs/{run_identifier}")
    async def prediction_run(run_identifier: str):
        return service.prediction_run(run_identifier)

    @app.get("/api/v1/publishers")
    async def publishers(
        limit: int = 25,
        offset: int = 0,
        q: str | None = None,
        model_id: str | None = None,
    ):
        return paginate(
            service.publisher_summaries(q=q, model_id=model_id), limit, offset
        )

    @app.get("/api/v1/publishers/{publisher_identifier}")
    async def publisher(publisher_identifier: str):
        return service.publisher(publisher_identifier)

    @app.get("/api/v1/evaluations")
    async def evaluations(
        limit: int = 25,
        offset: int = 0,
        publisher_id: str | None = None,
        model_id: str | None = None,
        method: str | None = None,
    ):
        return paginate(
            service.evaluations(
                publisher_id=publisher_id, model_id=model_id, method=method
            ),
            limit,
            offset,
        )

    @app.get("/api/v1/evaluations/{evaluation_identifier}")
    async def evaluation(evaluation_identifier: str):
        return service.evaluation(evaluation_identifier)

    @app.get("/api/v1/models")
    async def models(family: str | None = None, status: str | None = None):
        return {"items": service.models(family=family, status=status)}

    @app.post("/api/v1/models/scan", status_code=202)
    async def model_scan(_body: EmptyRequest):
        return {"job_id": jobs.submit("model_validation", {})}

    @app.post("/api/v1/evaluation-jobs", status_code=202)
    async def evaluation_job(body: EvaluationRequest):
        value = body.model_dump(mode="json")
        input_value = value["input"]
        if input_value["type"] != "article" and not value.get("aggregation_method"):
            raise AppError(
                "INVALID_INPUT", "Aggregation method is required for publisher results."
            )
        return {"job_id": jobs.submit("evaluation", value)}

    @app.get("/api/v1/jobs")
    async def list_jobs(
        limit: int = 25,
        offset: int = 0,
        status: str | None = None,
        job_type: str | None = None,
    ):
        return paginate(jobs.list(status=status, job_type=job_type), limit, offset)

    @app.get("/api/v1/jobs/{job_identifier}")
    async def get_job(job_identifier: str):
        return jobs.get(job_identifier)

    @app.get("/api/v1/imports")
    async def imports(limit: int = 25, offset: int = 0):
        return paginate(service.imports(), limit, offset)

    @app.get("/api/v1/imports/{import_identifier}")
    async def get_import(import_identifier: str):
        result = next(
            (row for row in service.imports() if row["import_id"] == import_identifier),
            None,
        )
        if result is None:
            raise AppError("NOT_FOUND", "Import was not found.")
        return result

    @app.post("/api/v1/imports/upload", status_code=202)
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
        return {
            "job_id": jobs.submit(
                "dataset_import",
                {"source_upload_id": token, "source_name": filename},
            )
        }

    @app.get("/api/v1/aggregation-methods")
    async def aggregation_methods():
        return {"items": METHODS}

    frontend = Path(__file__).with_name("frontend")
    app.mount("/assets", StaticFiles(directory=frontend), name="assets")

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def index():
        return FileResponse(frontend / "index.html")

    return app
