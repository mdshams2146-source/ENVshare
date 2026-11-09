import concurrent.futures
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

# Ensure backend root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import HTTPException

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.api.auth import forgot_password, reset_password
from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import Base
from app.core.rate_limit import auth_rate_limiter
from app.core.security import (
    create_access_token,
    create_password_reset_token,
    get_reset_token_secret,
    hash_password,
    hash_token,
    verify_password,
)
from app.models.models import User
from app.schemas.schemas import (
    ForgotPasswordRequest,
    ResetPasswordRequest,
)
from sqlalchemy.pool import StaticPool


class TestAuthRemediation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Use a shared in-memory SQLite database across connections
        cls.test_engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool
        )
        Base.metadata.create_all(bind=cls.test_engine)
        cls.TestSessionLocal = sessionmaker(
            autocommit=False, autoflush=False, bind=cls.test_engine
        )

    def setUp(self):
        # Reset rate limiter memory before each test
        auth_rate_limiter.history.clear()

        self.db = self.TestSessionLocal()
        # Clean users table in test in-memory DB
        self.db.query(User).delete()
        self.db.commit()


        # Create a sample test user
        self.test_user = User(
            name="Security Tester",
            email="tester@example.com",
            password_hash=hash_password("OldPassword123!"),
            token_version=1
        )
        self.db.add(self.test_user)
        self.db.commit()
        self.db.refresh(self.test_user)

        # Mock request with dummy client IP for rate limiting
        self.mock_request = MagicMock()
        self.mock_request.client.host = "127.0.0.1"
        self.mock_request.url.path = "/api/auth/test"

    def tearDown(self):
        self.db.close()

    # -------------------------------------------------------------
    # 1. AUTH-02: Secret Validation & Environment Separation
    # -------------------------------------------------------------
    def test_production_reset_secret_validation(self):
        """Test production startup failure when RESET_TOKEN_SECRET is missing, weak, or equal to JWT_SECRET."""
        with patch.object(settings, "APP_ENV", "production"):
            # A) Missing or empty secret
            with patch.object(settings, "RESET_TOKEN_SECRET", ""):
                with self.assertRaises(ValueError) as ctx:
                    get_reset_token_secret()
                self.assertIn("must be explicitly configured", str(ctx.exception))

            # B) Equal to general JWT_SECRET
            with patch.object(settings, "RESET_TOKEN_SECRET", settings.JWT_SECRET):
                with self.assertRaises(ValueError) as ctx:
                    get_reset_token_secret()
                self.assertIn("must be dedicated and distinct from JWT_SECRET", str(ctx.exception))

            # C) Weak secret (< 32 bytes)
            with patch.object(settings, "RESET_TOKEN_SECRET", "short_weak_secret"):
                with self.assertRaises(ValueError) as ctx:
                    get_reset_token_secret()
                self.assertIn("at least 32 bytes of entropy", str(ctx.exception))

            # D) Valid dedicated secret (>= 32 bytes)
            valid_secret = "a_very_strong_dedicated_production_reset_secret_with_sufficient_entropy_12345"
            with patch.object(settings, "RESET_TOKEN_SECRET", valid_secret):
                secret = get_reset_token_secret()
                self.assertEqual(secret, valid_secret)

    def test_development_fallback_secret(self):
        """Test development configuration fallback when RESET_TOKEN_SECRET is omitted."""
        with patch.object(settings, "APP_ENV", "development"):
            with patch.object(settings, "RESET_TOKEN_SECRET", ""):
                dev_secret = get_reset_token_secret()
                self.assertTrue(len(dev_secret) >= 32)
                self.assertIn("dev-insecure-reset-token-secret", dev_secret)

    # -------------------------------------------------------------
    # 2. AUTH-01: Genuinely Single-Use Reset Tokens & Atomic Consumption
    # -------------------------------------------------------------
    def test_valid_password_reset_flow(self):
        """Test successful reset: hash storage, atomic consumption, and clearing."""
        # 1. Request reset
        with patch("app.api.auth.send_password_reset_email") as mock_email:
            res = forgot_password(
                self.mock_request,
                ForgotPasswordRequest(email="tester@example.com"),
                self.db
            )
            self.assertIn("If an account matches that email", res["message"])
            self.assertTrue(mock_email.called)
            sent_token = mock_email.call_args[0][1]

        # Verify database stored ONLY the SHA-256 hash and an expiry date
        self.db.refresh(self.test_user)
        expected_hash = hash_token(sent_token)
        self.assertEqual(self.test_user.reset_token_hash, expected_hash)
        self.assertIsNotNone(self.test_user.reset_token_expires_at)
        exp = self.test_user.reset_token_expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        self.assertGreater(exp, datetime.now(timezone.utc))


        # 2. Perform reset
        reset_res = reset_password(
            self.mock_request,
            ResetPasswordRequest(token=sent_token, new_password="NewSecurePassword456!"),
            self.db
        )
        self.assertIn("Password updated successfully", reset_res["message"])

        # Verify token is cleared from the database (single-use)
        self.db.refresh(self.test_user)
        self.assertIsNone(self.test_user.reset_token_hash)
        self.assertIsNone(self.test_user.reset_token_expires_at)
        self.assertTrue(verify_password("NewSecurePassword456!", self.test_user.password_hash))
        # Verify token_version incremented
        self.assertEqual(self.test_user.token_version, 2)

    def test_reused_password_reset_fails(self):
        """Test that a reset token cannot be reused once consumed."""
        with patch("app.api.auth.send_password_reset_email") as mock_email:
            forgot_password(
                self.mock_request,
                ForgotPasswordRequest(email="tester@example.com"),
                self.db
            )
            sent_token = mock_email.call_args[0][1]

        # First consumption succeeds
        reset_password(
            self.mock_request,
            ResetPasswordRequest(token=sent_token, new_password="FirstNewPassword123!"),
            self.db
        )

        # Second consumption MUST fail
        with self.assertRaises(HTTPException) as ctx:
            reset_password(
                self.mock_request,
                ResetPasswordRequest(token=sent_token, new_password="SecondNewPassword456!"),
                self.db
            )
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("already been used", ctx.exception.detail)

    def test_expired_password_reset_fails(self):
        """Test that an expired reset token is rejected."""
        with patch("app.api.auth.send_password_reset_email") as mock_email:
            forgot_password(
                self.mock_request,
                ForgotPasswordRequest(email="tester@example.com"),
                self.db
            )
            sent_token = mock_email.call_args[0][1]

        # Force expiry in the past
        self.test_user.reset_token_expires_at = datetime.now(timezone.utc) - timedelta(minutes=5)
        self.db.commit()

        with self.assertRaises(HTTPException) as ctx:
            reset_password(
                self.mock_request,
                ResetPasswordRequest(token=sent_token, new_password="ExpiredPassword123!"),
                self.db
            )
        self.assertEqual(ctx.exception.status_code, 400)

    def test_new_forgot_password_invalidates_previous_token(self):
        """Test issuing a second reset token invalidates any previously outstanding token."""
        with patch("app.api.auth.send_password_reset_email") as mock_email:
            # First request
            forgot_password(
                self.mock_request,
                ForgotPasswordRequest(email="tester@example.com"),
                self.db
            )
            token_1 = mock_email.call_args[0][1]

            # Second request
            forgot_password(
                self.mock_request,
                ForgotPasswordRequest(email="tester@example.com"),
                self.db
            )
            token_2 = mock_email.call_args[0][1]

        self.assertNotEqual(token_1, token_2)

        # Token 1 must fail because Token 2 replaced its hash in the database
        with self.assertRaises(HTTPException) as ctx:
            reset_password(
                self.mock_request,
                ResetPasswordRequest(token=token_1, new_password="AttemptPassword1!"),
                self.db
            )
        self.assertEqual(ctx.exception.status_code, 400)

        # Token 2 must succeed
        res = reset_password(
            self.mock_request,
            ResetPasswordRequest(token=token_2, new_password="ValidPassword2!"),
            self.db
        )
        self.assertIn("Password updated successfully", res["message"])

    def test_concurrent_reset_attempts(self):
        """Test concurrent requests cannot both successfully reset the password.

        Uses an isolated file-backed SQLite database with WAL mode and independent
        connections to accurately simulate multi-process/thread production concurrency.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_db_path = os.path.join(tmpdir, "test_concurrent_auth.db")
            concurrent_engine = create_engine(
                f"sqlite:///{temp_db_path}",
                connect_args={"check_same_thread": False, "timeout": 30.0}
            )

            @event.listens_for(concurrent_engine, "connect")
            def set_temp_sqlite_pragma(dbapi_connection, connection_record):
                cursor = dbapi_connection.cursor()
                try:
                    cursor.execute("PRAGMA journal_mode=WAL")
                    cursor.execute("PRAGMA synchronous=NORMAL")
                    cursor.execute("PRAGMA busy_timeout=30000")
                except Exception:
                    pass
                finally:
                    cursor.close()

            Base.metadata.create_all(bind=concurrent_engine)
            ConcurrentSessionLocal = sessionmaker(
                autocommit=False, autoflush=False, bind=concurrent_engine
            )

            # Create test user in isolated database
            setup_db = ConcurrentSessionLocal()
            concurrent_user = User(
                name="Concurrent Tester",
                email="concurrent_tester@example.com",
                password_hash=hash_password("OldPassword123!"),
                token_version=1
            )
            setup_db.add(concurrent_user)
            setup_db.commit()

            with patch("app.api.auth.send_password_reset_email") as mock_email:
                forgot_password(
                    self.mock_request,
                    ForgotPasswordRequest(email="concurrent_tester@example.com"),
                    setup_db
                )
                token = mock_email.call_args[0][1]
            setup_db.close()

            def attempt_reset(pwd):
                thread_db = ConcurrentSessionLocal()
                try:
                    reset_password(
                        self.mock_request,
                        ResetPasswordRequest(token=token, new_password=pwd),
                        thread_db
                    )
                    return True
                except HTTPException:
                    return False
                finally:
                    thread_db.close()

            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                f1 = executor.submit(attempt_reset, "ConcurrentPassA1!")
                f2 = executor.submit(attempt_reset, "ConcurrentPassB2!")
                results = [f1.result(), f2.result()]

            concurrent_engine.dispose()

            success_count = results.count(True)
            failure_count = results.count(False)

            # Genuinely atomic: exactly ONE request succeeds, the other fails
            self.assertEqual(success_count, 1)
            self.assertEqual(failure_count, 1)

    # -------------------------------------------------------------
    # 3. CONFIG-04: Session Revocation via token_version
    # -------------------------------------------------------------
    def test_access_token_invalidation_after_password_reset(self):
        """Test access-token rejection after password reset increments token_version."""
        # 1. Issue access token for current user at token_version=1
        token = create_access_token({
            "sub": self.test_user.id,
            "email": self.test_user.email,
            "token_version": self.test_user.token_version
        })

        # Token is initially valid
        user_auth = get_current_user(token=token, db=self.db)
        self.assertEqual(user_auth.id, self.test_user.id)

        # 2. Reset password -> increments token_version to 2
        with patch("app.api.auth.send_password_reset_email") as mock_email:
            forgot_password(
                self.mock_request,
                ForgotPasswordRequest(email=self.test_user.email),
                self.db
            )
            reset_tok = mock_email.call_args[0][1]

        reset_password(
            self.mock_request,
            ResetPasswordRequest(token=reset_tok, new_password="BrandNewPassword99!"),
            self.db
        )

        # 3. Old access token MUST now be rejected (HTTP 401)
        with self.assertRaises(HTTPException) as ctx:
            get_current_user(token=token, db=self.db)
        self.assertEqual(ctx.exception.status_code, 401)
        self.assertIn("revoked", ctx.exception.detail)

    def test_rejection_of_access_tokens_missing_token_version(self):
        """Test rejection of access tokens missing the required token_version claim."""
        token_without_version = create_access_token({
            "sub": self.test_user.id,
            "email": self.test_user.email,
            # token_version omitted
        })

        with self.assertRaises(HTTPException) as ctx:
            get_current_user(token=token_without_version, db=self.db)
        self.assertEqual(ctx.exception.status_code, 401)
        self.assertIn("missing token_version claim", ctx.exception.detail)

    # -------------------------------------------------------------
    # 4. AUTH-03: Generic Email Response & Server-Side Logging
    # -------------------------------------------------------------
    def test_smtp_exception_does_not_leak_or_alter_generic_response(self):
        """Test that SMTP dispatch exceptions are caught, logged, and return the generic response."""
        with patch("app.api.auth.send_password_reset_email", side_effect=Exception("SMTPAuthenticationError: Bad credentials")):
            with patch("app.api.auth.logger.error") as mock_log:
                res = forgot_password(
                    self.mock_request,
                    ForgotPasswordRequest(email=self.test_user.email),
                    self.db
                )
                self.assertIn("If an account matches that email", res["message"])
                self.assertTrue(mock_log.called)
                # Verify sensitive detail wasn't logged or returned
                log_args = str(mock_log.call_args)
                self.assertNotIn("Bad credentials", log_args)

    # -------------------------------------------------------------
    # 5. Database Record Count Verification
    # -------------------------------------------------------------
    def test_existing_database_records_untouched(self):
        """Verify that the existing database records and counts are preserved."""
        db_path = Path(__file__).resolve().parent.parent / "envshare.db"
        if not db_path.exists():
            self.skipTest("backend/envshare.db not found for count verification")

        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        min_expected_counts = {
            "users": 2,
            "projects": 2,
            "project_members": 2,
            "environments": 6,
            "project_invitations": 4,
            "variables": 5,
            "history_logs": 7,
            "environment_snapshots": 4
        }

        for table, min_expected in min_expected_counts.items():
            cursor.execute(f"SELECT count(*) FROM {table}")
            actual = cursor.fetchone()[0]
            self.assertGreaterEqual(actual, min_expected, f"Table {table} records lost: expected at least {min_expected}, got {actual}")

        # Check existing users have valid token_version=1
        cursor.execute("SELECT token_version FROM users")
        versions = cursor.fetchall()
        for v in versions:
            self.assertIsNotNone(v[0])
            self.assertGreaterEqual(v[0], 1)

        conn.close()


if __name__ == "__main__":
    unittest.main()
