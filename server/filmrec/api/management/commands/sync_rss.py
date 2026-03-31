from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q
from django.utils import timezone


from django.utils import timezone
from api.models import User

from api.services.rss_sync import sync_user_rss_watches

class Command(BaseCommand):
    help = "Sync Letterboxd RSS watches for users who have letterboxd username"

    def add_arguments(self, parser):
        parser.add_argument("--user-id", type=int, default=None, help="Sync only to this user id")
        parser.add_argument("--limit", type=int, default=200, help="Max users to sync in one run")
        parser.add_argument("--stale-hours", type=int, default=6, help="Only sync users not synced in N hours")
        parser.add_argument("--dry-run", action="store_true", help="Print what would happen without writing")

    def handle(self, *args, **options):
        user_id = options["user_id"]
        limit = int(options["limit"] or 0)
        stale_hours = int(options["stale_hours"] or 0)
        dry_run = bool(options["dry_run"])

        qs = User.objects.filter(letterboxd_username__isnull=False).exclude(letterboxd_username="")

        if user_id is not None:
            qs = qs.filter(id=user_id)

        if stale_hours > 0:
            cutoff = timezone.now() - timezone.timedelta(hours=stale_hours)
            qs = qs.filter(Q(last_sync__isnull=True) | Q(last_sync__lt=cutoff))
        
        qs = qs.order_by("id")
        if limit > 0:
            qs = qs[:limit]

        total = ok = failed = 0
        for user in qs:
            total += 1

            if dry_run:
                self.stdout.write(
                    f"[dry-run] would sync user_id = {user.id} username={user.letterboxd_username}"
                )
                continue

            try:
                with transaction.atomic():
                    res = sync_user_rss_watches(user)
                if res.error:
                    failed += 1
                    self.stdout.write(self.style.WARNING(
                        f"[fail] user_id={res.user_id} url={res.rss_url} error={res.error}"
                        f"movies+{res.movies_created} events+{res.events_created}"
                        f"rel+{res.rel_created} upd+{res.rel_updated} stopped_early={res.stopped_early}"
                    ))
                else:
                    ok += 1
                    self.stdout.write(self.style.SUCCESS(
                        f"[ok] user_id = {res.user_id} entries_seen={res.entries_seen}"
                    ))
            except Exception as e:
                failed += 1
                self.stdout.write(self.style.ERROR(f"[crash] user_id={user.id} error={str(e)}"))
        self.stdout.write(f"done. total={total} ok = {ok} failed={failed} dry_run={dry_run}")