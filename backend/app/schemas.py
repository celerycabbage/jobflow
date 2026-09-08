from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from .models import ApplicationStatus


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class CompanyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    website: str | None = Field(default=None, max_length=500)


class CompanyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    website: str | None = Field(default=None, max_length=500)


class CompanyRead(ORMModel):
    id: int
    name: str
    website: str | None


class ResumeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    file_name: str | None = Field(default=None, max_length=255)
    content_text: str | None = None


class ResumeUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    content_text: str | None = None


class ResumeRead(ORMModel):
    id: int
    name: str
    file_name: str | None
    has_file: bool
    content_text: str | None
    created_at: datetime


class JobCreate(BaseModel):
    company_id: int
    title: str = Field(min_length=1, max_length=200)
    location: str | None = Field(default=None, max_length=160)
    source: str | None = Field(default=None, max_length=80)
    source_url: str | None = Field(default=None, max_length=1000)
    jd_text: str | None = None


class JobUpdate(BaseModel):
    company_id: int | None = None
    title: str | None = Field(default=None, min_length=1, max_length=200)
    location: str | None = Field(default=None, max_length=160)
    source: str | None = Field(default=None, max_length=80)
    source_url: str | None = Field(default=None, max_length=1000)
    jd_text: str | None = None


class JobRead(ORMModel):
    id: int
    company_id: int
    title: str
    location: str | None
    source: str | None
    source_url: str | None
    jd_text: str | None
    created_at: datetime
    company: CompanyRead


class ApplicationCreate(BaseModel):
    job_id: int
    resume_version_id: int | None = None
    status: ApplicationStatus = ApplicationStatus.SAVED
    notes: str | None = None
    next_action_at: datetime | None = None
    tags: list[str] = Field(default_factory=list, max_length=20)
    custom_fields: dict[str, str] = Field(default_factory=dict)


class ApplicationStatusUpdate(BaseModel):
    status: ApplicationStatus


class ApplicationUpdate(BaseModel):
    resume_version_id: int | None = None
    notes: str | None = None
    next_action_at: datetime | None = None
    tags: list[str] | None = Field(default=None, max_length=20)
    custom_fields: dict[str, str] | None = None


class ApplicationRead(ORMModel):
    id: int
    job_id: int
    resume_version_id: int | None
    status: ApplicationStatus
    notes: str | None
    applied_at: datetime | None
    next_action_at: datetime | None
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None
    tags: list[str]
    custom_fields: dict[str, str]
    job: JobRead
    resume_version: ResumeRead | None


class FunnelItem(BaseModel):
    status: ApplicationStatus
    count: int


class TimelineRead(ORMModel):
    id: int
    event_type: str
    from_status: str | None
    to_status: str | None
    created_at: datetime


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


class NotificationRead(ORMModel):
    id: int
    application_id: int | None
    kind: str
    title: str
    body: str
    scheduled_for: datetime
    delivered_at: datetime | None
    read_at: datetime | None
    created_at: datetime


class SourceInsight(BaseModel):
    source: str
    total: int
    interviews: int
    offers: int


class ResumeInsight(BaseModel):
    resume: str
    total: int
    interviews: int
    offers: int


class WeeklyTrend(BaseModel):
    week: str
    applications: int


class StageInsight(BaseModel):
    status: ApplicationStatus
    current_count: int
    ever_reached: int
    average_days_to_reach: float | None


class DashboardInsights(BaseModel):
    total_applications: int
    active_applications: int
    offer_rate: float
    average_days_to_offer: float | None
    stages: list[StageInsight]
    sources: list[SourceInsight]
    resumes: list[ResumeInsight]
    weekly_trend: list[WeeklyTrend]


class CSVImportError(BaseModel):
    row: int
    detail: str


class CSVImportResult(BaseModel):
    imported: int
    skipped: int
    errors: list[CSVImportError]


class InterviewCreate(BaseModel):
    round_name: str = Field(min_length=1, max_length=120)
    interview_type: str = Field(default="video", max_length=40)
    scheduled_at: datetime
    duration_minutes: int = Field(default=60, ge=15, le=480)
    location: str | None = Field(default=None, max_length=500)
    interviewer: str | None = Field(default=None, max_length=160)
    notes: str | None = None


class InterviewUpdate(BaseModel):
    round_name: str | None = Field(default=None, min_length=1, max_length=120)
    interview_type: str | None = Field(default=None, max_length=40)
    scheduled_at: datetime | None = None
    duration_minutes: int | None = Field(default=None, ge=15, le=480)
    location: str | None = Field(default=None, max_length=500)
    interviewer: str | None = Field(default=None, max_length=160)
    notes: str | None = None
    outcome: str | None = Field(default=None, max_length=40)


class InterviewRead(ORMModel):
    id: int
    application_id: int
    round_name: str
    interview_type: str
    scheduled_at: datetime
    duration_minutes: int
    location: str | None
    interviewer: str | None
    notes: str | None
    outcome: str | None
    created_at: datetime
    updated_at: datetime


class BulkStatusUpdate(BaseModel):
    application_ids: list[int] = Field(min_length=1, max_length=100)
    status: ApplicationStatus


class MergeApplications(BaseModel):
    source_application_id: int


class MatchResult(BaseModel):
    score: int
    matched_keywords: list[str]
    missing_keywords: list[str]
    questions: list[str]
    recommendation: str
