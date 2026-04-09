# api/tasks/taste_tasks.py
from __future__ import annotations
import logging

from celery import shared_task
from django.utils import timezone
from django.conf import settings
from django.core.cache import cache
from django.contrib.auth import get_user_model
from django.core.management import call_command

from api.models import FilmBank

logger = logging.getLogger(__name__)
User = get_user_model()

DEFAULT_TASTE_OUT_DIR = "taste_out"
FEEDBACK_REBUILD_THRESHOLD = 3
TASTE_QUEUE_LOCK_SECONDS = 60 * 10  # 10m
TASTE_RUN_LOCK_SECONDS = 60 * 20    # 20m

# ---------------------------------------------------------------------------
# Feedback-trigger policy
# ---------------------------------------------------------------------------

def is_strong_feedback_signal(*, rating: str | None, watched, text: str) -> bool:
    text = (text or "").strip()
    if text:
        return True
    
    if rating == "good" and watched is True:
        return True
    
    if rating == "bad" and watched is False:
        return True
    
    return False

def pending_feedback_count(user_id: int) -> int:
    """
    Count feedback rows submitted after the last rebuild.
    We use the latest feedback-submitted-at timestamp already recorded
    into the merged summary file indirectly via rebuild timing.
    Simple first version: count all feedback rows that still exist
    """
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return 0
    
    qs =  FilmBank.objects.filter(
        user_id=user_id,
        feedback_submitted_at__isnull=False,
    )

    if user.last_taste_rebuild_at:
        qs = qs.filter(feedback_submitted_at__gt=user.last_taste_rebuild_at)\
        
    return qs.count()

def _taste_out_dir() -> str:
    # Central place to resolve taste artifact output directory
    # override later with settings
    return getattr(settings, "TASTE_OUT_DIR", DEFAULT_TASTE_OUT_DIR)

def _queue_lock_key(user_id: int) -> str:
    return f"taste:queue-lock:user:{user_id}"

def _run_lock_key(user_id: int) -> str:
    return f"taste:run-lock:user:{user_id}"

def _acquire_queue_lock(user_id: int) -> bool:
    return cache.add(_queue_lock_key(user_id), "1", timeout=TASTE_QUEUE_LOCK_SECONDS)

def _release_queue_lock(user_id: int) -> None:
    cache.delete(_run_lock_key(user_id))

def _acquire_run_lock(user_id: int) -> bool:
    return cache.add(_run_lock_key(user_id), "1", timeout=TASTE_RUN_LOCK_SECONDS)

def _release_run_lock(user_id: int) -> None:
    cache.delete(_run_lock_key(user_id))

def _mark_taste_rebuilt(user_id: int) -> None:
    User.objects.filter(id=user_id).update(last_taste_rebuild_at=timezone.now())

def _user_has_source_data(user) -> bool:
    return (
        (getattr(user, "manual_import_count", 0) or 0) > 0
        or (getattr(user, "rss_import_count", 0) or 0) > 0
    )

def _has_built_taste_profile(user) -> bool:
    # DB-backed truth, not filesystem truth
    return bool(
        getattr(user, "last_taste_rebuild_at", None)
        or getattr(user, "taste_vectore_store_id", None)
    )

def should_init_taste_profile(user_id: int):
    # Init only if the user has enough soruce data and has no taste file
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return False
    
    if not _user_has_source_data(user):
        return False

    return not _has_built_taste_profile(user)

def should_rebuild_taste_profile(
        *,
        user_id: int,
        reason: str,
        has_updates: bool,
        out: str | None = None,
) -> bool:
    """
    Rebuild only if:
        - taste file alr exists
        - reason is allowed
        - there were meaningful updates
    """
    try:
        user = User.objects.get(id=user_id)
    except user.DoesNotExist:
        return False
    
    if not _has_built_taste_profile(user):
        return False
    
    if not has_updates:
        return False
    
    allowed_reasons = {"manual", "csv", "rss", "feedback", "admin"}
    return reason in allowed_reasons

@shared_task
def run_init_taste_profile(user_id: int, out: str | None = None) -> None:
    out_dir = out or _taste_out_dir()

    if not _acquire_run_lock(user_id):
        logger.info("INIT_TASTE_PROFILE skip user=%s reason=run_lock_exists", user_id)
        return
    
    try:
        logger.info("INIT_TASTE_PROFILE start user=%s out=%s", user_id, out_dir)
        
        call_command(
            "init_taste_profile",
            user_id=user_id,
            out=out_dir,
        )
        
        _mark_taste_rebuilt(user_id)
        
        logger.info("INIT_TASTE_PROFILE success user=%s out=%s", user_id, out_dir)
    finally:
        _release_run_lock(user_id)
        _release_queue_lock(user_id)

