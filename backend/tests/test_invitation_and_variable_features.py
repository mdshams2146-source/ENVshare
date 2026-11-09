import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest

# Ensure backend root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi import HTTPException

from app.core.database import Base
from app.core.roles import OWNER_ROLE, MEMBER_ROLE
from app.models.models import (
    User, Project, ProjectMember, Environment, ProjectInvitation, Variable, HistoryLog
)
from app.schemas.schemas import (
    ProjectCreate, VariableCreate, VariableUpdate, ImportParseRequest, BulkImportCommitRequest
)
from app.services.parser import is_sensitive_key, parse_raw_env, compute_diff
from app.core.crypto import decrypt_value
from app.core.security import hash_password

from app.api.projects import (
    create_project,
    get_user_projects,
    get_project_members,
    create_project_invite,
    accept_project_invite,
    AcceptInviteRequest
)
from app.api.variables import (
    create_variable,
    update_variable,
    preview_bulk_diff,
    commit_bulk_import
)


class TestInvitationAndVariableFeatures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Use an isolated in-memory SQLite database
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
        self.db = self.TestSessionLocal()
        # Clean tables between tests
        for table in (Variable, HistoryLog, ProjectInvitation, Environment, ProjectMember, Project, User):
            self.db.query(table).delete()
        self.db.commit()

        # Seed an owner user
        self.owner = User(
            id="owner-uuid-1",
            name="Alice Owner",
            email="owner@example.com",
            password_hash=hash_password("ownerPassword123!"),
            token_version=1
        )
        # Seed a collaborator user
        self.collaborator = User(
            id="collab-uuid-2",
            name="Bob Collaborator",
            email="collab@example.com",
            password_hash=hash_password("collabPassword123!"),
            token_version=1
        )
        self.db.add_all([self.owner, self.collaborator])
        self.db.commit()

        # Create a test project for owner
        proj_res = create_project(
            ProjectCreate(name="Core API", description="Main backend services"),
            db=self.db,
            current_user=self.owner
        )
        self.project_id = proj_res["id"]
        self.env = self.db.query(Environment).filter(Environment.project_id == self.project_id).first()

    def tearDown(self):
        self.db.close()

    # ==========================================
    # ISSUE 1: INVITATION FLOW & MEMBERSHIP
    # ==========================================

    def test_owner_can_generate_invite_and_collaborator_can_accept(self):
        # 1. Owner generates invite link
        invite_res = create_project_invite(self.project_id, db=self.db, current_user=self.owner)
        token = invite_res["token"]
        self.assertTrue(token)

        # 2. Collaborator accepts invite
        accept_res = accept_project_invite(
            AcceptInviteRequest(token=token),
            db=self.db,
            current_user=self.collaborator
        )
        self.assertEqual(accept_res["project_id"], self.project_id)
        self.assertIn("joined", accept_res["message"].lower())

        # 3. Verify membership record
        member = self.db.query(ProjectMember).filter(
            ProjectMember.project_id == self.project_id,
            ProjectMember.user_id == self.collaborator.id
        ).first()
        self.assertIsNotNone(member)
        self.assertEqual(member.role, MEMBER_ROLE)

        # 4. Collaborator sees project in their project list
        collab_projects = get_user_projects(db=self.db, current_user=self.collaborator)
        self.assertEqual(len(collab_projects), 1)
        self.assertEqual(collab_projects[0]["id"], self.project_id)
        self.assertEqual(collab_projects[0]["role"], MEMBER_ROLE)

        # 5. Members endpoint returns both owner and collaborator
        members_list = get_project_members(self.project_id, db=self.db, current_user=self.owner)
        self.assertEqual(len(members_list), 2)
        roles = {m["email"]: m["role"] for m in members_list}
        self.assertEqual(roles["owner@example.com"], OWNER_ROLE)
        self.assertEqual(roles["collab@example.com"], MEMBER_ROLE)

    def test_owner_visiting_invite_does_not_consume_or_burn_token(self):
        """Regression test: Owner opening their own invite link must not mark it as used."""
        invite_res = create_project_invite(self.project_id, db=self.db, current_user=self.owner)
        token = invite_res["token"]

        # Owner opens the link (already a member)
        res = accept_project_invite(
            AcceptInviteRequest(token=token),
            db=self.db,
            current_user=self.owner
        )
        self.assertEqual(res["project_id"], self.project_id)
        self.assertIn("already a member", res["message"])

        # Verify the token is NOT marked as used
        invite_record = self.db.query(ProjectInvitation).filter(ProjectInvitation.token == token).first()
        self.assertFalse(invite_record.is_used)

        # Collaborator can still successfully use this invite link!
        accept_res = accept_project_invite(
            AcceptInviteRequest(token=token),
            db=self.db,
            current_user=self.collaborator
        )
        self.assertEqual(accept_res["project_id"], self.project_id)
        self.assertIn("joined", accept_res["message"].lower())

        # Now it is marked used
        self.db.refresh(invite_record)
        self.assertTrue(invite_record.is_used)

    def test_invite_token_is_strictly_single_use(self):
        invite_res = create_project_invite(self.project_id, db=self.db, current_user=self.owner)
        token = invite_res["token"]

        # First claim succeeds
        accept_project_invite(
            AcceptInviteRequest(token=token),
            db=self.db,
            current_user=self.collaborator
        )

        # Create a third user
        user3 = User(
            id="user3-uuid",
            name="Charlie User",
            email="charlie@example.com",
            password_hash=hash_password("password123!"),
            token_version=1
        )
        self.db.add(user3)
        self.db.commit()

        # Second claim attempt must fail
        with self.assertRaises(HTTPException) as ctx:
            accept_project_invite(
                AcceptInviteRequest(token=token),
                db=self.db,
                current_user=user3
            )
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("already been used", ctx.exception.detail)

    def test_expired_and_invalid_tokens_are_rejected(self):
        # 1. Invalid token
        with self.assertRaises(HTTPException) as ctx:
            accept_project_invite(
                AcceptInviteRequest(token="non-existent-token"),
                db=self.db,
                current_user=self.collaborator
            )
        self.assertEqual(ctx.exception.status_code, 404)

        # 2. Expired token
        expired_invite = ProjectInvitation(
            project_id=self.project_id,
            token="expired-token-123",
            role=MEMBER_ROLE,
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
            is_used=False
        )
        self.db.add(expired_invite)
        self.db.commit()

        with self.assertRaises(HTTPException) as ctx:
            accept_project_invite(
                AcceptInviteRequest(token="expired-token-123"),
                db=self.db,
                current_user=self.collaborator
            )
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("expired", ctx.exception.detail)

    # ==========================================
    # ISSUE 2: VARIABLE EDIT ACTION
    # ==========================================

    def test_update_variable_preserves_encryption_and_logs_history(self):
        # Create initial variable
        create_res = create_variable(
            env_id=self.env.id,
            var_in=VariableCreate(key="APP_PORT", value="3000", is_sensitive=False),
            db=self.db,
            current_user=self.owner
        )
        var_id = create_res["id"]

        # Update value via update_variable
        updated = update_variable(
            env_id=self.env.id,
            var_id=var_id,
            var_in=VariableUpdate(value="8080"),
            db=self.db,
            current_user=self.owner
        )
        self.assertEqual(updated["value"], "8080")
        self.assertFalse(updated["is_sensitive"])

        # Check DB & history
        db_var = self.db.query(Variable).filter(Variable.id == var_id).first()
        self.assertEqual(db_var.value, "8080")

        history = self.db.query(HistoryLog).filter(
            HistoryLog.key == "APP_PORT",
            HistoryLog.action == "UPDATE"
        ).first()
        self.assertIsNotNone(history)

    def test_update_sensitive_variable_encrypts_and_prevents_downgrade(self):
        # Create sensitive variable
        create_res = create_variable(
            env_id=self.env.id,
            var_in=VariableCreate(key="DB_SECRET", value="InitialPass123", is_sensitive=True),
            db=self.db,
            current_user=self.owner
        )
        var_id = create_res["id"]

        # Update value while remaining sensitive
        updated = update_variable(
            env_id=self.env.id,
            var_id=var_id,
            var_in=VariableUpdate(value="NewSuperSecretPass456!"),
            db=self.db,
            current_user=self.owner
        )
        self.assertEqual(updated["value"], "••••••••")
        self.assertTrue(updated["is_sensitive"])

        # Check that value in DB is ciphertext and decryptable
        db_var = self.db.query(Variable).filter(Variable.id == var_id).first()
        self.assertNotEqual(db_var.value, "NewSuperSecretPass456!")
        decrypted = decrypt_value(db_var.value, db_var.iv)
        self.assertEqual(decrypted, "NewSuperSecretPass456!")

        # Attempting to downgrade sensitive variable to plaintext must fail
        with self.assertRaises(HTTPException) as ctx:
            update_variable(
                env_id=self.env.id,
                var_id=var_id,
                var_in=VariableUpdate(is_sensitive=False),
                db=self.db,
                current_user=self.owner
            )
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("cannot mark known secret keys as non-sensitive", ctx.exception.detail.lower())

    # ==========================================
    # ISSUE 3: SENSITIVE IMPORT PREVIEW REDACTION
    # ==========================================

    def test_sensitive_key_heuristics(self):
        # Keys that MUST be sensitive
        sensitive_test_keys = [
            "DATABASE_URL",
            "API_SECRET",
            "PASSWORD",
            "ACCESS_TOKEN",
            "MONGO_URI",
            "REDIS_URL",
            "DB_URL",
            "CONNECTION_STRING"
        ]
        for key in sensitive_test_keys:
            with self.subTest(key=key):
                self.assertTrue(is_sensitive_key(key), f"{key} should be sensitive")

        # Keys that MUST NOT be sensitive
        non_sensitive_test_keys = [
            "APP_NAME",
            "DEBUG",
            "PORT",
            "HOST",
            "NODE_ENV"
        ]
        for key in non_sensitive_test_keys:
            with self.subTest(key=key):
                self.assertFalse(is_sensitive_key(key), f"{key} should not be sensitive")

    def test_import_preview_redacts_database_url_and_secrets(self):
        raw_env = (
            "DATABASE_URL=postgres://user:supersecret@localhost:5432/mydb\n"
            "API_SECRET=sk_live_123456789\n"
            "PASSWORD=secret_password_here\n"
            "ACCESS_TOKEN=jwt_token_here\n"
            "APP_NAME=EnvSharePro\n"
            "DEBUG=true\n"
            "PORT=8000\n"
        )
        preview_res = preview_bulk_diff(
            env_id=self.env.id,
            payload=ImportParseRequest(raw_env=raw_env),
            db=self.db,
            current_user=self.owner
        )
        by_key = {item["key"]: item for item in preview_res}

        # Sensitive keys MUST have is_sensitive=True and redacted new_value
        for secret_key in ["DATABASE_URL", "API_SECRET", "PASSWORD", "ACCESS_TOKEN"]:
            self.assertTrue(by_key[secret_key]["is_sensitive"], f"{secret_key} must be marked sensitive")
            self.assertEqual(by_key[secret_key]["new_value"], "[REDACTED]", f"{secret_key} new_value must be redacted")

        # Non-sensitive keys MUST have is_sensitive=False and plaintext values preserved
        self.assertFalse(by_key["APP_NAME"]["is_sensitive"])
        self.assertEqual(by_key["APP_NAME"]["new_value"], "EnvSharePro")
        self.assertFalse(by_key["DEBUG"]["is_sensitive"])
        self.assertEqual(by_key["DEBUG"]["new_value"], "true")
        self.assertFalse(by_key["PORT"]["is_sensitive"])
        self.assertEqual(by_key["PORT"]["new_value"], "8000")

    def test_import_commit_encrypts_database_url_at_rest(self):
        raw_env = (
            "DATABASE_URL=postgres://user:topsecret@localhost:5432/mydb\n"
            "PORT=3000\n"
        )
        commit_bulk_import(
            env_id=self.env.id,
            payload=BulkImportCommitRequest(
                raw_env=raw_env,
                sensitive_keys=["DATABASE_URL"]
            ),
            db=self.db,
            current_user=self.owner
        )

        db_db_url = self.db.query(Variable).filter(
            Variable.environment_id == self.env.id,
            Variable.key == "DATABASE_URL"
        ).first()
        self.assertIsNotNone(db_db_url)
        self.assertTrue(db_db_url.is_sensitive)
        self.assertNotEqual(db_db_url.value, "postgres://user:topsecret@localhost:5432/mydb")
        decrypted = decrypt_value(db_db_url.value, db_db_url.iv)
        self.assertEqual(decrypted, "postgres://user:topsecret@localhost:5432/mydb")

        # Port remains non-sensitive
        db_port = self.db.query(Variable).filter(
            Variable.environment_id == self.env.id,
            Variable.key == "PORT"
        ).first()
        self.assertIsNotNone(db_port)
        self.assertFalse(db_port.is_sensitive)
        self.assertEqual(db_port.value, "3000")


if __name__ == "__main__":
    unittest.main()

