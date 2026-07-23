"""Command-line interface for the local research demo."""

from __future__ import annotations

import argparse
import json
import socket
import sys
import tempfile
from pathlib import Path

from .config import Config
from .errors import AppError
from .importer import import_bundled_release, import_csv, verify_manifest
from .storage import Storage


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="publisher-reliability")
    commands = root.add_subparsers(dest="command", required=True)

    serve = commands.add_parser("serve", help="Start the loopback-only web application")
    serve.add_argument("--port", type=int)
    serve.add_argument("--data-dir", type=Path)
    serve.add_argument("--models-dir", type=Path, action="append")
    serve.add_argument("--seed-dataset", type=Path)
    serve.add_argument("--offline", action="store_true", default=None)
    serve.add_argument("--device", choices=("auto", "cpu", "cuda"))
    serve.add_argument("--log-level", choices=("debug", "info", "warning", "error"))

    dataset = commands.add_parser("dataset", help="Verify or import predictions")
    dataset_commands = dataset.add_subparsers(dest="dataset_command", required=True)
    verify = dataset_commands.add_parser("verify")
    verify.add_argument("path", type=Path)
    data_import = dataset_commands.add_parser("import")
    data_import.add_argument("path", type=Path)
    data_import.add_argument("--data-dir", type=Path)

    models = commands.add_parser("models", help="Manage official model artifacts")
    model_commands = models.add_subparsers(dest="models_command", required=True)
    scan = model_commands.add_parser("scan")
    scan.add_argument("--data-dir", type=Path)

    storage = commands.add_parser("storage", help="Inspect persistent CSV state")
    storage_commands = storage.add_subparsers(dest="storage_command", required=True)
    storage_verify = storage_commands.add_parser("verify")
    storage_verify.add_argument("--data-dir", type=Path)
    return root


def _config_with_args(args: argparse.Namespace) -> Config:
    config = Config.from_env()
    for argument, attribute in (
        ("port", "port"),
        ("data_dir", "data_dir"),
        ("seed_dataset", "seed_dataset"),
        ("device", "device"),
        ("log_level", "log_level"),
    ):
        value = getattr(args, argument, None)
        if value is not None:
            setattr(config, attribute, value)
    if getattr(args, "models_dir", None):
        config.models_dirs = tuple(args.models_dir)
    if getattr(args, "offline", None) is not None:
        config.offline = args.offline
    config.validate()
    return config


def _serve(args: argparse.Namespace) -> int:
    config = _config_with_args(args)
    bind_host = "0.0.0.0" if config.container_internal else "127.0.0.1"
    reservation = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        reservation.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        reservation.bind((bind_host, config.port))
        reservation.listen(128)
    except OSError as exc:
        reservation.close()
        raise AppError(
            "INVALID_INPUT",
            f"Port {config.port} is unavailable; no data directory was changed.",
        ) from exc

    try:
        from uvicorn import Config as UvicornConfig, Server
        from .api import create_app

        app = create_app(config)
        print(f"UI:      http://127.0.0.1:{config.port}/")
        print(f"API:     http://127.0.0.1:{config.port}/api/v1/status")
        print(f"Docs:    http://127.0.0.1:{config.port}/api/docs")
        print(f"Offline: {str(config.offline).lower()}  Device: {config.device}")
        server = Server(
            UvicornConfig(
                app,
                host=bind_host,
                port=config.port,
                log_level=config.log_level,
                workers=1,
            )
        )
        try:
            server.run(sockets=[reservation])
        except KeyboardInterrupt:
            pass
        return 0
    finally:
        reservation.close()


def _dataset_verify(path: Path) -> int:
    if path.is_dir():
        result = verify_manifest(path)
        print(
            json.dumps(
                {
                    "records": result["records"],
                    "parts": len(result["parts"]),
                    "content_sha256": result["content_digest_sha256"],
                },
                indent=2,
            )
        )
        return 0
    if not path.is_file():
        raise AppError("INVALID_INPUT", "Dataset path does not exist.")
    with tempfile.TemporaryDirectory(prefix="prt-verify-") as temporary:
        with Storage(Path(temporary) / "data") as storage:
            result = import_csv(storage, path)
    print(
        json.dumps(
            {
                "status": result["status"],
                "source_rows": int(result["source_rows"]),
                "accepted_rows": int(result["accepted_rows"]),
                "content_sha256": result["content_sha256"],
            },
            indent=2,
        )
    )
    return 0


def _dataset_import(args: argparse.Namespace) -> int:
    config = Config.from_env()
    data_dir = args.data_dir or config.data_dir
    with Storage(data_dir) as storage:
        result = (
            import_bundled_release(storage, args.path)
            if args.path.is_dir()
            else import_csv(storage, args.path)
        )
    print(json.dumps(result, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "serve":
            return _serve(args)
        if args.command == "dataset":
            if args.dataset_command == "verify":
                return _dataset_verify(args.path)
            return _dataset_import(args)
        if args.command == "storage":
            config = Config.from_env()
            with Storage(args.data_dir or config.data_dir) as storage:
                print(json.dumps(storage.verify(), indent=2))
            return 0
        if args.command == "models":
            config = Config.from_env()
            with Storage(args.data_dir or config.data_dir):
                print(
                    json.dumps(
                        {
                            "registered": 0,
                            "message": "No supported official artifacts were found.",
                        },
                        indent=2,
                    )
                )
            return 0
    except AppError as exc:
        print(f"{exc.code}: {exc.message}", file=sys.stderr)
        if exc.code == "STORAGE_ERROR":
            return 3
        if exc.code in {"IMPORT_INVALID"}:
            return 3
        return 2
    except Exception:
        print("INTERNAL_ERROR: The command failed unexpectedly.", file=sys.stderr)
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