@shared_task
def run_rebuild_taste_profile(
    user_id: int,
    reason: str = "manual",
    out: str | None = None,
) -> None:
    out_dir = out or _taste_out_dir()
    if not _acquire_run_lock(user_id):
        logger.info(
            "REBUILD_TASTE_PROFILE skip user=%s reason=%s cause=run_lock_exists",
            user_id,
            reason,
        )  
        return
    try:
        logger.info(
            "REBUILD_TASTE_PROFILE start user=%s reason=%s out=%s",
            user_id,
            reason,
            out_dir,
        )

        # rebuild the user taste summary
        call_command("rebuild_taste_profile", user_id=user_id, out=out_dir, reason=reason,)

        _mark_taste_rebuilt(user_id)
        logger.info(
            "REBUILD_TASTE_PROFILE success user=%s reason=%s out=%s",
            user_id,
            reason,
            out_dir,
        )
    finally:
        _release_run_lock(user_id)
        _release_queue_lock(user_id)

def enqueue_taste_profile_refresh(
        *,
        user_id: int,
        reason: str,
        has_updates: bool,
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

    if not _acquire_queue_lock(user_id):
        logger.info(
            "TASTE_PROFILE noop init user=%s reason=%s cause=queue_lock_exists",
            user_id,
            reason,
        )
        return "noop"
    
    if should_init_taste_profile(user_id=user_id):
        run_init_taste_profile.delay(user_id=user_id, out=out_dir)
        logger.info(
            "TASTE_PROFILE queued init user=%s reason=%s out=%s",
            user_id,
            reason,
            out_dir,
        )
        return "init"
    
    # redundancy check if there is no user taste summary
    # if no user taste summary -> build initial basic taste summary
    if should_rebuild_taste_profile(user_id=user_id, reason=reason, has_updates=has_updates, out=out_dir):
        run_rebuild_taste_profile.delay(user_id=user_id, reason=reason, out=out_dir)
        logger.info(
            "TASTE_PROFILE queued init user=%s reason=%s out=%s",
            user_id,
            reason,
            out_dir,
        )
        return "rebuild"
    
    _release_queue_lock(user_id)
    logger.info(
        "TASTE_PROFILE noop user=%s reason=%s out=%s",
        user_id,
        reason,
        out_dir,
    )
    return "noop"
    
def enqueue_feedback_taste_refresh(
        *,
        user_id: int,
        rating: str | None,
        watched,
        text: str,
        out: str | None = None,
) -> str:
    """
    Walkthrough:
        - init if no taste profile exists yet
        - immediate rebuild for strong feedback
        - rebuild if feedback count reaches threshold
        - otherwise defer
    """
    out_dir = out or _taste_out_dir()
    
    if not _acquire_queue_lock(user_id):
        logger.info(
            "FEEDBACK_TASTE noop user=%s cause=queue_lock_exists", user_id,)
        return "noop"
    
    if should_init_taste_profile(user_id=user_id):
        run_init_taste_profile.delay(user_id=user_id, out=out_dir)
        logger.info(
            "FEEDBACK_TASTE queued init user=%s out=%s", user_id, out_dir,)
        return "init"
    
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExists:
        _release_queue_lock(user_id)
        return "noop"
    
    if not _has_built_taste_profile(user):
        _release_queue_lock(user_id)
        logger.info(
            "FEEDBACK_TASTE noop user=%s reason=no_built_profile",
            user_id,
        )
        return "noop"
    
    if is_strong_feedback_signal(rating=rating, watched=watched, text=text):
        run_rebuild_taste_profile.delay(
            user_id=user_id,
            reason="feedback",
            out=out_dir,
        )
        logger.info(
            "FEEDBACK_TASTE queued rebuild user=%s reason=strong_signal out=%s",
            user_id,
            out_dir,
        )
        return "rebuild"
    
    count = pending_feedback_count(user_id=user_id)
    if count >= FEEDBACK_REBUILD_THRESHOLD:
        run_rebuild_taste_profile.delay(
            user_id=user_id,
            reason="feedback",
            out=out_dir,
        )
        logger.info(
            "FEEDBACK_TASTE queued rebuild user=%s reason=threshold count=%s out=%s",
            user_id,
            count,
            out_dir,
        )
        return "rebuild"
    
    _release_queue_lock(user_id)
    logger.info(
        "FEEDBACK_TASTE deffered user=%s count=%s out=%s",
        user_id,
        count,
        out_dir,
    )
    return "defer"