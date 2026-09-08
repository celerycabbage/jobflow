from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.tasks import create_due_notifications, create_stale_notifications, create_weekly_reports


def create_application_fixture(client: TestClient, headers: dict[str, str], suffix: str = "one"):
    company = client.post(
        "/api/v1/companies",
        json={"name": f"Company {suffix}", "website": "https://example.com"},
        headers=headers,
    ).json()
    resume = client.post(
        "/api/v1/resumes", json={"name": f"Resume {suffix}"}, headers=headers
    ).json()
    job = client.post(
        "/api/v1/jobs",
        json={
            "company_id": company["id"],
            "title": f"Engineer {suffix}",
            "source": "career-site",
            "source_url": f"https://example.com/jobs/{suffix}",
        },
        headers=headers,
    ).json()
    application = client.post(
        "/api/v1/applications",
        json={"job_id": job["id"], "resume_version_id": resume["id"]},
        headers=headers,
    ).json()
    return company, resume, job, application


def test_crud_search_export_and_cleanup(client: TestClient, auth_headers: dict[str, str]):
    company, resume, job, application = create_application_fixture(client, auth_headers)

    updated_company = client.patch(
        f"/api/v1/companies/{company['id']}",
        json={"name": "Renamed Company"},
        headers=auth_headers,
    )
    assert updated_company.status_code == 200
    assert updated_company.json()["name"] == "Renamed Company"

    updated_resume = client.patch(
        f"/api/v1/resumes/{resume['id']}",
        json={"name": "Resume final"},
        headers=auth_headers,
    )
    assert updated_resume.status_code == 200

    updated_job = client.patch(
        f"/api/v1/jobs/{job['id']}",
        json={"title": "Senior Engineer", "location": "Remote"},
        headers=auth_headers,
    )
    assert updated_job.status_code == 200
    assert updated_job.json()["location"] == "Remote"

    updated_application = client.patch(
        f"/api/v1/applications/{application['id']}",
        json={"notes": "Prepare system design", "resume_version_id": None},
        headers=auth_headers,
    )
    assert updated_application.status_code == 200
    assert updated_application.json()["notes"] == "Prepare system design"
    assert updated_application.json()["resume_version_id"] is None

    search = client.get("/api/v1/applications?q=Senior", headers=auth_headers)
    assert [item["id"] for item in search.json()] == [application["id"]]

    exported = client.get("/api/v1/applications-export.csv", headers=auth_headers)
    assert exported.status_code == 200
    assert "Renamed Company,Senior Engineer" in exported.text

    assert (
        client.delete(f"/api/v1/jobs/{job['id']}", headers=auth_headers).status_code == 409
    )
    assert (
        client.delete(f"/api/v1/applications/{application['id']}", headers=auth_headers).status_code
        == 204
    )
    assert client.delete(f"/api/v1/jobs/{job['id']}", headers=auth_headers).status_code == 204
    assert (
        client.delete(f"/api/v1/companies/{company['id']}", headers=auth_headers).status_code
        == 204
    )
    assert client.delete(f"/api/v1/resumes/{resume['id']}", headers=auth_headers).status_code == 204


def test_insights_are_derived_from_timeline(client: TestClient, auth_headers: dict[str, str]):
    _, _, _, application = create_application_fixture(client, auth_headers, "insights")
    for target in ("applied", "interview", "offer"):
        response = client.patch(
            f"/api/v1/applications/{application['id']}/status",
            json={"status": target},
            headers=auth_headers,
        )
        assert response.status_code == 200

    insights = client.get("/api/v1/dashboard/insights", headers=auth_headers).json()
    assert insights["offer_rate"] == 100.0
    stages = {item["status"]: item for item in insights["stages"]}
    assert stages["interview"]["ever_reached"] == 1
    assert stages["offer"]["current_count"] == 1
    assert insights["sources"] == [
        {"source": "career-site", "total": 1, "interviews": 1, "offers": 1}
    ]
    assert insights["resumes"] == [
        {"resume": "Resume insights", "total": 1, "interviews": 1, "offers": 1}
    ]
    assert insights["average_days_to_offer"] is not None
    assert len(insights["weekly_trend"]) == 1


