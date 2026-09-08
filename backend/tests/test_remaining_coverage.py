import runpy
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from app import database, tasks, wait_for_database
from app.api import parse_csv_datetime, resume_signature_is_valid, settings
from app.celery_app import record_task_failure
from app.database import SessionLocal
from app.models import TaskFailure, UTCDateTime
from app.security import decode_access_token, verify_password


def create_company(client: TestClient, headers: dict[str, str], name: str) -> dict:
    response = client.post(
        "/api/v1/companies",
        json={"name": name, "website": f"https://{name.lower()}.example"},
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


def create_job(
    client: TestClient,
    headers: dict[str, str],
    company_id: int,
    title: str,
    source: str,
    source_url: str,
) -> dict:
    response = client.post(
        "/api/v1/jobs",
        json={
            "company_id": company_id,
            "title": title,
            "location": "Remote",
            "source": source,
            "source_url": source_url,
            "jd_text": f"Build {title}",
        },
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


def test_authentication_and_health_error_paths(
    client: TestClient, auth_headers: dict[str, str]
):
    assert client.get("/health").json() == {"status": "ok"}
    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    assert "http_requests_total" in metrics.text

    assert client.get("/api/v1/companies").status_code == 401
    assert (
        client.get(
            "/api/v1/companies", headers={"Authorization": "Bearer definitely-not-a-token"}
        ).status_code
        == 401
    )
    duplicate = client.post(
        "/api/v1/auth/register",
        json={"email": "OWNER@example.com", "password": "password123"},
    )
    assert duplicate.status_code == 409
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"email": "missing@example.com", "password": "password123"},
        ).status_code
        == 401
    )
    assert (
        client.patch(
            "/api/v1/auth/password",
            json={"current_password": "wrong-password", "new_password": "replacement-password"},
            headers=auth_headers,
        ).status_code
        == 400
    )


def test_company_and_resume_conflicts_and_file_cleanup(
    client: TestClient, auth_headers: dict[str, str]
):
    alpha = create_company(client, auth_headers, "Alpha")
    beta = create_company(client, auth_headers, "Beta")
    assert len(client.get("/api/v1/companies", headers=auth_headers).json()) == 2
    assert (
        client.post("/api/v1/companies", json={"name": "Alpha"}, headers=auth_headers).status_code
        == 409
    )
    assert (
        client.patch(
            f"/api/v1/companies/{beta['id']}",
            json={"name": "Alpha", "website": "https://updated.example"},
            headers=auth_headers,
        ).status_code
        == 409
    )
    updated = client.patch(
        f"/api/v1/companies/{beta['id']}",
        json={"website": "https://beta-updated.example"},
        headers=auth_headers,
    )
    assert updated.status_code == 200
    assert updated.json()["website"] == "https://beta-updated.example"

    create_job(client, auth_headers, alpha["id"], "Protected", "manual", "https://jobs/1")
    assert client.delete(f"/api/v1/companies/{alpha['id']}", headers=auth_headers).status_code == 409

    first = client.post("/api/v1/resumes", json={"name": "Primary"}, headers=auth_headers)
    second = client.post("/api/v1/resumes", json={"name": "Secondary"}, headers=auth_headers)
    assert first.status_code == second.status_code == 201
    assert len(client.get("/api/v1/resumes", headers=auth_headers).json()) == 2
    assert (
        client.post("/api/v1/resumes", json={"name": "Primary"}, headers=auth_headers).status_code
        == 409
    )
    assert (
        client.patch(
            f"/api/v1/resumes/{second.json()['id']}",
            json={"name": "Primary"},
            headers=auth_headers,
        ).status_code
        == 409
    )
    assert (
        client.get(
            f"/api/v1/resumes/{first.json()['id']}/download", headers=auth_headers
        ).status_code
        == 404
    )

    uploaded = client.post(
        "/api/v1/resumes/upload",
        data={"name": "Delete after upload"},
        files={"file": ("resume.doc", bytes.fromhex("D0CF11E0A1B11AE1") + b"body")},
        headers=auth_headers,
    )
    assert uploaded.status_code == 201
    uploaded_files = list(Path(settings.upload_dir).rglob("*.doc"))
    assert len(uploaded_files) == 1
    assert (
        client.delete(f"/api/v1/resumes/{uploaded.json()['id']}", headers=auth_headers).status_code
        == 204
    )
    assert not uploaded_files[0].exists()


