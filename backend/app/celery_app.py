from celery import Celery
from celery.schedules import crontab
from celery.signals import task_failure
from sqlalchemy.exc import SQLAlchemyError

from .config import get_settings

settings = get_settings()
celery_app = Celery("jobflow", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    broker_connection_retry_on_startup=True,
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "scan-due-reminders": {
            "task": "app.tasks.scan_due_reminders",
            "schedule": 300.0,
        },
        "scan-stale-applications": {
            "task": "app.tasks.scan_stale_applications",
            "schedule": crontab(hour=1, minute=15),
        },
        "generate-weekly-reports": {
            "task": "app.tasks.generate_weekly_reports",
            "schedule": crontab(hour=1, minute=30, day_of_week="monday"),
        }
    },
)
celery_app.autodiscover_tasks(["app"])


@task_failure.connect
def record_task_failure(task_id=None, exception=None, traceback=None, sender=None, **kwargs):
    """Persist exhausted task errors so operations can inspect and replay them."""
    from .database import SessionLocal
    from .models import TaskFailure

    try:
        with SessionLocal() as db:
            db.add(
                TaskFailure(
                    task_id=task_id,
                    task_name=getattr(sender, "name", "unknown"),
                    error=str(exception),
                    traceback=str(traceback) if traceback else None,
                )
            )
            db.commit()
    except SQLAlchemyError:
        # Celery's own error log remains the final fallback when the database is unavailable.
        return
