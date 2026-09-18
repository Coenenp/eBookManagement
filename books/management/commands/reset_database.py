"""
Management command to safely drop and rebuild the MySQL/MariaDB database.

This command is the foundation for repeatable local development and clean
migration hygiene. It reads database credentials from Django settings and:

1. Backs up the current database with ``mysqldump`` (unless ``--skip-backup``).
2. Drops and recreates the database using the utf8mb4 charset.
3. Removes existing ``books`` migration files (keeping ``__init__.py``).
4. Runs ``makemigrations books`` to regenerate migrations from the current models.
5. Runs ``migrate`` to apply all migrations.
6. Optionally creates a superuser.

The database is not dropped without confirmation unless ``--noinput`` is passed.
If the configured database user cannot drop/create the database, the command
retries with the ``DB_ADMIN_*`` credentials from settings.
"""

import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

MYSQL_ENGINE = "django.db.backends.mysql"
DEFAULT_COLLATION = "utf8mb4_unicode_ci"

try:
    import MySQLdb
except ImportError:  # pragma: no cover - exercised on hosts without mysqlclient
    MySQLdb = None


class Command(BaseCommand):
    help = "Back up, drop, and rebuild the MySQL/MariaDB database from the current models"

    def add_arguments(self, parser):
        parser.add_argument(
            "--noinput",
            "--no-input",
            action="store_true",
            dest="noinput",
            help="Skip the confirmation prompt before dropping the database",
        )
        parser.add_argument(
            "--skip-backup",
            action="store_true",
            dest="skip_backup",
            help="Skip the mysqldump backup before dropping the database",
        )
        parser.add_argument(
            "--superuser",
            action="store_true",
            dest="create_superuser",
            help="Create a superuser after migrating",
        )
        parser.add_argument(
            "--superuser-username",
            type=str,
            default=None,
            help="Superuser username (overrides DJANGO_SUPERUSER_USERNAME)",
        )
        parser.add_argument(
            "--superuser-email",
            type=str,
            default=None,
            help="Superuser email (overrides DJANGO_SUPERUSER_EMAIL)",
        )
        parser.add_argument(
            "--superuser-password",
            type=str,
            default=None,
            help="Superuser password (overrides DJANGO_SUPERUSER_PASSWORD)",
        )

    def handle(self, *args, **options):
        database = settings.DATABASES["default"]
        engine = database.get("ENGINE", "")

        if engine != MYSQL_ENGINE:
            raise CommandError(
                f"reset_database only supports the MySQL/MariaDB engine (current engine: {engine}). "
                "Set USE_SQLITE_TEMPORARILY=false and configure the DB_* environment variables first."
            )

        name = database.get("NAME")
        if not name:
            raise CommandError("settings.DATABASES['default']['NAME'] is empty.")

        user = database.get("USER", "")
        password = database.get("PASSWORD", "")
        host = database.get("HOST", "localhost")
        port = int(database.get("PORT") or 3306)
        charset = database.get("OPTIONS", {}).get("charset", "utf8mb4")

        if not options.get("noinput") and not self._confirm_drop(name):
            self.stdout.write(self.style.WARNING("Aborted. The database was not changed."))
            return

        if not options.get("skip_backup"):
            self._backup_database(name, user, password, host, port)

        self._drop_and_create_database(name, user, password, host, port, charset)

        self.stdout.write(self.style.NOTICE("Removing existing migrations for the books app..."))
        self._delete_migrations()

        self.stdout.write(self.style.NOTICE("Generating migrations for the books app..."))
        call_command("makemigrations", "books", interactive=False, stdout=self.stdout, stderr=self.stderr)

        self.stdout.write(self.style.NOTICE("Applying migrations..."))
        call_command("migrate", interactive=False, stdout=self.stdout, stderr=self.stderr)

        if options.get("create_superuser"):
            self._create_superuser(options)

        self.stdout.write(self.style.SUCCESS("Database reset complete."))

    def _delete_migrations(self):
        """Delete generated migration files for the books app (keeping __init__.py)."""
        migrations_dir = Path(settings.BASE_DIR) / "books" / "migrations"
        if not migrations_dir.is_dir():
            self.stdout.write(self.style.NOTICE("No migrations directory found; nothing to remove."))
            return

        removed = []
        for path in sorted(migrations_dir.iterdir()):
            if path.is_file() and path.suffix == ".py" and path.name != "__init__.py":
                path.unlink()
                removed.append(path.name)
            elif path.is_dir() and path.name == "__pycache__":
                shutil.rmtree(path, ignore_errors=True)

        if removed:
            self.stdout.write(self.style.WARNING(f"Removed migration files: {', '.join(removed)}"))
        else:
            self.stdout.write(self.style.NOTICE("No migration files to remove."))

    def _confirm_drop(self, name):
        self.stdout.write(self.style.WARNING(f"\nYou are about to DROP database '{name}' and all of its data.\n" "This action cannot be undone.\n"))
        try:
            answer = input("Type 'yes' to continue: ")
        except EOFError:
            return False
        return answer.strip().lower() == "yes"

    def _credential_candidates(self, user, password, host, port):
        candidates = [(user, password, host, port)]
        admin_user = getattr(settings, "DB_ADMIN_USER", None)
        if admin_user:
            admin_password = getattr(settings, "DB_ADMIN_PASSWORD", None) or ""
            admin_host = getattr(settings, "DB_ADMIN_HOST", None) or host
            admin_port = int(getattr(settings, "DB_ADMIN_PORT", None) or port)
            candidates.append((admin_user, admin_password, admin_host, admin_port))
        return candidates

    def _backup_database(self, name, user, password, host, port):
        mysqldump = os.getenv("MYSQLDUMP_PATH") or shutil.which("mysqldump")
        if not mysqldump:
            raise CommandError("mysqldump was not found on PATH and MYSQLDUMP_PATH is not set. " "Set MYSQLDUMP_PATH or pass --skip-backup to skip the pre-drop backup.")

        backup_dir = Path(getattr(settings, "DB_BACKUP_DIR", "backups"))
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_path = backup_dir / f"{name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sql"

        self.stdout.write(self.style.NOTICE(f"Backing up database '{name}' to '{backup_path}'..."))

        last_error = None
        for candidate_user, candidate_password, candidate_host, candidate_port in self._credential_candidates(user, password, host, port):
            env = os.environ.copy()
            env["MYSQL_PWD"] = candidate_password or ""
            try:
                with open(backup_path, "wb") as dump_file:
                    result = subprocess.run(
                        [
                            mysqldump,
                            f"--host={candidate_host}",
                            f"--port={candidate_port}",
                            f"--user={candidate_user}",
                            "--single-transaction",
                            name,
                        ],
                        stdout=dump_file,
                        stderr=subprocess.PIPE,
                        env=env,
                    )
                if result.returncode == 0:
                    self.stdout.write(self.style.SUCCESS(f"Backup written to '{backup_path}'."))
                    return
                last_error = result.stderr.decode(errors="replace").strip() if result.stderr else f"exit code {result.returncode}"
                self.stdout.write(self.style.WARNING(f"Backup failed with user '{candidate_user}'. Error: {last_error}"))
            except OSError as exc:
                last_error = str(exc)
                self.stdout.write(self.style.WARNING(f"Backup failed with user '{candidate_user}'. Error: {exc}"))

        backup_path.unlink(missing_ok=True)
        raise CommandError(f"Database backup failed for '{name}'. Original error: {last_error}")

    def _drop_and_create_database(self, name, user, password, host, port, charset):
        if MySQLdb is None:
            raise CommandError("mysqlclient is required for reset_database. Install it with: pip install mysqlclient")

        quoted_name = self._quote_identifier(name)
        self.stdout.write(self.style.WARNING(f"Dropping and recreating database '{name}'..."))

        last_error = None
        for candidate_user, candidate_password, candidate_host, candidate_port in self._credential_candidates(user, password, host, port):
            connection = None
            try:
                connection = MySQLdb.connect(
                    host=candidate_host,
                    user=candidate_user,
                    password=candidate_password,
                    port=candidate_port,
                    charset=charset,
                )
                cursor = connection.cursor()
                try:
                    cursor.execute(f"DROP DATABASE IF EXISTS {quoted_name}")
                    cursor.execute(f"CREATE DATABASE {quoted_name} CHARACTER SET {charset} COLLATE {DEFAULT_COLLATION}")
                finally:
                    cursor.close()
                self.stdout.write(self.style.SUCCESS(f"Database '{name}' recreated."))
                return
            except MySQLdb.Error as exc:
                last_error = exc
                self.stdout.write(self.style.WARNING(f"Database rebuild failed with user '{candidate_user}'. Error: {exc}"))
            finally:
                if connection is not None:
                    connection.close()

        raise CommandError(
            f"Failed to drop or recreate database '{name}'. "
            "Ensure the configured MySQL user has DROP and CREATE privileges for the database "
            "or provide DB_ADMIN_* credentials. "
            f"Original error: {last_error}"
        ) from last_error

    def _create_superuser(self, options):
        username = options.get("superuser_username") or os.getenv("DJANGO_SUPERUSER_USERNAME")
        email = options.get("superuser_email") or os.getenv("DJANGO_SUPERUSER_EMAIL")
        password = options.get("superuser_password") or os.getenv("DJANGO_SUPERUSER_PASSWORD")

        self.stdout.write(self.style.NOTICE("Creating superuser..."))

        if password:
            os.environ["DJANGO_SUPERUSER_PASSWORD"] = password

        create_kwargs = {}
        if username:
            create_kwargs["username"] = username
        if email:
            create_kwargs["email"] = email
        if username and password:
            create_kwargs["interactive"] = False

        call_command("createsuperuser", stdout=self.stdout, stderr=self.stderr, **create_kwargs)

    @staticmethod
    def _quote_identifier(identifier):
        return "`" + identifier.replace("`", "``") + "`"