def test_resume_upload_validation_conflicts_missing_file_and_account_cleanup(
    client: TestClient, auth_headers: dict[str, str]
):
    assert resume_signature_is_valid(".doc", bytes.fromhex("D0CF11E0A1B11AE1"))
    assert resume_signature_is_valid(".docx", b"PK data [Content_Types].xml")
    assert not resume_signature_is_valid(".docx", b"PK but incomplete")
    assert not resume_signature_is_valid(".txt", b"text")

    invalid_extension = client.post(
        "/api/v1/resumes/upload",
        data={"name": "Text"},
        files={"file": ("resume.txt", b"plain text")},
        headers=auth_headers,
    )
    assert invalid_extension.status_code == 415

    oversized = client.post(
        "/api/v1/resumes/upload",
        data={"name": "Too large"},
        files={"file": ("large.pdf", b"%PDF-" + b"x" * settings.max_upload_bytes)},
        headers=auth_headers,
    )
    assert oversized.status_code == 413

    first = client.post(
        "/api/v1/resumes/upload",
        data={"name": "Unique upload"},
        files={"file": ("first.pdf", b"%PDF-1.7 first")},
        headers=auth_headers,
    )
    assert first.status_code == 201
    duplicate = client.post(
        "/api/v1/resumes/upload",
        data={"name": "Unique upload"},
        files={"file": ("second.pdf", b"%PDF-1.7 second")},
        headers=auth_headers,
    )
    assert duplicate.status_code == 409

    stored_file = next(Path(settings.upload_dir).rglob("*.pdf"))
    stored_file.unlink()
    assert (
        client.get(
            f"/api/v1/resumes/{first.json()['id']}/download", headers=auth_headers
        ).status_code
        == 404
    )

    account_file = client.post(
        "/api/v1/resumes/upload",
        data={"name": "Account owned"},
        files={"file": ("account.docx", b"PK payload [Content_Types].xml")},
        headers=auth_headers,
    )
    assert account_file.status_code == 201
    account_path = next(Path(settings.upload_dir).rglob("*.docx"))
    assert client.delete("/api/v1/auth/account", headers=auth_headers).status_code == 204
    assert not account_path.exists()


def test_job_and_application_filter_update_and_conflict_paths(
    client: TestClient, auth_headers: dict[str, str]
):
    first_company = create_company(client, auth_headers, "First")
    second_company = create_company(client, auth_headers, "Second")
    first_job = create_job(
        client, auth_headers, first_company["id"], "Platform Engineer", "referral", "https://jobs/first"
    )
    second_job = create_job(
        client, auth_headers, second_company["id"], "Data Engineer", "board", "https://jobs/second"
    )

    assert [item["id"] for item in client.get("/api/v1/jobs?q=Build+Data", headers=auth_headers).json()] == [
        second_job["id"]
    ]
    assert [item["id"] for item in client.get("/api/v1/jobs?source=referral", headers=auth_headers).json()] == [
        first_job["id"]
    ]

    moved = client.patch(
        f"/api/v1/jobs/{second_job['id']}",
        json={"company_id": first_company["id"]},
        headers=auth_headers,
    )
    assert moved.status_code == 200
    conflict = client.patch(
        f"/api/v1/jobs/{second_job['id']}",
        json={"title": first_job["title"], "source_url": first_job["source_url"]},
        headers=auth_headers,
    )
    assert conflict.status_code == 409

    created = client.post(
        "/api/v1/applications",
        json={"job_id": first_job["id"], "status": "applied"},
        headers=auth_headers,
    )
    assert created.status_code == 201
    application_id = created.json()["id"]
    assert (
        client.post(
            "/api/v1/applications", json={"job_id": first_job["id"]}, headers=auth_headers
        ).status_code
        == 409
    )
    by_status = client.get("/api/v1/applications?status=applied", headers=auth_headers).json()
    by_source = client.get("/api/v1/applications?source=referral", headers=auth_headers).json()
    assert [item["id"] for item in by_status] == [application_id]
    assert [item["id"] for item in by_source] == [application_id]
    assert (
        client.patch(
            f"/api/v1/applications/{application_id}",
            json={"resume_version_id": 999999},
            headers=auth_headers,
        ).status_code
        == 404
    )


def test_csv_validation_limits_and_datetime_parsing(
    client: TestClient, auth_headers: dict[str, str]
):
    assert parse_csv_datetime(" ") is None
    naive = parse_csv_datetime("2030-01-02T03:04:05")
    aware = parse_csv_datetime("2030-01-02T11:04:05+08:00")
    assert naive == datetime(2030, 1, 2, 3, 4, 5, tzinfo=UTC)
    assert aware == naive

    too_large = client.post(
        "/api/v1/applications-import.csv",
        files={"file": ("large.csv", b"x" * 1_000_001)},
        headers=auth_headers,
    )
    assert too_large.status_code == 413
    invalid_encoding = client.post(
        "/api/v1/applications-import.csv",
        files={"file": ("invalid.csv", b"company,title\n\xff,Role")},
        headers=auth_headers,
    )
    assert invalid_encoding.status_code == 400
    missing_headers = client.post(
        "/api/v1/applications-import.csv",
        files={"file": ("missing.csv", b"name,role\nExample,Engineer")},
        headers=auth_headers,
    )
    assert missing_headers.status_code == 400

    many_rows = "company,title\n" + "\n".join("Repeated,Engineer" for _ in range(501))
    limited = client.post(
        "/api/v1/applications-import.csv",
        files={"file": ("many.csv", many_rows.encode())},
        headers=auth_headers,
    )
    assert limited.status_code == 200
    assert limited.json()["errors"][-1] == {
        "row": 502,
        "detail": "Only the first 500 rows are accepted",
    }


