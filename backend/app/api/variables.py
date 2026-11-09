import json
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.models import (
    Variable,
    Environment,
    ProjectMember,
    HistoryLog,
    User,
    EnvironmentSnapshot
)
from app.schemas.schemas import (
    VariableCreate,
    VariableUpdate,
    VariableOut,
    ImportParseRequest,
    BulkImportCommitRequest,
    DiffItem
)
from app.api.deps import get_current_user
from app.core.crypto import encrypt_value, decrypt_value
from app.services.parser import parse_raw_env, compute_diff, is_sensitive_key
from app.core.roles import is_supported_project_role

router = APIRouter(
    prefix="/api/environments/{env_id}/variables",
    tags=["Variables"]
)


def verify_env_access(
    env_id: str,
    user_id: str,
    db: Session,
    required_roles: Optional[List[str]] = None
) -> Environment:
    env = db.query(Environment).filter(Environment.id == env_id).first()
    if not env:
        raise HTTPException(status_code=404, detail="Environment not found")

    member = db.query(ProjectMember).filter(
        ProjectMember.project_id == env.project_id,
        ProjectMember.user_id == user_id
    ).first()

    if not member:
        raise HTTPException(status_code=403, detail="Access denied")

    if not is_supported_project_role(member.role):
        raise HTTPException(status_code=403, detail="Unsupported project role")

    if required_roles and member.role not in required_roles:
        raise HTTPException(
            status_code=403,
            detail=f"Operation requires one of the following roles: {', '.join(required_roles)}"
        )

    return env


