from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient


def create_item(client: TestClient, headers: dict[str, str], suffix: str, *, resume_text: str = "Python SQL Docker"):
    company = client.post("/api/v1/companies", json={"name": f"Org {suffix}"}, headers=headers).json()
    resume = client.post("/api/v1/resumes", json={"name": f"CV {suffix}", "content_text": resume_text}, headers=headers).json()
    job = client.post("/api/v1/jobs", json={
        "company_id": company["id"], "title": f"Engineer {suffix}",
        "source_url": f"https://example.com/{suffix}",
        "jd_text": "Python SQL Docker Kubernetes 系统设计 沟通",
    }, headers=headers).json()
    application = client.post("/api/v1/applications", json={
        "job_id": job["id"], "resume_version_id": resume["id"],
        "tags": ["重点", "重点", " 远程 "], "custom_fields": {"薪资": "30k"},
    }, headers=headers).json()
    return company, resume, job, application


def test_matching_metadata_exports_and_resume_text(client: TestClient, auth_headers: dict[str, str]):
    _, resume, _, application = create_item(client, auth_headers, "match")
    assert set(application["tags"]) == {"重点", "远程"}
    assert application["custom_fields"] == {"薪资": "30k"}
    match = client.get(f"/api/v1/applications/{application['id']}/match", headers=auth_headers).json()
    assert match["score"] == 50
    assert match["matched_keywords"] == ["python", "sql", "docker"]
    assert "kubernetes" in match["missing_keywords"]
    assert match["questions"]

    updated = client.patch(f"/api/v1/applications/{application['id']}", json={
        "tags": ["校招"], "custom_fields": {"优先级": "高"}
    }, headers=auth_headers).json()
    assert updated["tags"] == ["校招"]
    assert updated["custom_fields"] == {"优先级": "高"}
    renamed = client.patch(f"/api/v1/resumes/{resume['id']}", json={
        "name": "CV updated", "content_text": "Python SQL Docker Kubernetes 系统设计 沟通"
    }, headers=auth_headers)
    assert renamed.status_code == 200
    assert client.get(f"/api/v1/applications/{application['id']}/match", headers=auth_headers).json()["score"] == 100

    exported = client.get("/api/v1/applications-export.json", headers=auth_headers)
    assert exported.status_code == 200
    assert exported.json()[0]["custom_fields"] == {"优先级": "高"}
    assert "jobflow-applications.json" in exported.headers["content-disposition"]


def test_interviews_conflicts_calendar_and_crud(client: TestClient, auth_headers: dict[str, str]):
    _, _, _, application = create_item(client, auth_headers, "round")
    scheduled = datetime.now(UTC) + timedelta(days=2)
    created = client.post(f"/api/v1/applications/{application['id']}/interviews", json={
        "round_name": "技术一面", "interview_type": "video",
        "scheduled_at": scheduled.isoformat(), "duration_minutes": 60,
        "location": "https://meeting.example", "interviewer": "Alex", "notes": "系统设计",
    }, headers=auth_headers)
    assert created.status_code == 201
    interview = created.json()
    assert client.get(f"/api/v1/applications/{application['id']}/interviews", headers=auth_headers).json()[0]["round_name"] == "技术一面"
    assert client.get("/api/v1/applications", headers=auth_headers).json()[0]["status"] == "interview"

    _, _, _, other = create_item(client, auth_headers, "round-other")
    conflict = client.post(f"/api/v1/applications/{other['id']}/interviews", json={
        "round_name": "冲突面试", "scheduled_at": (scheduled + timedelta(minutes=30)).isoformat(),
    }, headers=auth_headers)
    assert conflict.status_code == 409

    patched = client.patch(f"/api/v1/interviews/{interview['id']}", json={
        "round_name": "技术二面", "outcome": "passed", "duration_minutes": 90,
        "scheduled_at": (scheduled + timedelta(hours=2)).isoformat(),
    }, headers=auth_headers)
    assert patched.status_code == 200
    assert patched.json()["outcome"] == "passed"
    calendar = client.get("/api/v1/calendar.ics", headers=auth_headers)
    assert "BEGIN:VCALENDAR" in calendar.text
    assert "interview-" in calendar.text
    assert "application-" not in calendar.text
    assert client.delete(f"/api/v1/interviews/{interview['id']}", headers=auth_headers).status_code == 204


