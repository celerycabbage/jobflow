import csv
import hashlib
import io
import json
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from .config import get_settings
from .database import get_db
from .dependencies import get_current_user
from .models import (
    Application,
    ApplicationStatus,
    Company,
    InterviewRound,
    Job,
    Notification,
    ResumeVersion,
    TimelineEvent,
    User,
)
from .schemas import (
    ApplicationCreate,
    ApplicationRead,
    ApplicationStatusUpdate,
    ApplicationUpdate,
    BulkStatusUpdate,
    CompanyCreate,
    CompanyRead,
    CompanyUpdate,
    CSVImportError,
    CSVImportResult,
    DashboardInsights,
    FunnelItem,
    InterviewCreate,
    InterviewRead,
    InterviewUpdate,
    JobCreate,
    JobRead,
    JobUpdate,
    LoginRequest,
    MatchResult,
    MergeApplications,
    NotificationRead,
    PasswordChange,
    ResumeCreate,
    ResumeInsight,
    ResumeRead,
    ResumeUpdate,
    SourceInsight,
    StageInsight,
    TimelineRead,
    TokenResponse,
    UserCreate,
    WeeklyTrend,
)
from .security import create_access_token, hash_password, verify_password

router = APIRouter()
settings = get_settings()
ALLOWED_RESUME_SUFFIXES = {".pdf", ".doc", ".docx"}
CSV_IMPORT_LIMIT = 500


def normalize(value: str | None) -> str:
    return " ".join((value or "").strip().lower().split())


def job_fingerprint(user_id: int, company_id: int, payload: JobCreate) -> str:
    identity = f"{user_id}|{company_id}|{normalize(payload.title)}|{normalize(payload.source_url)}"
    return hashlib.sha256(identity.encode()).hexdigest()


def resume_signature_is_valid(suffix: str, content: bytes) -> bool:
    if suffix == ".pdf":
        return content.startswith(b"%PDF-")
    if suffix == ".doc":
        return content.startswith(bytes.fromhex("D0CF11E0A1B11AE1"))
    if suffix == ".docx":
        return content.startswith(b"PK") and b"[Content_Types].xml" in content
    return False


def owned_or_404(db: Session, model: type, object_id: int, user_id: int):
    value = db.scalar(select(model).where(model.id == object_id, model.user_id == user_id))
    if value is None:
        raise HTTPException(status_code=404, detail=f"{model.__name__} not found")
    return value


