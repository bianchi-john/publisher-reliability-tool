import re
import tempfile
import unittest
from pathlib import Path

from httpx import ASGITransport, AsyncClient

from publisher_reliability.api import create_app
from publisher_reliability.config import Config
from publisher_reliability.storage import HEADERS


class ApiTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.config = Config(
            port=8765,
            data_dir=Path(self.temporary.name) / "data",
            models_dirs=(),
            seed_dataset=Path(self.temporary.name) / "missing-seed",
            offline=True,
        )
        self.app = create_app(self.config)
        self.client = AsyncClient(
            transport=ASGITransport(app=self.app),
            base_url="http://127.0.0.1:8765",
        )

    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        self.app.state.jobs.stop()
        self.app.state.storage.close()
        self.temporary.cleanup()

    async def test_health_openapi_host_and_error_envelope(self) -> None:
        self.assertEqual(
            (await self.client.get("/health/live")).json(), {"status": "alive"}
        )
        self.assertEqual(
            (await self.client.get("/health/ready")).json(), {"status": "ready"}
        )

        openapi = await self.client.get("/api/openapi.json")
        self.assertEqual(openapi.status_code, 200)
        self.assertIn("/api/v1/articles", openapi.json()["paths"])
        self.assertIn("/api/v1/evaluation-jobs", openapi.json()["paths"])
        self.assertIn("/api/v1/models/available", openapi.json()["paths"])
        self.assertIn("/api/v1/models/upload", openapi.json()["paths"])
        self.assertIn("/api/v1/models/official-upload", openapi.json()["paths"])
        self.assertNotIn(
            "/api/v1/models/official-catalog", openapi.json()["paths"]
        )

        # The paper's large decoder checkpoints are not importable in this release.
        catalog = await self.client.get("/api/v1/models/official-catalog")
        self.assertEqual(catalog.status_code, 404)
        refused = await self.client.post(
            "/api/v1/models/official-upload",
            files={"files": ("llama_fold_1.pt.z01", b"irrelevant")},
        )
        self.assertEqual(refused.status_code, 501)
        self.assertEqual(refused.json()["error"]["code"], "FEATURE_UNAVAILABLE")

        missing = await self.client.get(
            "/api/v1/articles/00000000-0000-0000-0000-000000000000"
        )
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(missing.json()["error"]["code"], "NOT_FOUND")
        self.assertIn("request_id", missing.json()["error"])

        invalid_host = await self.client.get(
            "/health/live", headers={"Host": "127.0.0.1.evil:8765"}
        )
        self.assertEqual(invalid_host.status_code, 421)
        self.assertEqual(invalid_host.json()["error"]["code"], "INVALID_HOST")

        availability = await self.client.get(
            "/api/v1/models/available",
            params={"url": "https://example.com/article"},
        )
        self.assertEqual(availability.status_code, 200)
        self.assertEqual(availability.json()["items"], [])
        self.assertEqual(
            availability.json()["availability"]["code"],
            "NO_LOCAL_CHECKPOINTS",
        )

        invalid_model = await self.client.post(
            "/api/v1/models/upload",
            files={"file": ("unsafe.pt", b"not-a-bundle", "application/octet-stream")},
        )
        self.assertEqual(invalid_model.status_code, 422)
        self.assertEqual(invalid_model.json()["error"]["code"], "INVALID_INPUT")

    async def test_pagination_validation_uses_stable_error(self) -> None:
        response = await self.client.get("/api/v1/articles?limit=10")
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "INVALID_INPUT")

    async def test_clear_user_data_is_exposed_and_confirmation_checked(self) -> None:
        paths = (await self.client.get("/api/openapi.json")).json()["paths"]
        self.assertEqual(set(paths["/api/v1/user-data"]), {"delete"})

        wrong = await self.client.request(
            "DELETE", "/api/v1/user-data", json={"confirmation": "please"}
        )
        self.assertEqual(wrong.status_code, 422)
        self.assertEqual(wrong.json()["error"]["code"], "INVALID_INPUT")

        # Nothing to delete in a fresh workspace, but the confirmed call still
        # succeeds and reports zero of each, rather than treating "nothing local
        # yet" as an error.
        confirmed = await self.client.request(
            "DELETE", "/api/v1/user-data", json={"confirmation": "DELETE"}
        )
        self.assertEqual(confirmed.status_code, 200)
        self.assertEqual(
            confirmed.json(),
            {"deleted_predictions": 0, "deleted_saved_content": 0},
        )

    async def test_clear_jobs_needs_no_confirmation_body(self) -> None:
        paths = (await self.client.get("/api/openapi.json")).json()["paths"]
        self.assertEqual(set(paths["/api/v1/jobs"]), {"get", "delete"})

        # Unlike /api/v1/user-data, this one asks for nothing beyond the method: no
        # request body, no confirmation phrase.
        response = await self.client.delete("/api/v1/jobs")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"deleted": 0})

    async def test_only_single_articles_can_be_evaluated(self) -> None:
        """A publisher class is read, never requested as an evaluation."""

        refused = await self.client.post(
            "/api/v1/evaluation-jobs",
            json={
                "input": {"type": "publisher", "url": "https://outlet.example"},
                "model_id": "any-model",
            },
        )
        self.assertEqual(refused.status_code, 422)
        self.assertEqual(refused.json()["error"]["code"], "INVALID_INPUT")

        paths = (await self.client.get("/api/openapi.json")).json()["paths"]
        # Reading a publisher's class is a GET; there is no endpoint that creates one.
        aggregation = paths["/api/v1/publishers/{publisher_identifier}/aggregation"]
        self.assertEqual(set(aggregation), {"get"})

        # Availability is asked about one article and nothing else. The publisher
        # input, and the article-count options that only served it, are gone.
        parameters = paths["/api/v1/models/available"]["get"]["parameters"]
        self.assertEqual([item["name"] for item in parameters], ["url"])
        self.assertNotIn("/api/v1/publisher-evaluations", paths)
        self.assertNotIn("/api/v1/aggregation-jobs", paths)
        for path, operations in paths.items():
            if "publisher" in path:
                self.assertEqual(set(operations), {"get"}, path)

    async def test_unknown_publisher_aggregation_is_a_stable_not_found(self) -> None:
        response = await self.client.get(
            "/api/v1/publishers/00000000-0000-0000-0000-000000000000/aggregation"
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "NOT_FOUND")

    async def test_frontend_shell_is_served_with_its_referenced_assets(self) -> None:
        """Every script the shell points at must exist, and never be stale.

        The page is split across many small files with stable names and no build step,
        so a browser reusing a previous shell would ask for a script the current one no
        longer has. Each frontend response therefore has to be revalidated.
        """

        shell = await self.client.get("/")
        self.assertEqual(shell.status_code, 200)
        self.assertEqual(shell.headers["cache-control"], "no-cache")

        sources = re.findall(r'(?:src|href)="(/assets/[^"]+)"', shell.text)
        self.assertIn("/assets/js/app.js", sources)
        for source in sources:
            asset = await self.client.get(source)
            self.assertEqual(asset.status_code, 200, source)
            self.assertEqual(asset.headers["cache-control"], "no-cache", source)

    async def test_every_page_template_the_router_can_render_exists(self) -> None:
        entry = await self.client.get("/assets/js/templates.js")
        self.assertEqual(entry.status_code, 200)

        names = re.search(r"PAGE_TEMPLATES = \[(.*?)\]", entry.text, re.S)
        self.assertIsNotNone(names)
        templates = re.findall(r'"([a-z-]+)"', names.group(1))
        self.assertIn("evaluate", templates)
        for name in templates:
            page = await self.client.get(f"/assets/pages/{name}.html")
            self.assertEqual(page.status_code, 200, name)

    async def test_every_pager_is_told_how_many_rows_it_actually_drew(self) -> None:
        """The pager must never label a page with rows that are not on it.

        The list endpoints report the requested ``limit``, not the number of rows they
        answered with, so a pager left to infer the range from ``limit`` alone claims
        "Rows 26-50" on a final page holding two. There is no JavaScript runtime in
        this project's test environment, so the contract is pinned structurally here:
        every call site has to hand the pager the real row count.
        """

        for module in ("articles", "publishers", "publisher"):
            source = await self.client.get(f"/assets/js/pages/{module}.js")
            self.assertEqual(source.status_code, 200, module)
            calls = _pager_arguments(source.text)
            self.assertTrue(calls, f"{module}.js calls no pager")
            for call in calls:
                self.assertIn(".items.length", call, f"{module}.js: pager({call})")

    async def test_every_element_a_page_wires_up_exists_in_its_template(self) -> None:
        """A page module must not query an element its template does not define.

        `content.querySelector("#x")` returns null when the id is absent, and the very
        next line calls `addEventListener` on it, so a renamed id does not degrade the
        page: it throws and the whole route renders as an error card. There is no
        JavaScript runtime here, so the wiring is checked structurally instead.
        """

        page_of_module = {
            "articles": ["articles"],
            "article": ["article"],
            "publishers": ["publishers"],
            "publisher": ["publisher"],
            "models": ["models"],
            "jobs": ["jobs"],
            # The evaluate page also renders the shared result card.
            "evaluate": ["evaluate", "prediction-result"],
        }
        for module, pages in page_of_module.items():
            source = await self.client.get(f"/assets/js/pages/{module}.js")
            self.assertEqual(source.status_code, 200, module)
            markup = ""
            for page in pages:
                template = await self.client.get(f"/assets/pages/{page}.html")
                self.assertEqual(template.status_code, 200, page)
                markup += template.text
            queried = set(
                re.findall(r'content\.querySelector\("#([A-Za-z0-9_-]+)"\)', source.text)
            )
            defined = set(re.findall(r'id="([A-Za-z0-9_-]+)"', markup))
            self.assertEqual(
                queried - defined, set(), f"{module}.js queries ids missing from {pages}"
            )

    async def test_the_evaluate_form_fields_the_page_reads_exist(self) -> None:
        source = await self.client.get("/assets/js/pages/evaluate.js")
        template = await self.client.get("/assets/pages/evaluate.html")
        read = set(re.findall(r"\.elements\.([A-Za-z0-9_]+)", source.text))
        named = set(re.findall(r'name="([A-Za-z0-9_-]+)"', template.text))
        self.assertTrue(read, "evaluate.js reads no form field")
        self.assertEqual(read - named, set())

    async def test_status_reports_the_running_job_not_a_waiting_one(self) -> None:
        """With one FIFO worker, "current" means the job actually executing.

        Ledger order is least-recently-updated first, so an older queued row sits
        ahead of the running one it is waiting behind. Reporting that row as the
        current job would show the workspace as busy with work that has not started.
        """

        def row(job_id: str, status: str, created: str) -> dict[str, object]:
            record = {column: "" for column in HEADERS["jobs"]}
            record.update(
                job_id=job_id,
                job_type="model_validation",
                status=status,
                phase="",
                progress="0",
                request_json="{}",
                result_json="{}",
                created_at=created,
                updated_at=created,
            )
            return record

        storage = self.app.state.storage
        storage.upsert("jobs", "job_id", row("queued-old", "queued", "2026-01-01T00:00:00Z"))
        storage.upsert("jobs", "job_id", row("running", "running", "2026-01-02T00:00:00Z"))
        storage.upsert("jobs", "job_id", row("queued-new", "queued", "2026-01-03T00:00:00Z"))

        current = (await self.client.get("/api/v1/status")).json()["current_job"]

        self.assertEqual(current["job_id"], "running")
        self.assertEqual(current["status"], "running")

        # With nothing running, the oldest queued job is the one about to run.
        storage.delete("jobs", "job_id", "running")
        current = (await self.client.get("/api/v1/status")).json()["current_job"]
        self.assertEqual(current["job_id"], "queued-old")

        storage.replace("jobs", [])
        self.assertIsNone((await self.client.get("/api/v1/status")).json()["current_job"])

    async def test_a_page_never_draws_a_superseded_response(self) -> None:
        """Overlapping requests on one page must not let an older answer win.

        The router aborts in-flight work when the user navigates, but nothing cancels
        a second request the same page starts: typing again during a model lookup, or
        unticking several articles in a row, leaves two responses racing. Whichever
        arrives last would otherwise be drawn, which can describe a URL the field no
        longer holds or a selection the checkboxes no longer show.
        """

        for module in ("evaluate", "publisher"):
            source = (await self.client.get(f"/assets/js/pages/{module}.js")).text
            self.assertIn(
                "ticket",
                source,
                f"{module}.js does not guard against a superseded response",
            )
            # The guard has to sit between awaiting the response and drawing it.
            guard = re.compile(
                r"await api\([^;]*?\);\s*if \(ticket !== latest\w+\) return;", re.S
            )
            self.assertRegex(
                source,
                guard,
                f"{module}.js draws before checking whether it was superseded",
            )


def _pager_arguments(source: str) -> list[str]:
    """Extract the argument text of every ``pager(...)`` call in one module."""

    calls = []
    for start in range(len(source)):
        if not source.startswith("pager(", start):
            continue
        depth = 0
        for index in range(start + len("pager"), len(source)):
            if source[index] == "(":
                depth += 1
            elif source[index] == ")":
                depth -= 1
                if depth == 0:
                    calls.append(source[start + len("pager(") : index])
                    break
    return calls


if __name__ == "__main__":
    unittest.main()
