
"""Create a compressed PostgreSQL custom-format database backup."""

import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connections


class Command(BaseCommand):
    help = "Create a timestamped PostgreSQL database backup."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output-dir",
            help="Backup directory (defaults to HMS_BACKUP_DIR or ../hms-backups).",
        )

    def handle(self, *args, **options):
        database = connections["default"]
        config = database.settings_dict

        if config["ENGINE"] != "django.db.backends.postgresql":
            raise CommandError("Database backups require PostgreSQL.")

        configured_dir = (
            options.get("output_dir")
            or os.environ.get("HMS_BACKUP_DIR")
            or str(settings.BASE_DIR.parent / "hms-backups")
        )
        output_dir = Path(configured_dir).expanduser().resolve()

        pg_dump = os.environ.get("PG_DUMP_PATH") or shutil.which("pg_dump")
        if not pg_dump:
            candidate = Path(r"E:\PostgreSQL\16\bin\pg_dump.exe")
            if candidate.is_file():
                pg_dump = str(candidate)

        if not pg_dump or not Path(pg_dump).is_file():
            raise CommandError(
                "pg_dump was not found. Set PG_DUMP_PATH to its full path."
            )

        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        destination = output_dir / f"hms-{timestamp}.dump"
        temporary = output_dir / f".hms-{timestamp}.dump.tmp"

        env = os.environ.copy()
        env["PGPASSWORD"] = config.get("PASSWORD", "")
        env["PGCONNECT_TIMEOUT"] = "10"

        command = [
            pg_dump,
            "--format=custom",
            "--no-password",
            "--host", str(config.get("HOST") or "localhost"),
            "--port", str(config.get("PORT") or "5432"),
            "--username", str(config.get("USER") or ""),
            "--dbname", str(config["NAME"]),
            "--file", str(temporary),
        ]

        try:
            result = subprocess.run(
                command,
                env=env,
                capture_output=True,
                text=True,
                timeout=3600,
                check=False,
            )
            if result.returncode != 0:
                raise CommandError(
                    "pg_dump failed. Check database connectivity and backup "
                    "permissions. Details: "
                    + (result.stderr.strip() or "No error details returned.")
                )

            if not temporary.is_file() or temporary.stat().st_size == 0:
                raise CommandError("pg_dump produced an empty backup.")

            pg_restore = os.environ.get("PG_RESTORE_PATH") or shutil.which("pg_restore")
            if not pg_restore:
                candidate = Path(r"E:\PostgreSQL\16\bin\pg_restore.exe")
                if candidate.is_file():
                    pg_restore = str(candidate)

            if not pg_restore or not Path(pg_restore).is_file():
                raise CommandError(
                    "pg_restore was not found; backup verification cannot run."
                )

            verification = subprocess.run(
                [pg_restore, "--list", str(temporary)],
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            if verification.returncode != 0:
                raise CommandError(
                    "Backup verification failed: "
                    + (verification.stderr.strip() or "Invalid backup archive.")
                )

            temporary.replace(destination)
            self.stdout.write(self.style.SUCCESS(
                f"Backup created and archive verified: {destination} "
                f"({destination.stat().st_size} bytes)"
            ))
        except subprocess.TimeoutExpired as exc:
            raise CommandError("PostgreSQL backup or verification timed out.") from exc
        finally:
            if temporary.exists():
                temporary.unlink()