@router.post("/auth/register", response_model=TokenResponse, status_code=201)
def register(payload: UserCreate, db: Session = Depends(get_db)) -> TokenResponse:
    normalized_email = payload.email.lower()
    if db.scalar(select(User).where(User.email == normalized_email)):
        raise HTTPException(status_code=409, detail="Email already registered")
    user = User(email=normalized_email, password_hash=hash_password(payload.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return TokenResponse(access_token=create_access_token(user.id))


@router.post("/auth/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    return TokenResponse(access_token=create_access_token(user.id))


@router.patch("/auth/password", status_code=204)
def change_password(
    payload: PasswordChange,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    user.password_hash = hash_password(payload.new_password)
    db.commit()


@router.delete("/auth/account", status_code=204)
def delete_account(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> None:
    storage_keys = db.scalars(
        select(ResumeVersion.storage_key).where(
            ResumeVersion.user_id == user.id, ResumeVersion.storage_key.is_not(None)
        )
    ).all()
    db.delete(user)
    db.commit()
    for storage_key in storage_keys:
        if storage_key:
            (settings.upload_dir / storage_key).unlink(missing_ok=True)


@router.get("/companies", response_model=list[CompanyRead])
def list_companies(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list[Company]:
    return list(
        db.scalars(select(Company).where(Company.user_id == user.id).order_by(Company.name))
    )


@router.post("/companies", response_model=CompanyRead, status_code=201)
def create_company(
    payload: CompanyCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Company:
    company = Company(user_id=user.id, name=payload.name.strip(), website=payload.website)
    db.add(company)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Company already exists") from exc
    db.refresh(company)
    return company


@router.patch("/companies/{company_id}", response_model=CompanyRead)
def update_company(
    company_id: int,
    payload: CompanyUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Company:
    company = owned_or_404(db, Company, company_id, user.id)
    changes = payload.model_dump(exclude_unset=True)
    if "name" in changes:
        company.name = changes["name"].strip()
    if "website" in changes:
        company.website = changes["website"]
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Company already exists") from exc
    db.refresh(company)
    return company


@router.delete("/companies/{company_id}", status_code=204)
def delete_company(
    company_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    company = owned_or_404(db, Company, company_id, user.id)
    if db.scalar(select(Job.id).where(Job.company_id == company.id).limit(1)) is not None:
        raise HTTPException(status_code=409, detail="Delete this company's jobs first")
    db.delete(company)
    db.commit()


@router.get("/resumes", response_model=list[ResumeRead])
def list_resumes(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list[ResumeVersion]:
    statement = (
        select(ResumeVersion)
        .where(ResumeVersion.user_id == user.id)
        .order_by(ResumeVersion.created_at.desc())
    )
    return list(db.scalars(statement))


@router.post("/resumes", response_model=ResumeRead, status_code=201)
def create_resume(
    payload: ResumeCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ResumeVersion:
    resume = ResumeVersion(
        user_id=user.id, name=payload.name.strip(), file_name=payload.file_name,
        content_text=payload.content_text,
    )
    db.add(resume)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Resume version already exists") from exc
    db.refresh(resume)
    return resume


@router.patch("/resumes/{resume_id}", response_model=ResumeRead)
def update_resume(
    resume_id: int,
    payload: ResumeUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ResumeVersion:
    resume = owned_or_404(db, ResumeVersion, resume_id, user.id)
    resume.name = payload.name.strip()
    if "content_text" in payload.model_fields_set:
        resume.content_text = payload.content_text
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Resume version already exists") from exc
    db.refresh(resume)
    return resume


@router.delete("/resumes/{resume_id}", status_code=204)
def delete_resume(
    resume_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    resume = owned_or_404(db, ResumeVersion, resume_id, user.id)
    storage_key = resume.storage_key
    db.delete(resume)
    db.commit()
    if storage_key:
        (settings.upload_dir / storage_key).unlink(missing_ok=True)


@router.post("/resumes/upload", response_model=ResumeRead, status_code=201)
async def upload_resume(
    name: Annotated[str, Form(min_length=1, max_length=120)],
    file: Annotated[UploadFile, File()],
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ResumeVersion:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_RESUME_SUFFIXES:
        raise HTTPException(status_code=415, detail="Only PDF, DOC, and DOCX files are supported")

    content = await file.read(settings.max_upload_bytes + 1)
    await file.close()
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="Resume file must not exceed 5 MB")
    if not resume_signature_is_valid(suffix, content):
        raise HTTPException(status_code=415, detail="File content does not match its extension")

    storage_key = f"{user.id}/{uuid4().hex}{suffix}"
    destination = settings.upload_dir / storage_key
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(content)

    resume = ResumeVersion(
        user_id=user.id,
        name=name.strip(),
        file_name=Path(file.filename or f"resume{suffix}").name,
        storage_key=storage_key,
    )
    db.add(resume)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        destination.unlink(missing_ok=True)
        raise HTTPException(status_code=409, detail="Resume version already exists") from exc
    db.refresh(resume)
    return resume


@router.get("/resumes/{resume_id}/download")
def download_resume(
    resume_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FileResponse:
    resume = owned_or_404(db, ResumeVersion, resume_id, user.id)
    if not resume.storage_key:
        raise HTTPException(status_code=404, detail="This resume version has no uploaded file")
    upload_root = settings.upload_dir.resolve()
    source = (settings.upload_dir / resume.storage_key).resolve()
    if upload_root not in source.parents or not source.is_file():
        raise HTTPException(status_code=404, detail="Resume file not found")
    return FileResponse(source, filename=resume.file_name or source.name)


@router.get("/jobs", response_model=list[JobRead])
def list_jobs(
    q: str | None = None,
    source: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[Job]:
    statement = select(Job).options(joinedload(Job.company)).where(Job.user_id == user.id)
    if q:
        pattern = f"%{q.strip()}%"
        statement = statement.where(
            or_(Job.title.ilike(pattern), Job.location.ilike(pattern), Job.jd_text.ilike(pattern))
        )
    if source:
        statement = statement.where(Job.source == source)
    statement = statement.order_by(Job.created_at.desc()).offset(offset).limit(limit)
    return list(db.scalars(statement))


@router.post("/jobs", response_model=JobRead, status_code=201)
def create_job(
    payload: JobCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Job:
    owned_or_404(db, Company, payload.company_id, user.id)
    job = Job(
        user_id=user.id,
        company_id=payload.company_id,
        title=payload.title.strip(),
        location=payload.location,
        source=payload.source,
        source_url=payload.source_url,
        jd_text=payload.jd_text,
        fingerprint=job_fingerprint(user.id, payload.company_id, payload),
    )
    db.add(job)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="This job has already been saved") from exc
    return db.scalar(select(Job).options(joinedload(Job.company)).where(Job.id == job.id))


@router.patch("/jobs/{job_id}", response_model=JobRead)
def update_job(
    job_id: int,
    payload: JobUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Job:
    job = owned_or_404(db, Job, job_id, user.id)
    changes = payload.model_dump(exclude_unset=True)
    if "company_id" in changes:
        owned_or_404(db, Company, changes["company_id"], user.id)
        job.company_id = changes["company_id"]
    for field in ("location", "source", "source_url", "jd_text"):
        if field in changes:
            setattr(job, field, changes[field])
    if "title" in changes:
        job.title = changes["title"].strip()
    fingerprint_payload = JobCreate(
        company_id=job.company_id,
        title=job.title,
        location=job.location,
        source=job.source,
        source_url=job.source_url,
        jd_text=job.jd_text,
    )
    job.fingerprint = job_fingerprint(user.id, job.company_id, fingerprint_payload)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="This job has already been saved") from exc
    return db.scalar(select(Job).options(joinedload(Job.company)).where(Job.id == job.id))


@router.delete("/jobs/{job_id}", status_code=204)
def delete_job(
    job_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    job = owned_or_404(db, Job, job_id, user.id)
    if db.scalar(select(Application.id).where(Application.job_id == job.id).limit(1)) is not None:
        raise HTTPException(status_code=409, detail="Delete this job's application first")
    db.delete(job)
    db.commit()


def application_query(user_id: int):
    return (
        select(Application)
        .options(
            joinedload(Application.job).joinedload(Job.company),
            joinedload(Application.resume_version),
        )
        .where(Application.user_id == user_id)
    )


@router.get("/applications", response_model=list[ApplicationRead])
def list_applications(
    q: str | None = None,
    application_status: ApplicationStatus | None = Query(default=None, alias="status"),
    source: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    archived: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[Application]:
    statement = application_query(user.id)
    statement = statement.where(
        Application.archived_at.is_not(None) if archived else Application.archived_at.is_(None)
    )
    if application_status:
        statement = statement.where(Application.status == application_status.value)
    if source:
        statement = statement.where(Application.job.has(Job.source == source))
    if q:
        pattern = f"%{q.strip()}%"
        statement = statement.where(
            Application.job.has(
                or_(Job.title.ilike(pattern), Job.company.has(Company.name.ilike(pattern)))
            )
        )
    statement = statement.order_by(Application.updated_at.desc()).offset(offset).limit(limit)
    return list(db.scalars(statement))


@router.post("/applications", response_model=ApplicationRead, status_code=201)
def create_application(
    payload: ApplicationCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Application:
    owned_or_404(db, Job, payload.job_id, user.id)
    if payload.resume_version_id is not None:
        owned_or_404(db, ResumeVersion, payload.resume_version_id, user.id)
    applied_at = datetime.now(UTC) if payload.status == ApplicationStatus.APPLIED else None
    application = Application(
        user_id=user.id,
        job_id=payload.job_id,
        resume_version_id=payload.resume_version_id,
        status=payload.status.value,
        notes=payload.notes,
        next_action_at=payload.next_action_at,
        applied_at=applied_at,
        tags=sorted({tag.strip() for tag in payload.tags if tag.strip()}),
        custom_fields=payload.custom_fields,
    )
    db.add(application)
    try:
        db.flush()
        db.add(
            TimelineEvent(
                user_id=user.id,
                application_id=application.id,
                event_type="application_created",
                to_status=application.status,
            )
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="An application already exists for this job"
        ) from exc
    return db.scalar(application_query(user.id).where(Application.id == application.id))


@router.patch("/applications/{application_id}", response_model=ApplicationRead)
def update_application(
    application_id: int,
    payload: ApplicationUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Application:
    application = owned_or_404(db, Application, application_id, user.id)
    changes = payload.model_dump(exclude_unset=True)
    if "resume_version_id" in changes and changes["resume_version_id"] is not None:
        owned_or_404(db, ResumeVersion, changes["resume_version_id"], user.id)
    for field in ("resume_version_id", "notes", "next_action_at", "custom_fields"):
        if field in changes:
            setattr(application, field, changes[field])
    if "tags" in changes and changes["tags"] is not None:
        application.tags = sorted({tag.strip() for tag in changes["tags"] if tag.strip()})
    db.commit()
    return db.scalar(application_query(user.id).where(Application.id == application.id))


@router.delete("/applications/{application_id}", status_code=204)
def delete_application(
    application_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    application = owned_or_404(db, Application, application_id, user.id)
    db.delete(application)
    db.commit()


@router.patch("/applications/{application_id}/archive", response_model=ApplicationRead)
def archive_application(
    application_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Application:
    application = owned_or_404(db, Application, application_id, user.id)
    if application.archived_at is None:
        application.archived_at = datetime.now(UTC)
        db.commit()
    return db.scalar(application_query(user.id).where(Application.id == application.id))


@router.patch("/applications/{application_id}/restore", response_model=ApplicationRead)
def restore_application(
    application_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Application:
    application = owned_or_404(db, Application, application_id, user.id)
    if application.archived_at is not None:
        application.archived_at = None
        db.commit()
    return db.scalar(application_query(user.id).where(Application.id == application.id))


@router.patch("/applications/{application_id}/status", response_model=ApplicationRead)
def update_application_status(
    application_id: int,
    payload: ApplicationStatusUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Application:
    application = owned_or_404(db, Application, application_id, user.id)
    previous = application.status
    if previous != payload.status.value:
        application.status = payload.status.value
        if payload.status == ApplicationStatus.APPLIED and application.applied_at is None:
            application.applied_at = datetime.now(UTC)
        db.add(
            TimelineEvent(
                user_id=user.id,
                application_id=application.id,
                event_type="status_changed",
                from_status=previous,
                to_status=application.status,
            )
        )
        db.commit()
    return db.scalar(application_query(user.id).where(Application.id == application.id))


def set_application_status(
    db: Session, application: Application, target: ApplicationStatus, user_id: int
) -> None:
    previous = application.status
    if previous == target.value:
        return
    application.status = target.value
    if target == ApplicationStatus.APPLIED and application.applied_at is None:
        application.applied_at = datetime.now(UTC)
    db.add(TimelineEvent(user_id=user_id, application_id=application.id,
                         event_type="status_changed", from_status=previous,
                         to_status=target.value))


@router.patch("/application-actions/bulk-status", response_model=list[ApplicationRead])
def bulk_update_status(
    payload: BulkStatusUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[Application]:
    ids = list(dict.fromkeys(payload.application_ids))
    applications = list(db.scalars(select(Application).where(
        Application.user_id == user.id, Application.id.in_(ids))))
    if len(applications) != len(ids):
        raise HTTPException(status_code=404, detail="One or more applications were not found")
    for application in applications:
        set_application_status(db, application, payload.status, user.id)
    db.commit()
    return list(db.scalars(application_query(user.id).where(Application.id.in_(ids))))


@router.post("/applications/{application_id}/undo-status", response_model=ApplicationRead)
def undo_application_status(
    application_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Application:
    application = owned_or_404(db, Application, application_id, user.id)
    event = db.scalar(select(TimelineEvent).where(
        TimelineEvent.user_id == user.id,
        TimelineEvent.application_id == application.id,
        TimelineEvent.event_type == "status_changed",
        TimelineEvent.to_status == application.status,
    ).order_by(TimelineEvent.created_at.desc(), TimelineEvent.id.desc()))
    if event is None or event.from_status is None:
        raise HTTPException(status_code=409, detail="No status change can be undone")
    previous, application.status = application.status, event.from_status
    db.add(TimelineEvent(user_id=user.id, application_id=application.id,
                         event_type="status_undone", from_status=previous,
                         to_status=application.status))
    db.commit()
    return db.scalar(application_query(user.id).where(Application.id == application.id))


@router.post("/applications/{application_id}/merge", response_model=ApplicationRead)
def merge_application(
    application_id: int,
    payload: MergeApplications,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Application:
    target = owned_or_404(db, Application, application_id, user.id)
    source = owned_or_404(db, Application, payload.source_application_id, user.id)
    if source.id == target.id:
        raise HTTPException(status_code=400, detail="Choose two different applications")
    target.notes = "\n\n".join(part for part in (target.notes, source.notes) if part) or None
    target.tags = sorted(set((target.tags or []) + (source.tags or [])))
    target.custom_fields = {**(source.custom_fields or {}), **(target.custom_fields or {})}
    target.next_action_at = target.next_action_at or source.next_action_at
    for interview in list(source.interviews):
        interview.application = target
    source_job = source.job
    db.delete(source)
    db.flush()
    if not db.scalar(select(Application.id).where(Application.job_id == source_job.id).limit(1)):
        db.delete(source_job)
    db.add(TimelineEvent(user_id=user.id, application_id=target.id,
                         event_type="duplicate_merged"))
    db.commit()
    return db.scalar(application_query(user.id).where(Application.id == target.id))


@router.get("/applications/{application_id}/interviews", response_model=list[InterviewRead])
def list_interviews(application_id: int, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)) -> list[InterviewRound]:
    owned_or_404(db, Application, application_id, user.id)
    return list(db.scalars(select(InterviewRound).where(
        InterviewRound.user_id == user.id, InterviewRound.application_id == application_id
    ).order_by(InterviewRound.scheduled_at)))


def ensure_no_interview_conflict(db: Session, user_id: int, scheduled_at: datetime,
                                 duration_minutes: int, exclude_id: int | None = None) -> None:
    start = scheduled_at
    end = start + timedelta(minutes=duration_minutes)
    candidates = db.scalars(select(InterviewRound).where(InterviewRound.user_id == user_id)).all()
    for item in candidates:
        if item.id == exclude_id:
            continue
        if start < item.scheduled_at + timedelta(minutes=item.duration_minutes) and item.scheduled_at < end:
            raise HTTPException(status_code=409, detail=f"Conflicts with interview: {item.round_name}")


@router.post("/applications/{application_id}/interviews", response_model=InterviewRead, status_code=201)
def create_interview(application_id: int, payload: InterviewCreate,
                     db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> InterviewRound:
    application = owned_or_404(db, Application, application_id, user.id)
    ensure_no_interview_conflict(db, user.id, payload.scheduled_at, payload.duration_minutes)
    interview = InterviewRound(user_id=user.id, application_id=application.id,
                               **payload.model_dump())
    db.add(interview)
    if application.status not in {ApplicationStatus.INTERVIEW.value, ApplicationStatus.OFFER.value,
                                  ApplicationStatus.CLOSED.value}:
        set_application_status(db, application, ApplicationStatus.INTERVIEW, user.id)
    db.add(TimelineEvent(user_id=user.id, application_id=application.id,
                         event_type="interview_scheduled"))
    db.commit()
    db.refresh(interview)
    return interview


@router.patch("/interviews/{interview_id}", response_model=InterviewRead)
def update_interview(interview_id: int, payload: InterviewUpdate,
                     db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> InterviewRound:
    interview = owned_or_404(db, InterviewRound, interview_id, user.id)
    changes = payload.model_dump(exclude_unset=True)
    start = changes.get("scheduled_at", interview.scheduled_at)
    duration = changes.get("duration_minutes", interview.duration_minutes)
    ensure_no_interview_conflict(db, user.id, start, duration, interview.id)
    for field, value in changes.items():
        setattr(interview, field, value)
    db.commit()
    db.refresh(interview)
    return interview


@router.delete("/interviews/{interview_id}", status_code=204)
def delete_interview(interview_id: int, db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)) -> None:
    db.delete(owned_or_404(db, InterviewRound, interview_id, user.id))
    db.commit()


KEYWORDS = (
    "python", "java", "javascript", "typescript", "react", "vue", "sql", "docker",
    "kubernetes", "aws", "azure", "gcp", "linux", "git", "fastapi", "django",
    "spring", "node", "redis", "mysql", "postgresql", "算法", "数据结构", "系统设计",
    "微服务", "云计算", "机器学习", "沟通", "英语", "项目管理",
)


@router.get("/applications/{application_id}/match", response_model=MatchResult)
def match_application(application_id: int, db: Session = Depends(get_db),
                      user: User = Depends(get_current_user)) -> MatchResult:
    application = owned_or_404(db, Application, application_id, user.id)
    jd = (application.job.jd_text or "").lower()
    resume = ((application.resume_version.content_text if application.resume_version else "") or "").lower()
    requested = [keyword for keyword in KEYWORDS if keyword in jd]
    matched = [keyword for keyword in requested if keyword in resume]
    missing = [keyword for keyword in requested if keyword not in resume]
    score = round(len(matched) / len(requested) * 100) if requested else 0
    questions = [f"请结合项目说明你使用 {keyword} 解决过什么问题？" for keyword in missing[:5]]
    if not application.job.jd_text:
        recommendation = "请先补充 JD 文本，再生成针对性分析。"
    elif not application.resume_version or not application.resume_version.content_text:
        recommendation = "请在简历版本中粘贴可分析文本；文件仍保留在本地存储。"
    elif score >= 75:
        recommendation = "匹配度较高，重点准备量化成果和项目取舍。"
    elif score >= 45:
        recommendation = "具备部分匹配项，建议在简历中补充缺失技能的真实项目证据。"
    else:
        recommendation = "当前关键词覆盖较低，建议选择更匹配的简历版本或补充相关经历。"
    return MatchResult(score=score, matched_keywords=matched, missing_keywords=missing,
                       questions=questions, recommendation=recommendation)


@router.get("/applications/{application_id}/timeline", response_model=list[TimelineRead])
def get_timeline(
    application_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[TimelineEvent]:
    owned_or_404(db, Application, application_id, user.id)
    statement = (
        select(TimelineEvent)
        .where(TimelineEvent.application_id == application_id, TimelineEvent.user_id == user.id)
        .order_by(TimelineEvent.created_at.desc())
    )
    return list(db.scalars(statement))


@router.get("/dashboard/funnel", response_model=list[FunnelItem])
def get_funnel(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list[FunnelItem]:
    counts = dict(
        db.execute(
            select(Application.status, func.count(Application.id))
            .where(Application.user_id == user.id)
            .group_by(Application.status)
        ).all()
    )
    return [FunnelItem(status=item, count=counts.get(item.value, 0)) for item in ApplicationStatus]


@router.get("/dashboard/insights", response_model=DashboardInsights)
def get_dashboard_insights(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> DashboardInsights:
    applications = list(db.scalars(application_query(user.id)))
    events = list(
        db.scalars(
            select(TimelineEvent)
            .where(TimelineEvent.user_id == user.id)
            .order_by(TimelineEvent.created_at)
        )
    )
    events_by_application: dict[int, list[TimelineEvent]] = defaultdict(list)
    for event in events:
        events_by_application[event.application_id].append(event)

    current_counts: dict[str, int] = defaultdict(int)
    reached: dict[str, set[int]] = defaultdict(set)
    elapsed_days: dict[str, list[float]] = defaultdict(list)
    source_totals: dict[str, dict[str, int]] = defaultdict(
        lambda: {"total": 0, "interviews": 0, "offers": 0}
    )
    resume_totals: dict[str, dict[str, int]] = defaultdict(
        lambda: {"total": 0, "interviews": 0, "offers": 0}
    )
    weekly_totals: dict[str, int] = defaultdict(int)
    offer_durations: list[float] = []
    for application in applications:
        current_counts[application.status] += 1
        reached_for_application: set[str] = set()
        for event in events_by_application[application.id]:
            if event.to_status and event.to_status not in reached_for_application:
                reached[event.to_status].add(application.id)
                reached_for_application.add(event.to_status)
                elapsed = event.created_at - application.created_at
                elapsed_days[event.to_status].append(max(0.0, elapsed.total_seconds() / 86400))
        source = application.job.source or "manual"
        source_totals[source]["total"] += 1
        if ApplicationStatus.INTERVIEW.value in reached_for_application:
            source_totals[source]["interviews"] += 1
        if ApplicationStatus.OFFER.value in reached_for_application:
            source_totals[source]["offers"] += 1
        resume_name = application.resume_version.name if application.resume_version else "未关联简历"
        resume_totals[resume_name]["total"] += 1
        if ApplicationStatus.INTERVIEW.value in reached_for_application:
            resume_totals[resume_name]["interviews"] += 1
        if ApplicationStatus.OFFER.value in reached_for_application:
            resume_totals[resume_name]["offers"] += 1
            offer_events = [
                event
                for event in events_by_application[application.id]
                if event.to_status == ApplicationStatus.OFFER.value
            ]
            if offer_events:
                start = application.applied_at or application.created_at
                offer_durations.append(
                    max(0.0, (offer_events[0].created_at - start).total_seconds() / 86400)
                )
        week_start = application.created_at.date() - timedelta(
            days=application.created_at.weekday()
        )
        weekly_totals[week_start.isoformat()] += 1

    stages = []
    for item in ApplicationStatus:
        durations = elapsed_days[item.value]
        stages.append(
            StageInsight(
                status=item,
                current_count=current_counts[item.value],
                ever_reached=len(reached[item.value]),
                average_days_to_reach=(
                    round(sum(durations) / len(durations), 2) if durations else None
                ),
            )
        )
    sources = [
        SourceInsight(source=source, **values)
        for source, values in sorted(source_totals.items(), key=lambda pair: -pair[1]["total"])
    ]
    resumes = [
        ResumeInsight(resume=resume, **values)
        for resume, values in sorted(resume_totals.items(), key=lambda pair: -pair[1]["total"])
    ]
    weekly_trend = [
        WeeklyTrend(week=week, applications=count)
        for week, count in sorted(weekly_totals.items())[-12:]
    ]
    offer_count = len(reached[ApplicationStatus.OFFER.value])
    total = len(applications)
    return DashboardInsights(
        total_applications=total,
        active_applications=sum(
            1 for application in applications if application.status not in {"offer", "closed"}
        ),
        offer_rate=round(offer_count / total * 100, 2) if total else 0.0,
        average_days_to_offer=(
            round(sum(offer_durations) / len(offer_durations), 2) if offer_durations else None
        ),
        stages=stages,
        sources=sources,
        resumes=resumes,
        weekly_trend=weekly_trend,
    )


def parse_csv_datetime(value: str) -> datetime | None:
    if not value.strip():
        return None
    parsed = datetime.fromisoformat(value.strip())
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


@router.post("/applications-import.csv", response_model=CSVImportResult)
async def import_applications(
    file: Annotated[UploadFile, File()],
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CSVImportResult:
    content = await file.read(1_000_001)
    await file.close()
    if len(content) > 1_000_000:
        raise HTTPException(status_code=413, detail="CSV file must not exceed 1 MB")
    try:
        stream = io.StringIO(content.decode("utf-8-sig"), newline="")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="CSV must use UTF-8 encoding") from exc
    reader = csv.DictReader(stream)
    if not reader.fieldnames or not {"company", "title"}.issubset(reader.fieldnames):
        raise HTTPException(status_code=400, detail="CSV requires company and title columns")

    imported = 0
    skipped = 0
    errors: list[CSVImportError] = []
    for index, row in enumerate(reader, start=2):
        if index > CSV_IMPORT_LIMIT + 1:
            errors.append(CSVImportError(row=index, detail="Only the first 500 rows are accepted"))
            break
        try:
            company_name = (row.get("company") or "").strip()
            title = (row.get("title") or "").strip()
            if not company_name or not title:
                raise ValueError("company and title are required")
            raw_status = (row.get("status") or ApplicationStatus.SAVED.value).strip().lower()
            application_status = ApplicationStatus(raw_status)
            with db.begin_nested():
                company = db.scalar(
                    select(Company).where(
                        Company.user_id == user.id, func.lower(Company.name) == company_name.lower()
                    )
                )
                if company is None:
                    company = Company(user_id=user.id, name=company_name)
                    db.add(company)
                    db.flush()
                job_payload = JobCreate(
                    company_id=company.id,
                    title=title,
                    location=(row.get("location") or "").strip() or None,
                    source=(row.get("source") or "").strip() or None,
                    source_url=(row.get("source_url") or "").strip() or None,
                    jd_text=(row.get("jd_text") or "").strip() or None,
                )
                fingerprint = job_fingerprint(user.id, company.id, job_payload)
                job = db.scalar(
                    select(Job).where(Job.user_id == user.id, Job.fingerprint == fingerprint)
                )
                if job is None:
                    job = Job(user_id=user.id, fingerprint=fingerprint, **job_payload.model_dump())
                    db.add(job)
                    db.flush()
                if db.scalar(
                    select(Application.id).where(
                        Application.user_id == user.id, Application.job_id == job.id
                    )
                ):
                    skipped += 1
                    continue
                resume_name = (row.get("resume_version") or "").strip()
                resume = (
                    db.scalar(
                        select(ResumeVersion).where(
                            ResumeVersion.user_id == user.id,
                            func.lower(ResumeVersion.name) == resume_name.lower(),
                        )
                    )
                    if resume_name
                    else None
                )
                application = Application(
                    user_id=user.id,
                    job_id=job.id,
                    resume_version_id=resume.id if resume else None,
                    status=application_status.value,
                    notes=(row.get("notes") or "").strip() or None,
                    next_action_at=parse_csv_datetime(row.get("next_action_at") or ""),
                    applied_at=(
                        datetime.now(UTC)
                        if application_status != ApplicationStatus.SAVED
                        else None
                    ),
                )
                db.add(application)
                db.flush()
                db.add(
                    TimelineEvent(
                        user_id=user.id,
                        application_id=application.id,
                        event_type="application_imported",
                        to_status=application.status,
                    )
                )
                imported += 1
        except (ValueError, IntegrityError) as exc:
            errors.append(CSVImportError(row=index, detail=str(exc)))
    db.commit()
    return CSVImportResult(imported=imported, skipped=skipped, errors=errors)


@router.get("/applications-export.csv")
def export_applications(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> StreamingResponse:
    applications = list(db.scalars(application_query(user.id).order_by(Application.created_at)))
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "company",
            "title",
            "status",
            "location",
            "source",
            "source_url",
            "resume_version",
            "next_action_at",
            "notes",
            "created_at",
        ]
    )
    for application in applications:
        writer.writerow(
            [
                application.job.company.name,
                application.job.title,
                application.status,
                application.job.location or "",
                application.job.source or "",
                application.job.source_url or "",
                application.resume_version.name if application.resume_version else "",
                application.next_action_at.isoformat() if application.next_action_at else "",
                application.notes or "",
                application.created_at.isoformat(),
            ]
        )
    response = StreamingResponse(iter([output.getvalue()]), media_type="text/csv; charset=utf-8")
    response.headers["Content-Disposition"] = 'attachment; filename="jobflow-applications.csv"'
    return response


@router.get("/applications-export.json")
def export_applications_json(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> StreamingResponse:
    applications = list(db.scalars(application_query(user.id).order_by(Application.created_at)))
    payload = [{
        "company": item.job.company.name,
        "title": item.job.title,
        "status": item.status,
        "location": item.job.location,
        "source": item.job.source,
        "source_url": item.job.source_url,
        "jd_text": item.job.jd_text,
        "resume_version": item.resume_version.name if item.resume_version else None,
        "next_action_at": item.next_action_at.isoformat() if item.next_action_at else None,
        "notes": item.notes,
        "tags": item.tags or [],
        "custom_fields": item.custom_fields or {},
        "created_at": item.created_at.isoformat(),
    } for item in applications]
    response = StreamingResponse(iter([json.dumps(payload, ensure_ascii=False, indent=2)]),
                                 media_type="application/json; charset=utf-8")
    response.headers["Content-Disposition"] = 'attachment; filename="jobflow-applications.json"'
    return response


def ics_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def ics_datetime(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


@router.get("/calendar.ics")
def export_calendar(db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)) -> StreamingResponse:
    applications = list(db.scalars(application_query(user.id)))
    interviews = list(db.scalars(select(InterviewRound).where(InterviewRound.user_id == user.id)))
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//JobFlow//Calendar//ZH-CN",
             "CALSCALE:GREGORIAN", "METHOD:PUBLISH"]
    now = ics_datetime(datetime.now(UTC))
    for item in applications:
        if not item.next_action_at:
            continue
        lines.extend(["BEGIN:VEVENT", f"UID:application-{item.id}@jobflow.local", f"DTSTAMP:{now}",
                      f"DTSTART:{ics_datetime(item.next_action_at)}",
                      f"DTEND:{ics_datetime(item.next_action_at + timedelta(minutes=30))}",
                      f"SUMMARY:{ics_escape('跟进：' + item.job.company.name + ' - ' + item.job.title)}",
                      "BEGIN:VALARM", "TRIGGER:-PT30M", "ACTION:DISPLAY", "DESCRIPTION:JobFlow 跟进提醒",
                      "END:VALARM", "END:VEVENT"])
    for item in interviews:
        application = owned_or_404(db, Application, item.application_id, user.id)
        lines.extend(["BEGIN:VEVENT", f"UID:interview-{item.id}@jobflow.local", f"DTSTAMP:{now}",
                      f"DTSTART:{ics_datetime(item.scheduled_at)}",
                      f"DTEND:{ics_datetime(item.scheduled_at + timedelta(minutes=item.duration_minutes))}",
                      f"SUMMARY:{ics_escape(item.round_name + '：' + application.job.company.name)}",
                      f"LOCATION:{ics_escape(item.location or '')}",
                      f"DESCRIPTION:{ics_escape(item.notes or application.job.title)}",
                      "BEGIN:VALARM", "TRIGGER:-PT1H", "ACTION:DISPLAY", "DESCRIPTION:JobFlow 面试提醒",
                      "END:VALARM", "END:VEVENT"])
    lines.append("END:VCALENDAR")
    response = StreamingResponse(iter(["\r\n".join(lines) + "\r\n"]),
                                 media_type="text/calendar; charset=utf-8")
    response.headers["Content-Disposition"] = 'attachment; filename="jobflow-calendar.ics"'
    return response


@router.post("/sample-data", status_code=201)
def create_sample_data(db: Session = Depends(get_db),
                       user: User = Depends(get_current_user)) -> dict[str, int]:
    if db.scalar(select(Application.id).where(Application.user_id == user.id).limit(1)):
        raise HTTPException(status_code=409, detail="Sample data is only available in an empty workspace")
    company = Company(user_id=user.id, name="示例科技", website="https://example.com")
    resume = ResumeVersion(user_id=user.id, name="产品研发版", content_text="Python SQL Docker React 系统设计 沟通")
    db.add_all([company, resume])
    db.flush()
    job_payload = JobCreate(company_id=company.id, title="后端工程师", location="上海 / 远程",
                            source="示例", source_url="https://example.com/jobs/backend",
                            jd_text="熟悉 Python、SQL、Docker、Kubernetes 与系统设计，具备良好沟通能力")
    job = Job(user_id=user.id, fingerprint=job_fingerprint(user.id, company.id, job_payload),
              **job_payload.model_dump())
    db.add(job)
    db.flush()
    application = Application(user_id=user.id, job_id=job.id, resume_version_id=resume.id,
                              status=ApplicationStatus.INTERVIEW.value, tags=["重点", "远程"],
                              custom_fields={"薪资范围": "25k-35k"},
                              notes="这是一条可安全删除的示例投递。",
                              next_action_at=datetime.now(UTC) + timedelta(days=2))
    db.add(application)
    db.flush()
    db.add(TimelineEvent(user_id=user.id, application_id=application.id,
                         event_type="sample_created", to_status=application.status))
    db.commit()
    return {"application_id": application.id}


@router.get("/notifications", response_model=list[NotificationRead])
def list_notifications(
    unread_only: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[Notification]:
    statement = select(Notification).where(Notification.user_id == user.id)
    if unread_only:
        statement = statement.where(Notification.read_at.is_(None))
    return list(db.scalars(statement.order_by(Notification.created_at.desc()).limit(100)))


@router.patch("/notifications/{notification_id}/read", response_model=NotificationRead)
def mark_notification_read(
    notification_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Notification:
    notification = owned_or_404(db, Notification, notification_id, user.id)
    if notification.read_at is None:
        notification.read_at = datetime.now(UTC)
        db.commit()
        db.refresh(notification)
    return notification