@router.get("", response_model=List[VariableOut])
def list_variables(
    env_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    verify_env_access(env_id, current_user.id, db)

    variables = db.query(Variable).filter(
        Variable.environment_id == env_id
    ).all()

    results = []
    for v in variables:
        results.append({
            "id": v.id,
            "key": v.key,
            "value": "••••••••" if v.is_sensitive else v.value,
            "is_sensitive": v.is_sensitive,
            "updated_at": v.updated_at
        })

    return results


@router.post("", response_model=VariableOut)
def create_variable(
    env_id: str,
    var_in: VariableCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    env = verify_env_access(env_id, current_user.id, db)

    existing = db.query(Variable).filter(
        Variable.environment_id == env_id,
        Variable.key == var_in.key
    ).first()

    if existing:
        raise HTTPException(
            status_code=400,
            detail="Variable key already exists in this environment"
        )

    # Auto-detect sensitive key if not explicitly flagged
    is_sensitive = var_in.is_sensitive or is_sensitive_key(var_in.key)

    stored_val = var_in.value
    stored_iv = None

    if is_sensitive:
        enc = encrypt_value(var_in.value)
        stored_val = enc["ciphertext"]
        stored_iv = enc["iv"]

    new_var = Variable(
        key=var_in.key,
        value=stored_val,
        iv=stored_iv,
        is_sensitive=is_sensitive,
        environment_id=env_id
    )

    db.add(new_var)

    db.add(HistoryLog(
        action="CREATE",
        key=var_in.key,
        old_value=None,
        new_value="[ENCRYPTED]" if is_sensitive else var_in.value,
        user_id=current_user.id,
        project_id=env.project_id,
        environment_id=env_id
    ))

    db.commit()
    db.refresh(new_var)

    return {
        "id": new_var.id,
        "key": new_var.key,
        "value": "••••••••" if new_var.is_sensitive else new_var.value,
        "is_sensitive": new_var.is_sensitive,
        "updated_at": new_var.updated_at
    }


@router.put("/{var_id}", response_model=VariableOut)
def update_variable(
    env_id: str,
    var_id: str,
    var_in: VariableUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Updates an existing variable with sensitivity and encryption preservation (QUAL-02)."""
    env = verify_env_access(env_id, current_user.id, db)

    var = db.query(Variable).filter(
        Variable.id == var_id,
        Variable.environment_id == env_id
    ).first()

    if not var:
        raise HTTPException(status_code=404, detail="Variable not found")

    old_is_sensitive = var.is_sensitive
    new_is_sensitive = var_in.is_sensitive if var_in.is_sensitive is not None else old_is_sensitive

    # Prevent accidental downgrade of known secret keys
    if old_is_sensitive and var_in.is_sensitive is False:
        raise HTTPException(
            status_code=400,
            detail="Cannot mark known secret keys as non-sensitive"
        )

    if var_in.value is not None:
        new_plain_val = var_in.value
    else:
        new_plain_val = decrypt_value(var.value, var.iv) if old_is_sensitive else var.value

    stored_val = new_plain_val
    stored_iv = None

    if new_is_sensitive:
        enc = encrypt_value(new_plain_val)
        stored_val = enc["ciphertext"]
        stored_iv = enc["iv"]

    var.value = stored_val
    var.iv = stored_iv
    var.is_sensitive = new_is_sensitive

    db.add(HistoryLog(
        action="UPDATE",
        key=var.key,
        old_value="[ENCRYPTED]" if old_is_sensitive else "[REDACTED]",
        new_value="[ENCRYPTED]" if new_is_sensitive else new_plain_val,
        user_id=current_user.id,
        project_id=env.project_id,
        environment_id=env_id
    ))

    db.commit()
    db.refresh(var)

    return {
        "id": var.id,
        "key": var.key,
        "value": "••••••••" if var.is_sensitive else var.value,
        "is_sensitive": var.is_sensitive,
        "updated_at": var.updated_at
    }


@router.post("/{var_id}/reveal")
def reveal_sensitive_variable(
    env_id: str,
    var_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    verify_env_access(env_id, current_user.id, db)

    var = db.query(Variable).filter(
        Variable.id == var_id,
        Variable.environment_id == env_id
    ).first()

    if not var:
        raise HTTPException(status_code=404, detail="Variable not found")

    if not var.is_sensitive:
        return {"key": var.key, "value": var.value}

    decrypted = decrypt_value(var.value, var.iv)

    return {"key": var.key, "value": decrypted}


@router.delete("/{var_id}")
def delete_variable(
    env_id: str,
    var_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    env = verify_env_access(env_id, current_user.id, db)

    var = db.query(Variable).filter(
        Variable.id == var_id,
        Variable.environment_id == env_id
    ).first()

    if not var:
        raise HTTPException(status_code=404, detail="Variable not found")

    db.add(HistoryLog(
        action="DELETE",
        key=var.key,
        old_value="[ENCRYPTED]" if var.is_sensitive else var.value,
        new_value=None,
        user_id=current_user.id,
        project_id=env.project_id,
        environment_id=env_id
    ))

    db.delete(var)
    db.commit()

    return {"message": "Variable deleted"}


@router.post("/parse-diff", response_model=List[DiffItem])
def preview_bulk_diff(
    env_id: str,
    payload: ImportParseRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    verify_env_access(env_id, current_user.id, db)

    try:
        incoming = parse_raw_env(payload.raw_env)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    existing_vars = db.query(Variable).filter(
        Variable.environment_id == env_id
    ).all()

    existing_by_key = {v.key: v for v in existing_vars}
    existing_values = {}

    for var in existing_vars:
        if var.is_sensitive:
            existing_values[var.key] = decrypt_value(var.value, var.iv)
        else:
            existing_values[var.key] = var.value

    diff_results = compute_diff(incoming, existing_values)

    # Never return plaintext values for existing or newly classified sensitive variables (SEC-01)
    safe_results = []
    for item in diff_results:
        existing_var = existing_by_key.get(item["key"])
        is_existing_sensitive = bool(existing_var and existing_var.is_sensitive)
        is_sensitive = is_existing_sensitive or is_sensitive_key(item["key"])

        safe_results.append({
            **item,
            "old_value": "[REDACTED]" if is_sensitive and item["old_value"] is not None else item["old_value"],
            "new_value": "[REDACTED]" if is_sensitive else item["new_value"],
            "is_sensitive": is_sensitive,
            "is_existing_sensitive": is_existing_sensitive
        })

    return safe_results


@router.post("/commit-bulk")
def commit_bulk_import(
    env_id: str,
    payload: BulkImportCommitRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    env = verify_env_access(env_id, current_user.id, db)

    # Parse raw .env on the server, or extract items if sent by legacy client (SEC-02, FUNC-02)
    if payload.raw_env:
        try:
            incoming = parse_raw_env(payload.raw_env)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    elif payload.items:
        incoming = []
        seen = set()
        for item in payload.items:
            if item.key in seen:
                raise HTTPException(status_code=400, detail=f"Duplicate environment variable key: {item.key}")
            seen.add(item.key)
            incoming.append({"key": item.key, "value": item.new_value})
    else:
        raise HTTPException(
            status_code=400,
            detail="The import payload contains no valid variable data"
        )

    if not incoming:
        raise HTTPException(
            status_code=400,
            detail="The imported .env file contains no valid variables"
        )

    existing_vars = db.query(Variable).filter(
        Variable.environment_id == env_id
    ).all()

    existing_by_key = {v.key: v for v in existing_vars}
    existing_values = {}

    for var in existing_vars:
        if var.is_sensitive:
            existing_values[var.key] = decrypt_value(var.value, var.iv)
        else:
            existing_values[var.key] = var.value

    # Recalculate diff on the backend using authoritative database values
    diff_results = compute_diff(incoming, existing_values)

    requested_sensitive_keys = set(payload.sensitive_keys)

    # Automatic safety snapshot before Smart Import
    if existing_vars:
        pre_import_data = [
            {
                "key": v.key,
                "value": v.value,
                "iv": v.iv,
                "is_sensitive": v.is_sensitive
            }
            for v in existing_vars
        ]

        db.add(EnvironmentSnapshot(
            environment_id=env_id,
            created_by_id=current_user.id,
            name=f"Auto-backup before Smart Import ({len(existing_vars)} vars)",
            variables_data=json.dumps(pre_import_data)
        ))
        db.flush()

    for item in diff_results:
        key = item["key"]
        new_value = item["new_value"]
        var = existing_by_key.get(key)

        # Sensitive status cannot be downgraded if previously sensitive or matching secret keywords
        new_is_sensitive = (
            key in requested_sensitive_keys
            or bool(var and var.is_sensitive)
            or is_sensitive_key(key)
        )

        if item["status"] == "UNCHANGED":
            # If an existing non-sensitive variable is newly classified as sensitive, encrypt it safely
            if new_is_sensitive and var and not var.is_sensitive:
                raw_val = existing_values.get(key, var.value)
                encrypted_existing = encrypt_value(raw_val)
                var.value = encrypted_existing["ciphertext"]
                var.iv = encrypted_existing["iv"]
                var.is_sensitive = True

                db.add(HistoryLog(
                    action="UPDATE",
                    key=key,
                    old_value="[REDACTED]",
                    new_value="[ENCRYPTED]",
                    user_id=current_user.id,
                    project_id=env.project_id,
                    environment_id=env_id
                ))
            continue

        stored_value = new_value
        stored_iv = None

        if new_is_sensitive:
            encrypted = encrypt_value(new_value)
            stored_value = encrypted["ciphertext"]
            stored_iv = encrypted["iv"]

        if item["status"] == "NEW":
            new_var = Variable(
                key=key,
                value=stored_value,
                iv=stored_iv,
                is_sensitive=new_is_sensitive,
                environment_id=env_id
            )
            db.add(new_var)

            db.add(HistoryLog(
                action="CREATE",
                key=key,
                old_value=None,
                new_value="[ENCRYPTED]" if new_is_sensitive else new_value,
                user_id=current_user.id,
                project_id=env.project_id,
                environment_id=env_id
            ))

        elif item["status"] == "UPDATE" and var:
            old_is_sensitive = var.is_sensitive

            var.value = stored_value
            var.iv = stored_iv
            var.is_sensitive = new_is_sensitive

            db.add(HistoryLog(
                action="UPDATE",
                key=key,
                old_value="[ENCRYPTED]" if (old_is_sensitive or new_is_sensitive) else existing_values.get(key, "[REDACTED]"),
                new_value="[ENCRYPTED]" if new_is_sensitive else new_value,
                user_id=current_user.id,
                project_id=env.project_id,
                environment_id=env_id
            ))

    db.commit()

    return {"message": "Bulk import applied successfully"}
