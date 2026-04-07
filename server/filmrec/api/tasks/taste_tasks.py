# api/tasks/taste_tasks.py
from __future__ import annotations
import logging
from pathlib import Path

from celery import shared_task
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command

from api.services.taste_store import taste_file_exists

logger = logging.getLogger(__name__)
User = get_user_model()

DEFAULT_TASTE_OUT_DIR = "taste_out"

def _taste_out_dir() -> str:
    # Central place to resolve taste artifact output directory
    # override later with settings
    return getattr(settings, "TASTE_OUT_DIR", DEFAULT_TASTE_OUT_DIR)

def should_init_taste_profile(user_id: int, out: str | None = None):
    # Init only if the user has enough soruce data and has no taste file
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return False
    
    has_source_data = (
        (getattr(user, "manual_import_count", 0) or 0) > 0
        or (getattr(user, "rss_import_count", 0) or 0) > 0
    )

    if not has_source_data:
        return False
    return not taste_file_exists(user_id=user_id, out=out or _taste_out_dir())

def should_rebuild_taste_profile(
        *,
        user_id: int,
        reason: str,
        out: str | None = None,
) -> bool:
    """
    Simple first-pass policy:
        - if no file exists yet, init should handle it
        - otherwise rebuild on csv/rss/feedback/manual
    """
    if not taste_file_exists(user_id=user_id, out=out or _taste_out_dir()):
        return False
    
    allowed_reasons = {"manual", "csv", "rss", "feedback", "admin"}
    return reason in allowed_reasons

@shared_task
def run_init_taste_profile(user_id: int, out: str | None = None) -> None:
    out_dir = out or _taste_out_dir()
    logger.info("INIT_TASTE_PROFILE start user=%s out=%s", user_id, out)

    call_command(
        "init_taste_profile",
        user_id=user_id,
        out=out_dir,
    )

    logger.info("INIT_TASTE_PROFILE success user=%s out=%s", user_id, out)

@shared_task
def run_rebuild_taste_profile(
    user_id: int,
    reason: str = "manual",
    out: str | None = None,
) -> None:
    out_dir = out or _taste_out_dir()
    logger.info(
        "REBUILD_TASTE_PROFILE start user=%s reason=%s out=%s",
        user_id,
        reason,
        out_dir,
    )

    call_command(
        "rebuild_taste_profile",
        user_id=user_id,
        out=out_dir,
        reason=reason,
    )

    logger.info(
        "REBUILD_TASTE_PROFILE success user=%s reason=%s out=%s",
        user_id,
        reason,
        out_dir,
    )

def enqueue_taste_profile_refresh(
        *,
        user_id: int,
        reason: str,
        out: str | None = None,
) -> str:
    """
    Main orchestration entry point for app code.
    returns one of:
        - init
        - rebuild
        - noop
    """
    out_dir = out or _taste_out_dir()

    if should_init_taste_profile(user_id=user_id, out=out_dir):
        run_init_taste_profile.delay(user_id=user_id, out=out_dir)
        logger.info(
            "TASTE_PROFILE queued init user=%s reason=%s out=%s",
            user_id,
            reason,
            out_dir,
        )
        return "init"
    
    if should_rebuild_taste_profile(user_id=user_id, out=out_dir):
        run_init_taste_profile.delay(user_id=user_id, out=out_dir)
        logger.info(
            "TASTE_PROFILE queued init user=%s reason=%s out=%s",
            user_id,
            reason,
            out_dir,
        )
        return "rebuild"
    
    logger.info(
        "TASTE_PROFILE noop user=%s reason=%s out=%s",
        user_id,
        reason,
        out_dir,
    )
    return "noop"
    

