import os
import logging

from django.utils import timezone
from django.contrib.auth import get_user_model

from ..models import ImportBatch
from ..services.letterboxd_import import run_letterboxd_import
from ..services.rss_sync import sync_user_rss_watches

logger = logging.getLogger(__name__)
User = get_user_model()

def _cleanup_file():
    pass