def test_security_datetime_celery_and_task_entrypoints(monkeypatch: pytest.MonkeyPatch):
    assert not verify_password("password", "legacy$1$bad$hash")
    assert not verify_password("password", "malformed")
    assert decode_access_token("not-a-token") is None

    column_type = UTCDateTime()
    naive_value = datetime.fromisoformat("2030-01-01T00:00:00")
    assert column_type.process_bind_param(None, None) is None
    assert column_type.process_bind_param(naive_value, None) == naive_value
    aware = datetime(2030, 1, 1, 8, tzinfo=timezone(timedelta(hours=8)))
    assert column_type.process_bind_param(aware, None) == naive_value
    assert column_type.process_result_value(None, None) is None
    assert column_type.process_result_value(naive_value, None).tzinfo == UTC
    assert column_type.process_result_value(aware, None) == datetime(2030, 1, 1, tzinfo=UTC)

    record_task_failure(
        task_id="failed-1",
        exception=RuntimeError("boom"),
        traceback="trace",
        sender=SimpleNamespace(name="app.tasks.example"),
    )
    with SessionLocal() as db:
        failure = db.scalar(select(TaskFailure).where(TaskFailure.task_id == "failed-1"))
        assert failure is not None
        assert failure.task_name == "app.tasks.example"
        assert failure.error == "boom"

    class FailingSession:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def add(self, _value):
            return None

        def commit(self):
            raise SQLAlchemyError("database unavailable")

    monkeypatch.setattr(database, "SessionLocal", lambda: FailingSession())
    assert record_task_failure(task_id="failed-2", exception=RuntimeError("ignored")) is None

    monkeypatch.setattr(tasks, "create_due_notifications", lambda: 11)
    monkeypatch.setattr(tasks, "create_stale_notifications", lambda: 12)
    monkeypatch.setattr(tasks, "create_weekly_reports", lambda: 13)
    assert tasks.scan_due_reminders.run() == 11
    assert tasks.scan_stale_applications.run() == 12
    assert tasks.generate_weekly_reports.run() == 13


def test_due_notification_defensive_skip(monkeypatch: pytest.MonkeyPatch):
    class ScalarResult:
        def all(self):
            return [SimpleNamespace(next_action_at=None)]

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def scalars(self, _statement):
            return ScalarResult()

    monkeypatch.setattr(tasks, "SessionLocal", lambda: FakeSession())
    assert tasks.create_due_notifications(datetime.now(UTC)) == 0


def test_wait_for_database_success_retry_timeout_and_module_entrypoint(
    monkeypatch: pytest.MonkeyPatch,
):
    wait_for_database.main()

    class WorkingConnection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, _statement):
            return None

    class RetryEngine:
        attempts = 0

        def connect(self):
            self.attempts += 1
            if self.attempts == 1:
                raise OperationalError("SELECT 1", {}, RuntimeError("starting"))
            return WorkingConnection()

    retry_engine = RetryEngine()
    monkeypatch.setattr(wait_for_database, "engine", retry_engine)
    monkeypatch.setattr(
        wait_for_database, "get_settings", lambda: SimpleNamespace(database_wait_seconds=10)
    )
    monkeypatch.setattr(wait_for_database.time, "monotonic", lambda: 0)
    sleeps: list[int] = []
    monkeypatch.setattr(wait_for_database.time, "sleep", sleeps.append)
    wait_for_database.main()
    assert retry_engine.attempts == 2
    assert sleeps == [2]

    class DownEngine:
        def connect(self):
            raise OperationalError("SELECT 1", {}, RuntimeError("down"))

    ticks = iter([0, 2])
    monkeypatch.setattr(wait_for_database, "engine", DownEngine())
    monkeypatch.setattr(
        wait_for_database, "get_settings", lambda: SimpleNamespace(database_wait_seconds=1)
    )
    monkeypatch.setattr(wait_for_database.time, "monotonic", lambda: next(ticks))
    with pytest.raises(SystemExit, match="Database did not become ready"):
        wait_for_database.main()

    monkeypatch.undo()
    with pytest.warns(RuntimeWarning, match="found in sys.modules"):
        runpy.run_module("app.wait_for_database", run_name="__main__")
