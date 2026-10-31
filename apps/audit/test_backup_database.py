
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase


class BackupDatabaseCommandTests(SimpleTestCase):
    def test_rejects_non_postgresql_database(self):
        with patch(
            "apps.audit.management.commands.backup_database.connections"
        ) as connections:
            connections.__getitem__.return_value.settings_dict = {
                "ENGINE": "django.db.backends.sqlite3",
            }
            with self.assertRaisesMessage(CommandError, "require PostgreSQL"):
                call_command("backup_database")

    def test_reports_missing_pg_dump(self):
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch(
                    "apps.audit.management.commands.backup_database.connections"
                ) as connections,
                patch(
                    "apps.audit.management.commands.backup_database.shutil.which",
                    return_value=None,
                ),
                patch(
                    "apps.audit.management.commands.backup_database.Path.is_file",
                    return_value=False,
                ),
            ):
                connections.__getitem__.return_value.settings_dict = {
                    "ENGINE": "django.db.backends.postgresql",
                }
                with self.assertRaisesMessage(CommandError, "pg_dump was not found"):
                    call_command("backup_database", output_dir=directory)

    def test_failed_dump_does_not_publish_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            fake_dump = Path(directory) / "pg_dump.exe"
            fake_dump.touch()

            with (
                patch(
                    "apps.audit.management.commands.backup_database.connections"
                ) as connections,
                patch(
                    "apps.audit.management.commands.backup_database.shutil.which",
                    return_value=str(fake_dump),
                ),
                patch(
                    "apps.audit.management.commands.backup_database.subprocess.run"
                ) as run,
            ):
                connections.__getitem__.return_value.settings_dict = {
                    "ENGINE": "django.db.backends.postgresql",
                    "NAME": "hms",
                    "USER": "hms",
                    "PASSWORD": "test-password",
                    "HOST": "localhost",
                    "PORT": "5432",
                }
                run.return_value.returncode = 1
                run.return_value.stderr = "simulated failure"

                with self.assertRaisesMessage(CommandError, "simulated failure"):
                    call_command("backup_database", output_dir=directory)

            self.assertEqual(list(Path(directory).glob("hms-*.dump")), [])
            self.assertEqual(list(Path(directory).glob("*.tmp")), [])
