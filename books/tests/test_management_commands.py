"""
Tests for the management commands related to scanning.
"""

import os
import tempfile
from io import StringIO
from unittest.mock import ANY, MagicMock, call, patch

from django.conf import settings as django_settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from books.tests.test_helpers import create_test_book_with_file, create_test_scan_folder


class ScanBooksCommandTest(TestCase):
    """Tests for the scan_books management command."""

    def setUp(self):
        self.scan_folder = create_test_scan_folder(name="Test Folder")

    @patch("books.scanner.background.BackgroundScanner")
    @patch("books.management.commands.scan_books.check_api_health")
    def test_scan_folder_command(self, mock_api_health, mock_scanner_class):
        """Test the `scan` action of the command."""
        mock_api_health.return_value = {"google_books": True}
        mock_scanner = mock_scanner_class.return_value
        mock_scanner.scan_folder.return_value = {"success": True, "message": "Test completed"}

        call_command("scan_books", "scan", "/fake/dir")

        mock_scanner_class.assert_called_once()
        mock_scanner.scan_folder.assert_called_once_with("/fake/dir", "en", True)

    @patch("books.management.commands.scan_books.background_scan_folder")
    def test_scan_folder_background_wait(self, mock_scan_folder):
        """Test the `scan` action with --background and --wait flags."""
        with patch("books.management.commands.scan_books.Command.wait_for_completion") as mock_wait:
            call_command("scan_books", "scan", "/fake/dir", "--background", "--wait")
            mock_scan_folder.assert_called_once()
            mock_wait.assert_called_once()

    @patch("books.scanner.background.BackgroundScanner")
    @patch("books.management.commands.scan_books.check_api_health")
    def test_rescan_all_command(self, mock_api_health, mock_scanner_class):
        """Test the `rescan --all` action."""
        mock_api_health.return_value = {"google_books": True}
        mock_scanner = mock_scanner_class.return_value
        mock_scanner.rescan_existing_books.return_value = {"success": True, "message": "Test completed"}

        book = create_test_book_with_file(file_path="/fake/dir/book1.epub", scan_folder=self.scan_folder)
        call_command("scan_books", "rescan", "--all")

        mock_scanner_class.assert_called_once()
        mock_scanner.rescan_existing_books.assert_called_once_with([book.id], True)

    @patch("books.scanner.background.BackgroundScanner")
    @patch("books.management.commands.scan_books.check_api_health")
    def test_rescan_by_ids_command(self, mock_api_health, mock_scanner_class):
        """Test the `rescan --book-ids` action."""
        mock_api_health.return_value = {"google_books": True}
        mock_scanner = mock_scanner_class.return_value
        mock_scanner.rescan_existing_books.return_value = {"success": True, "message": "Test completed"}

        book1 = create_test_book_with_file(file_path="/fake/dir/book1.epub", scan_folder=self.scan_folder)
        book2 = create_test_book_with_file(file_path="/fake/dir/book2.epub", scan_folder=self.scan_folder)
        call_command("scan_books", "rescan", "--book-ids", str(book1.id), str(book2.id))

        mock_scanner_class.assert_called_once()
        mock_scanner.rescan_existing_books.assert_called_once_with([book1.id, book2.id], True)

    @patch("books.scanner.background.BackgroundScanner")
    @patch("books.management.commands.scan_books.check_api_health")
    def test_rescan_folder_command(self, mock_api_health, mock_scanner_class):
        """Test the `rescan --folder` action targets only that folder's books."""
        mock_api_health.return_value = {"google_books": True}
        mock_scanner = mock_scanner_class.return_value
        mock_scanner.rescan_existing_books.return_value = {"success": True, "message": "Test completed"}

        book = create_test_book_with_file(file_path="/fake/dir/book1.epub", scan_folder=self.scan_folder)
        call_command("scan_books", "rescan", "--folder", self.scan_folder.path)

        mock_scanner_class.assert_called_once()
        mock_scanner.rescan_existing_books.assert_called_once_with([book.id], True)

    @patch("books.scanner.background.BackgroundScanner")
    @patch("books.management.commands.scan_books.check_api_health")
    def test_rescan_no_external_apis_disables_deep_scan(self, mock_api_health, mock_scanner_class):
        """`rescan --no-external-apis` skips the external (Deep Scan) pass entirely."""
        mock_scanner = mock_scanner_class.return_value
        mock_scanner.rescan_existing_books.return_value = {"success": True, "message": "Test completed"}

        book = create_test_book_with_file(file_path="/fake/dir/book1.epub", scan_folder=self.scan_folder)
        call_command("scan_books", "rescan", "--all", "--no-external-apis")

        mock_api_health.assert_not_called()
        mock_scanner.rescan_existing_books.assert_called_once_with([book.id], False)

    def test_rescan_no_target_error(self):
        """Test that `rescan` raises an error if no target is specified."""
        with self.assertRaises(CommandError):
            call_command("scan_books", "rescan")

    @patch("books.management.commands.scan_books.get_scan_progress")
    def test_status_command(self, mock_get_progress):
        """Test the `status` action."""
        mock_get_progress.return_value = {"percentage": 50, "status": "Running"}
        out = StringIO()
        call_command("scan_books", "status", "--job-id", "test-job", stdout=out)
        self.assertIn("Status: Running", out.getvalue())
        self.assertIn("Progress: 0/0 (50%)", out.getvalue())

    @patch("books.management.commands.scan_books.get_api_status")
    def test_status_apis_command(self, mock_get_api_status):
        """Test the `status --apis` action."""
        mock_get_api_status.return_value = {"google_books": {"api_name": "Google Books", "rate_limits": {}}}
        out = StringIO()
        call_command("scan_books", "status", "--apis", stdout=out)
        self.assertIn("API Rate Limit Status:", out.getvalue())
        self.assertIn("Google Books", out.getvalue())

    @patch("books.scanner.background.BackgroundScanner")
    @patch("books.management.commands.scan_books.check_api_health")
    def test_scan_resume_flag(self, mock_api_health, mock_scanner_class):
        """Test the `scan --resume` action dispatches to resume_scan."""
        mock_api_health.return_value = {"google_books": True}
        mock_scanner = mock_scanner_class.return_value
        mock_scanner.resume_scan.return_value = {"success": True, "message": "Resumed"}

        call_command("scan_books", "scan", "/fake/dir", "--resume")

        mock_scanner.resume_scan.assert_called_once_with("/fake/dir", "en", True)
        mock_scanner.scan_folder.assert_not_called()