def test_due_reminders_are_idempotent(client: TestClient, auth_headers: dict[str, str]):
    _, _, _, application = create_application_fixture(client, auth_headers, "reminder")
    now = datetime.now(UTC)
    due_at = now + timedelta(hours=2)
    response = client.patch(
        f"/api/v1/applications/{application['id']}",
        json={"next_action_at": due_at.isoformat()},
        headers=auth_headers,
    )
    assert response.status_code == 200

    assert create_due_notifications(now) == 1
    assert create_due_notifications(now) == 0
    notifications = client.get("/api/v1/notifications?unread_only=true", headers=auth_headers)
    assert notifications.status_code == 200
    assert len(notifications.json()) == 1
    notification_id = notifications.json()[0]["id"]
    marked = client.patch(
        f"/api/v1/notifications/{notification_id}/read", headers=auth_headers
    )
    assert marked.status_code == 200
    assert marked.json()["read_at"] is not None


def test_password_change(client: TestClient, auth_headers: dict[str, str]):
    changed = client.patch(
        "/api/v1/auth/password",
        json={"current_password": "password123", "new_password": "new-password-456"},
        headers=auth_headers,
    )
    assert changed.status_code == 204
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": "new-password-456"},
    )
    assert login.status_code == 200


def test_csv_import_and_archive_restore(client: TestClient, auth_headers: dict[str, str]):
    csv_content = (
        "company,title,status,location,source,source_url,notes\n"
        "Imported Inc,Platform Engineer,applied,Remote,referral,https://example.com/1,Hello\n"
        "Imported Inc,Platform Engineer,applied,Remote,referral,https://example.com/1,Duplicate\n"
        "Bad Row,,saved,,,,\n"
    )
    imported = client.post(
        "/api/v1/applications-import.csv",
        files={"file": ("applications.csv", csv_content, "text/csv")},
        headers=auth_headers,
    )
    assert imported.status_code == 200
    assert imported.json()["imported"] == 1
    assert imported.json()["skipped"] == 1
    assert imported.json()["errors"][0]["row"] == 4

    application = client.get("/api/v1/applications", headers=auth_headers).json()[0]
    archived = client.patch(
        f"/api/v1/applications/{application['id']}/archive", headers=auth_headers
    )
    assert archived.status_code == 200
    assert archived.json()["archived_at"] is not None
    assert client.get("/api/v1/applications", headers=auth_headers).json() == []
    assert len(client.get("/api/v1/applications?archived=true", headers=auth_headers).json()) == 1
    restored = client.patch(
        f"/api/v1/applications/{application['id']}/restore", headers=auth_headers
    )
    assert restored.status_code == 200
    assert restored.json()["archived_at"] is None


def test_invalid_resume_signature_is_rejected(client: TestClient, auth_headers: dict[str, str]):
    response = client.post(
        "/api/v1/resumes/upload",
        data={"name": "Not really a PDF"},
        files={"file": ("resume.pdf", b"plain text", "application/pdf")},
        headers=auth_headers,
    )
    assert response.status_code == 415


def test_stale_and_weekly_notifications_are_idempotent(
    client: TestClient, auth_headers: dict[str, str]
):
    _, _, _, application = create_application_fixture(client, auth_headers, "async")
    client.patch(
        f"/api/v1/applications/{application['id']}/status",
        json={"status": "applied"},
        headers=auth_headers,
    )
    future = datetime.now(UTC) + timedelta(days=15)
    assert create_stale_notifications(future) == 1
    assert create_stale_notifications(future) == 0
    assert create_weekly_reports(datetime.now(UTC)) == 1
    assert create_weekly_reports(datetime.now(UTC)) == 0
    notifications = client.get("/api/v1/notifications", headers=auth_headers).json()
    assert {item["kind"] for item in notifications} == {"no_feedback", "weekly_report"}
