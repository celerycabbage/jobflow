"""Self-contained local API entry point for the Windows desktop package."""

from __future__ import annotations

import argparse
import logging
import os
import secrets
import shutil
import sqlite3
import sys
import threading
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger("jobflow.desktop_server")


def _data_directory() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    return base / "JobFlow" / "server"


def _bundle_directory() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))


def _configure_environment() -> tuple[Path, Path, bool]:
    data_directory = _data_directory()
    upload_directory = data_directory / "uploads"
    database_path = data_directory / "jobflow.db"
    database_existed = database_path.exists()
    data_directory.mkdir(parents=True, exist_ok=True)
    upload_directory.mkdir(parents=True, exist_ok=True)

    secret_path = data_directory / "server-secret.txt"
    if secret_path.exists():
        jwt_secret = secret_path.read_text(encoding="utf-8").strip()
    else:
        jwt_secret = secrets.token_urlsafe(48)
        secret_path.write_text(jwt_secret, encoding="utf-8")

    os.environ["DATABASE_URL"] = f"sqlite:///{database_path.as_posix()}"
    os.environ["UPLOAD_DIR"] = str(upload_directory)
    os.environ["JWT_SECRET"] = jwt_secret
    os.environ.setdefault("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
    return data_directory, database_path, database_existed


def _prepare_database(database_existed: bool) -> None:
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import inspect

    from app import models  # noqa: F401
    from app.database import Base, engine

    bundle_directory = _bundle_directory()
    config = Config(str(bundle_directory / "alembic.ini"))
    config.set_main_option("script_location", str(bundle_directory / "migrations"))

    if not database_existed or "users" not in inspect(engine).get_table_names():
        Base.metadata.create_all(engine)
        command.stamp(config, "head")
    else:
        command.upgrade(config, "head")


def _run_scheduler(stop_event: threading.Event) -> None:
    from app.tasks import (
        create_due_notifications,
        create_stale_notifications,
        create_weekly_reports,
    )

    last_daily_scan: str | None = None
    last_weekly_scan: str | None = None
    while not stop_event.is_set():
        now = datetime.now(UTC)
        try:
            create_due_notifications(now)
            daily_key = now.date().isoformat()
            if daily_key != last_daily_scan:
                create_stale_notifications(now)
                last_daily_scan = daily_key
            week = now.date().isocalendar()
            weekly_key = f"{week.year}-W{week.week:02d}"
            if weekly_key != last_weekly_scan:
                create_weekly_reports(now)
                last_weekly_scan = weekly_key
        except Exception:
            logger.exception("Embedded reminder scan failed")
        stop_event.wait(300)


def _create_backup(data_directory: Path, database_path: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    database_backup = destination / f"jobflow-{stamp}.db"
    with sqlite3.connect(database_path) as source, sqlite3.connect(database_backup) as target:
        source.backup(target)
    uploads = data_directory / "uploads"
    if uploads.exists():
        shutil.make_archive(str(destination / f"jobflow-uploads-{stamp}"), "zip", uploads)
    print(f"Backup saved to {destination}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backup", type=Path)
    args = parser.parse_args()

    data_directory, database_path, database_existed = _configure_environment()
    logging.basicConfig(
        filename=data_directory / "server.log",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    _prepare_database(database_existed)

    if args.backup:
        _create_backup(data_directory, database_path, args.backup)
        return 0

    (data_directory / "server.pid").write_text(str(os.getpid()), encoding="ascii")
    stop_event = threading.Event()
    threading.Thread(target=_run_scheduler, args=(stop_event,), daemon=True).start()

    import uvicorn

    try:
        uvicorn.run("app.main:app", host="127.0.0.1", port=8000, log_config=None)
    finally:
        stop_event.set()
        (data_directory / "server.pid").unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
