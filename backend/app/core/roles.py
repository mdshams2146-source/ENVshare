OWNER_ROLE = "OWNER"
MEMBER_ROLE = "MEMBER"

SUPPORTED_PROJECT_ROLES = frozenset({
    OWNER_ROLE,
    MEMBER_ROLE,
})


def is_supported_project_role(role: str) -> bool:
    return role in SUPPORTED_PROJECT_ROLES
