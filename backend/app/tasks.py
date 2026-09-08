from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from .celery_app import celery_app
from .database import SessionLocal
from .models import Application, ApplicationStatus, Notification, User


def create_due_notifications(now: datetime | None = None) -> int:
    current = now or datetime.now(UTC)
    horizon = current + timedelta(hours=24)
    created = 0
    with SessionLocal() as db:
        applications = db.scalars(
            select(Application)
            .options(joinedload(Application.job))
            .where(
                Application.next_action_at.is_not(None),
                Application.next_action_at <= horizon,
                Application.status.not_in(
                    [ApplicationStatus.OFFER.value, ApplicationStatus.CLOSED.value]
                ),
            )
        ).all()
        for application in applications:
            scheduled = application.next_action_at
            if scheduled is None:
                continue
            dedupe_key = f"next-action:{application.id}:{scheduled.isoformat()}"
            notification = Notification(
                user_id=application.user_id,
                application_id=application.id,
                kind="next_action_due",
                title=f"{application.job.title} 待跟进",
                body="下一步安排将在 24 小时内到期"
                if scheduled > current
                else "下一步安排已经到期",
                scheduled_for=scheduled,
                delivered_at=current,
                dedupe_key=dedupe_key,
            )
            db.add(notification)
            try:
                db.commit()
                created += 1
            except IntegrityError:
                db.rollback()
    return created


def create_stale_notifications(now: datetime | None = None, stale_days: int = 14) -> int:
    current = now or datetime.now(UTC)
    cutoff = current - timedelta(days=stale_days)
    created = 0
    with SessionLocal() as db:
        applications = db.scalars(
            select(Application)
            .options(joinedload(Application.job))
            .where(
                Application.archived_at.is_(None),
                Application.updated_at <= cutoff,
                Application.status.in_(
                    [
                        ApplicationStatus.APPLIED.value,
                        ApplicationStatus.ASSESSMENT.value,
                        ApplicationStatus.INTERVIEW.value,
                    ]
                ),
            )
        ).all()
        for application in applications:
            dedupe_key = f"stale:{application.id}:{application.updated_at.date().isoformat()}"
            db.add(
                Notification(
                    user_id=application.user_id,
                    application_id=application.id,
                    kind="no_feedback",
                    title=f"{application.job.title} 暂无反馈",
                    body=f"这条投递已超过 {stale_days} 天没有更新，可以考虑跟进",
                    scheduled_for=current,
                    delivered_at=current,
                    dedupe_key=dedupe_key,
                )
            )
            try:
                db.commit()
                created += 1
            except IntegrityError:
                db.rollback()
    return created


def create_weekly_reports(now: datetime | None = None) -> int:
    current = now or datetime.now(UTC)
    start = current - timedelta(days=7)
    week = current.date().isocalendar()
    created = 0
    with SessionLocal() as db:
        for user_id in db.scalars(select(User.id)):
            applications = db.scalars(
                select(Application).where(
                    Application.user_id == user_id,
                    Application.created_at >= start,
                )
            ).all()
            active = sum(
                item.status not in {ApplicationStatus.OFFER.value, ApplicationStatus.CLOSED.value}
                for item in applications
            )
            dedupe_key = f"weekly:{user_id}:{week.year}-W{week.week:02d}"
            db.add(
                Notification(
                    user_id=user_id,
                    kind="weekly_report",
                    title="本周求职报告",
                    body=f"过去 7 天新增 {len(applications)} 条投递，其中 {active} 条仍在推进",
                    scheduled_for=current,
                    delivered_at=current,
                    dedupe_key=dedupe_key,
                )
            )
            try:
                db.commit()
                created += 1
            except IntegrityError:
                db.rollback()
    return created


@celery_app.task(
    name="app.tasks.scan_due_reminders",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def scan_due_reminders() -> int:
    return create_due_notifications()


@celery_app.task(
    name="app.tasks.scan_stale_applications",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def scan_stale_applications() -> int:
    return create_stale_notifications()


@celery_app.task(
    name="app.tasks.generate_weekly_reports",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def generate_weekly_reports() -> int:
    return create_weekly_reports()