class ScanContentIsbnCommandTest(TestCase):
    """Tests for the scan_content_isbn management command."""

    @patch("books.scanner.extractors.content_isbn.bulk_scan_content_isbns")
    def test_scan_content_isbn_command(self, mock_bulk_scan):
        """Test the basic execution of the command."""
        # Configure mock to return proper dictionary structure
        mock_bulk_scan.return_value = {"total_books": 1, "books_with_isbns": 0, "total_isbns_found": 0, "errors": 0}
        create_test_book_with_file(file_path="/fake/book.epub", file_format="epub")
        call_command("scan_content_isbn")
        mock_bulk_scan.assert_called_once()


class _MySQLDBError(Exception):
    """Stand-in for MySQLdb.Error in tests."""


class ResetDatabaseCommandTest(TestCase):
    """Tests for the reset_database management command."""

    MYSQL_CONFIG = {
        "ENGINE": "django.db.backends.mysql",
        "NAME": "test_ebook_manager",
        "USER": "ebook_user",
        "PASSWORD": "secret",
        "HOST": "db.example.com",
        "PORT": "3307",
        "OPTIONS": {"charset": "utf8mb4"},
    }

    def tearDown(self):
        for key in ("DJANGO_SUPERUSER_USERNAME", "DJANGO_SUPERUSER_EMAIL", "DJANGO_SUPERUSER_PASSWORD"):
            os.environ.pop(key, None)

    def test_non_mysql_engine_raises(self):
        """The command refuses to run when the active engine is not MySQL."""
        with self.assertRaises(CommandError):
            call_command("reset_database", "--noinput")

    @patch("books.management.commands.reset_database.MySQLdb")
    @patch("books.management.commands.reset_database.call_command")
    def test_mysql_rebuild_flow(self, mock_call_command, mock_mysql):
        """Drops and recreates the database, then runs makemigrations and migrate."""
        mock_connection = mock_mysql.connect.return_value
        mock_cursor = mock_connection.cursor.return_value

        with patch.object(django_settings, "DATABASES", {"default": self.MYSQL_CONFIG}):
            call_command("reset_database", "--noinput", "--skip-backup")

        mock_mysql.connect.assert_called_once_with(
            host="db.example.com",
            user="ebook_user",
            password="secret",
            port=3307,
            charset="utf8mb4",
        )

        statements = [call[0][0] for call in mock_cursor.execute.call_args_list]
        self.assertIn("DROP DATABASE IF EXISTS `test_ebook_manager`", statements[0])
        self.assertIn("CREATE DATABASE `test_ebook_manager`", statements[1])
        self.assertIn("utf8mb4", statements[1])

        mock_call_command.assert_any_call("makemigrations", "books", interactive=False, stdout=ANY, stderr=ANY)
        mock_call_command.assert_any_call("migrate", interactive=False, stdout=ANY, stderr=ANY)

    @patch("books.management.commands.reset_database.MySQLdb")
    def test_prompt_declines_abort(self, mock_mysql):
        """Declining the confirmation prompt aborts before any destructive call."""
        with patch.object(django_settings, "DATABASES", {"default": self.MYSQL_CONFIG}):
            with patch("builtins.input", return_value="no"):
                call_command("reset_database")

        mock_mysql.connect.assert_not_called()

    @patch("books.management.commands.reset_database.MySQLdb")
    @patch("books.management.commands.reset_database.call_command")
    def test_superuser_explicit_flags(self, mock_call_command, mock_mysql):
        """Explicit flags take precedence for superuser creation."""
        with patch.object(django_settings, "DATABASES", {"default": self.MYSQL_CONFIG}):
            call_command(
                "reset_database",
                "--noinput",
                "--skip-backup",
                "--superuser",
                "--superuser-username",
                "admin2",
                "--superuser-email",
                "admin2@example.com",
                "--superuser-password",
                "pw2",
            )

        mock_call_command.assert_any_call(
            "createsuperuser",
            interactive=False,
            username="admin2",
            email="admin2@example.com",
            stdout=ANY,
            stderr=ANY,
        )

    @patch("books.management.commands.reset_database.MySQLdb")
    @patch("books.management.commands.reset_database.call_command")
    def test_superuser_env_vars(self, mock_call_command, mock_mysql):
        """DJANGO_SUPERUSER_* env vars are used when explicit flags are absent."""
        env = {
            "DJANGO_SUPERUSER_USERNAME": "envuser",
            "DJANGO_SUPERUSER_EMAIL": "env@example.com",
            "DJANGO_SUPERUSER_PASSWORD": "envpw",
        }
        with patch.object(django_settings, "DATABASES", {"default": self.MYSQL_CONFIG}):
            with patch.dict(os.environ, env):
                call_command("reset_database", "--noinput", "--skip-backup", "--superuser")

        mock_call_command.assert_any_call(
            "createsuperuser",
            interactive=False,
            username="envuser",
            email="env@example.com",
            stdout=ANY,
            stderr=ANY,
        )

    @patch("books.management.commands.reset_database.MySQLdb")
    @patch("books.management.commands.reset_database.call_command")
    def test_superuser_interactive_fallback(self, mock_call_command, mock_mysql):
        """Without flags or env vars, createsuperuser is run interactively."""
        env = {
            "DJANGO_SUPERUSER_USERNAME": "",
            "DJANGO_SUPERUSER_EMAIL": "",
            "DJANGO_SUPERUSER_PASSWORD": "",
        }
        with patch.object(django_settings, "DATABASES", {"default": self.MYSQL_CONFIG}):
            with patch.dict(os.environ, env):
                call_command("reset_database", "--noinput", "--skip-backup", "--superuser")

        mock_call_command.assert_any_call("createsuperuser", stdout=ANY, stderr=ANY)

    @patch("books.management.commands.reset_database.MySQLdb")
    @patch("books.management.commands.reset_database.call_command")
    def test_admin_fallback_on_privilege_error(self, mock_call_command, mock_mysql):
        """When the app user cannot DROP/CREATE, the command retries with DB_ADMIN_*."""
        mock_mysql.Error = _MySQLDBError
        admin_connection = MagicMock()
        admin_cursor = admin_connection.cursor.return_value
        mock_mysql.connect.side_effect = [_MySQLDBError("access denied"), admin_connection]

        with patch.object(django_settings, "DATABASES", {"default": self.MYSQL_CONFIG}):
            with patch.object(django_settings, "DB_ADMIN_USER", "root"):
                with patch.object(django_settings, "DB_ADMIN_PASSWORD", "adminpass"):
                    with patch.object(django_settings, "DB_ADMIN_HOST", "adminhost"):
                        with patch.object(django_settings, "DB_ADMIN_PORT", 3308):
                            call_command("reset_database", "--noinput", "--skip-backup")

        self.assertEqual(
            mock_mysql.connect.call_args_list,
            [
                call(host="db.example.com", user="ebook_user", password="secret", port=3307, charset="utf8mb4"),
                call(host="adminhost", user="root", password="adminpass", port=3308, charset="utf8mb4"),
            ],
        )

        statements = [c[0][0] for c in admin_cursor.execute.call_args_list]
        self.assertIn("DROP DATABASE IF EXISTS `test_ebook_manager`", statements[0])
        self.assertIn("CREATE DATABASE `test_ebook_manager`", statements[1])

    @patch("books.management.commands.reset_database.MySQLdb")
    def test_no_admin_fallback_raises(self, mock_mysql):
        """Without DB_ADMIN_* credentials, a DROP/CREATE failure surfaces as CommandError."""
        mock_mysql.Error = _MySQLDBError
        mock_mysql.connect.side_effect = _MySQLDBError("access denied")

        with patch.object(django_settings, "DATABASES", {"default": self.MYSQL_CONFIG}):
            with patch.object(django_settings, "DB_ADMIN_USER", None):
                with self.assertRaises(CommandError):
                    call_command("reset_database", "--noinput", "--skip-backup")

    @patch("books.management.commands.reset_database.MySQLdb")
    @patch("books.management.commands.reset_database.call_command")
    @patch("books.management.commands.reset_database.Command._backup_database")
    def test_skip_backup(self, mock_backup, mock_call_command, mock_mysql):
        """--skip-backup bypasses the pre-drop backup."""
        with patch.object(django_settings, "DATABASES", {"default": self.MYSQL_CONFIG}):
            call_command("reset_database", "--noinput", "--skip-backup")

        mock_backup.assert_not_called()

    @patch("books.management.commands.reset_database.shutil.which", return_value=None)
    def test_backup_missing_mysqldump_raises(self, mock_which):
        """The command aborts when mysqldump is unavailable and backup is not skipped."""
        with patch.object(django_settings, "DATABASES", {"default": self.MYSQL_CONFIG}):
            with self.assertRaises(CommandError):
                call_command("reset_database", "--noinput")

    @patch("books.management.commands.reset_database.MySQLdb")
    @patch("books.management.commands.reset_database.call_command")
    @patch("books.management.commands.reset_database.subprocess.run")
    @patch("books.management.commands.reset_database.shutil.which", return_value="/usr/bin/mysqldump")
    def test_backup_runs_before_drop(self, mock_which, mock_run, mock_call_command, mock_mysql):
        """A successful mysqldump backup runs before the drop/recreate step."""
        result = MagicMock()
        result.returncode = 0
        result.stderr = b""
        mock_run.return_value = result

        with tempfile.TemporaryDirectory() as backup_dir:
            with patch.object(django_settings, "DATABASES", {"default": self.MYSQL_CONFIG}):
                with patch.object(django_settings, "DB_BACKUP_DIR", backup_dir):
                    call_command("reset_database", "--noinput")

        mock_run.assert_called_once()
        self.assertEqual(mock_run.call_args.kwargs["env"]["MYSQL_PWD"], "secret")
        self.assertIn("mysqldump", mock_run.call_args.args[0][0])
        self.assertIn("--single-transaction", mock_run.call_args.args[0])
