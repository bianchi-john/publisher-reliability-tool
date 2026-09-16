import re
import tempfile
import unittest
from pathlib import Path

from httpx import ASGITransport, AsyncClient

from publisher_reliability.api import create_app
from publisher_reliability.config import Config


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
            params={
                "input_type": "article",
                "url": "https://example.com/article",
            },
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


if __name__ == "__main__":
    unittest.main()
