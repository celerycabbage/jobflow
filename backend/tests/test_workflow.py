from fastapi.testclient import TestClient


def test_complete_application_workflow(client: TestClient, auth_headers: dict[str, str]):
    company = client.post("/api/v1/companies", json={"name": "Example Labs"}, headers=auth_headers)
    assert company.status_code == 201

    resume = client.post(
        "/api/v1/resumes",
        json={"name": "Backend internship v1", "file_name": "resume.pdf"},
        headers=auth_headers,
    )
    assert resume.status_code == 201

    job = client.post(
        "/api/v1/jobs",
        json={
            "company_id": company.json()["id"],
            "title": "Backend Intern",
            "source_url": "https://example.com/jobs/1",
            "jd_text": "Build reliable APIs.",
        },
        headers=auth_headers,
    )
    assert job.status_code == 201

    application = client.post(
        "/api/v1/applications",
        json={
            "job_id": job.json()["id"],
            "resume_version_id": resume.json()["id"],
            "next_action_at": "2030-01-02T03:04:00Z",
        },
        headers=auth_headers,
    )
    assert application.status_code == 201
    assert application.json()["status"] == "saved"
    assert application.json()["next_action_at"] == "2030-01-02T03:04:00Z"

    moved = client.patch(
        f"/api/v1/applications/{application.json()['id']}/status",
        json={"status": "interview"},
        headers=auth_headers,
    )
    assert moved.status_code == 200
    assert moved.json()["status"] == "interview"

    timeline = client.get(
        f"/api/v1/applications/{application.json()['id']}/timeline", headers=auth_headers
    )
    assert [item["event_type"] for item in timeline.json()] == [
        "status_changed",
        "application_created",
    ]

    funnel = client.get("/api/v1/dashboard/funnel", headers=auth_headers)
    assert funnel.status_code == 200
    counts = {item["status"]: item["count"] for item in funnel.json()}
    assert counts["interview"] == 1


def test_jobs_are_isolated_between_users(client: TestClient, auth_headers: dict[str, str]):
    company = client.post(
        "/api/v1/companies", json={"name": "Private Company"}, headers=auth_headers
    ).json()
    client.post(
        "/api/v1/jobs",
        json={"company_id": company["id"], "title": "Private role"},
        headers=auth_headers,
    )

    other_token = client.post(
        "/api/v1/auth/register", json={"email": "other@example.com", "password": "password123"}
    ).json()["access_token"]
    response = client.get("/api/v1/jobs", headers={"Authorization": f"Bearer {other_token}"})
    assert response.status_code == 200
    assert response.json() == []


def test_duplicate_job_is_rejected(client: TestClient, auth_headers: dict[str, str]):
    company = client.post(
        "/api/v1/companies", json={"name": "Duplicate Inc"}, headers=auth_headers
    ).json()
    payload = {
        "company_id": company["id"],
        "title": "Platform Engineer",
        "source_url": "https://example.com/job/42",
    }
    assert client.post("/api/v1/jobs", json=payload, headers=auth_headers).status_code == 201
    assert client.post("/api/v1/jobs", json=payload, headers=auth_headers).status_code == 409


def test_resume_upload_and_authenticated_download(client: TestClient, auth_headers: dict[str, str]):
    uploaded = client.post(
        "/api/v1/resumes/upload",
        data={"name": "Backend PDF"},
        files={"file": ("backend-resume.pdf", b"%PDF-1.4 test", "application/pdf")},
        headers=auth_headers,
    )
    assert uploaded.status_code == 201
    assert uploaded.json()["file_name"] == "backend-resume.pdf"

    downloaded = client.get(
        f"/api/v1/resumes/{uploaded.json()['id']}/download", headers=auth_headers
    )
    assert downloaded.status_code == 200
    assert downloaded.content == b"%PDF-1.4 test"

    other_token = client.post(
        "/api/v1/auth/register",
        json={"email": "download-other@example.com", "password": "password123"},
    ).json()["access_token"]
    denied = client.get(
        f"/api/v1/resumes/{uploaded.json()['id']}/download",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert denied.status_code == 404