def test_bulk_undo_merge_and_sample_data(client: TestClient, auth_headers: dict[str, str]):
    _, _, _, first = create_item(client, auth_headers, "first")
    _, _, _, second = create_item(client, auth_headers, "second")
    bulk = client.patch("/api/v1/application-actions/bulk-status", json={
        "application_ids": [first["id"], second["id"], first["id"]], "status": "applied"
    }, headers=auth_headers)
    assert bulk.status_code == 200
    assert {item["status"] for item in bulk.json()} == {"applied"}
    assert client.patch("/api/v1/application-actions/bulk-status", json={
        "application_ids": [second["id"]], "status": "applied"
    }, headers=auth_headers).status_code == 200
    undone = client.post(f"/api/v1/applications/{first['id']}/undo-status", headers=auth_headers)
    assert undone.json()["status"] == "saved"
    assert client.post(f"/api/v1/applications/{first['id']}/undo-status", headers=auth_headers).status_code == 409
    assert client.patch("/api/v1/application-actions/bulk-status", json={
        "application_ids": [99999], "status": "closed"
    }, headers=auth_headers).status_code == 404

    assert client.post(f"/api/v1/applications/{second['id']}/interviews", json={
        "round_name": "待合并面试", "scheduled_at": (datetime.now(UTC) + timedelta(days=5)).isoformat()
    }, headers=auth_headers).status_code == 201
    merged = client.post(f"/api/v1/applications/{first['id']}/merge", json={
        "source_application_id": second["id"]
    }, headers=auth_headers)
    assert merged.status_code == 200
    assert len(client.get("/api/v1/applications", headers=auth_headers).json()) == 1
    assert client.get(f"/api/v1/applications/{first['id']}/interviews", headers=auth_headers).json()[0]["round_name"] == "待合并面试"
    assert client.post(f"/api/v1/applications/{first['id']}/merge", json={
        "source_application_id": first["id"]
    }, headers=auth_headers).status_code == 400

    # A new account has an empty workspace and can opt into sample content.
    token = client.post("/api/v1/auth/register", json={"email": "sample@example.com", "password": "password123"}).json()["access_token"]
    sample_headers = {"Authorization": f"Bearer {token}"}
    sample = client.post("/api/v1/sample-data", headers=sample_headers)
    assert sample.status_code == 201
    assert client.post("/api/v1/sample-data", headers=sample_headers).status_code == 409
    app = client.get("/api/v1/applications", headers=sample_headers).json()[0]
    assert client.get(f"/api/v1/applications/{app['id']}/match", headers=sample_headers).json()["score"] > 0
    assert "VALARM" in client.get("/api/v1/calendar.ics", headers=sample_headers).text


def test_match_guidance_without_inputs(client: TestClient, auth_headers: dict[str, str]):
    company = client.post("/api/v1/companies", json={"name": "Sparse"}, headers=auth_headers).json()
    resume = client.post("/api/v1/resumes", json={"name": "Blank"}, headers=auth_headers).json()
    job = client.post("/api/v1/jobs", json={"company_id": company["id"], "title": "Role"}, headers=auth_headers).json()
    app = client.post("/api/v1/applications", json={"job_id": job["id"], "resume_version_id": resume["id"]}, headers=auth_headers).json()
    assert "JD" in client.get(f"/api/v1/applications/{app['id']}/match", headers=auth_headers).json()["recommendation"]
    client.patch(f"/api/v1/jobs/{job['id']}", json={"jd_text": "Python"}, headers=auth_headers)
    assert "简历" in client.get(f"/api/v1/applications/{app['id']}/match", headers=auth_headers).json()["recommendation"]
    client.patch(f"/api/v1/resumes/{resume['id']}", json={"name": "Blank", "content_text": "unrelated"}, headers=auth_headers)
    assert "覆盖较低" in client.get(f"/api/v1/applications/{app['id']}/match", headers=auth_headers).json()["recommendation"]
