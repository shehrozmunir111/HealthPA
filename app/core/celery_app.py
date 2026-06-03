"""
Celery Configuration for Background Tasks
"""

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "healthpa",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "app.services.ocr_service",
        "app.services.ai_engine",
        "app.tasks.email",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,  # 30 minutes
    worker_prefetch_multiplier=1,
    # Celery Beat — periodic tasks
    beat_schedule={
        "send-appointment-reminders": {
            "task": "app.tasks.email.send_appointment_reminders",
            # Runs at the top of every hour
            "schedule": crontab(minute=0),
        },
    },
)