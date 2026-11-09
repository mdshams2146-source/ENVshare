import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import HTTPException

from app.core.roles import (
    OWNER_ROLE,
    MEMBER_ROLE,
    is_supported_project_role,
)
from app.api.variables import verify_env_access as verify_variable_access
from app.api.snapshots import verify_env_access as verify_snapshot_access


class TestRolePolicy(unittest.TestCase):
    def test_supported_roles(self):
        self.assertTrue(is_supported_project_role(OWNER_ROLE))
        self.assertTrue(is_supported_project_role(MEMBER_ROLE))

    def test_unsupported_roles(self):
        self.assertFalse(is_supported_project_role("ADMIN"))
        self.assertFalse(is_supported_project_role("MANAGER"))
        self.assertFalse(is_supported_project_role(""))
        self.assertFalse(is_supported_project_role(None))

    def verify_helper(self, helper, role):
        db = MagicMock()
        environment = SimpleNamespace(id="env-1", project_id="project-1")
        member = SimpleNamespace(role=role)

        db.query.return_value.filter.return_value.first.side_effect = [
            environment,
            member,
        ]

        result = helper("env-1", "user-1", db)
        self.assertEqual(result, environment)

    def test_variable_access_accepts_owner_and_member(self):
        for role in (OWNER_ROLE, MEMBER_ROLE):
            with self.subTest(role=role):
                self.verify_helper(verify_variable_access, role)

    def test_snapshot_access_accepts_owner_and_member(self):
        for role in (OWNER_ROLE, MEMBER_ROLE):
            with self.subTest(role=role):
                self.verify_helper(verify_snapshot_access, role)

    def test_variable_access_rejects_unsupported_role(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.side_effect = [
            SimpleNamespace(id="env-1", project_id="project-1"),
            SimpleNamespace(role="ADMIN"),
        ]

        with self.assertRaises(HTTPException) as context:
            verify_variable_access("env-1", "user-1", db)

        self.assertEqual(context.exception.status_code, 403)

    def test_snapshot_access_rejects_unsupported_role(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.side_effect = [
            SimpleNamespace(id="env-1", project_id="project-1"),
            SimpleNamespace(role="ADMIN"),
        ]

        with self.assertRaises(HTTPException) as context:
            verify_snapshot_access("env-1", "user-1", db)

        self.assertEqual(context.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
