from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from app.core.database import get_db
from app.models.models import Variable, Environment, ProjectMember, HistoryLog, User
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
from app.services.parser import parse_raw_env, compute_diff

router = APIRouter(prefix="/api/environments/{env_id}/variables", tags=["Variables"])

def verify_env_access(env_id: str, user_id: str, db: Session) -> Environment:
    env = db.query(Environment).filter(Environment.id == env_id).first()
    if not env:
        raise HTTPException(status_code=404, detail="Environment not found")
    
    member = db.query(ProjectMember).filter(
        ProjectMember.project_id == env.project_id,
        ProjectMember.user_id == user_id
    ).first()
    
    if not member:
        raise HTTPException(status_code=403, detail="Access denied")
    return env

@router.get("", response_model=List[VariableOut])
def list_variables(
    env_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    verify_env_access(env_id, current_user.id, db)
    variables = db.query(Variable).filter(Variable.environment_id == env_id).all()
    
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
        raise HTTPException(status_code=400, detail="Variable key already exists in this environment")

    stored_val = var_in.value
    stored_iv = None
    if var_in.is_sensitive:
        enc = encrypt_value(var_in.value)
        stored_val = enc["ciphertext"]
        stored_iv = enc["iv"]

    new_var = Variable(
        key=var_in.key,
        value=stored_val,
        iv=stored_iv,
        is_sensitive=var_in.is_sensitive,
        environment_id=env_id
    )
    db.add(new_var)

    db.add(HistoryLog(
        action="CREATE",
        key=var_in.key,
        old_value=None,
        new_value="[ENCRYPTED]" if var_in.is_sensitive else var_in.value,
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

@router.post("/{var_id}/reveal")
def reveal_sensitive_variable(
    env_id: str,
    var_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    verify_env_access(env_id, current_user.id, db)
    var = db.query(Variable).filter(Variable.id == var_id, Variable.environment_id == env_id).first()
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
    var = db.query(Variable).filter(Variable.id == var_id, Variable.environment_id == env_id).first()
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
    incoming = parse_raw_env(payload.raw_env)
    
    existing_vars = db.query(Variable).filter(Variable.environment_id == env_id).all()
    existing_dict = {}
    for v in existing_vars:
        if v.is_sensitive:
            existing_dict[v.key] = decrypt_value(v.value, v.iv)
        else:
            existing_dict[v.key] = v.value

    return compute_diff(incoming, existing_dict)

@router.post("/commit-bulk")
def commit_bulk_import(
    env_id: str,
    payload: BulkImportCommitRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    env = verify_env_access(env_id, current_user.id, db)

    for item in payload.items:
        if item.status == "UNCHANGED":
            continue

        var = db.query(Variable).filter(
            Variable.environment_id == env_id,
            Variable.key == item.key
        ).first()

        stored_val = item.new_value
        stored_iv = None
        if item.is_sensitive:
            enc = encrypt_value(item.new_value)
            stored_val = enc["ciphertext"]
            stored_iv = enc["iv"]

        if item.status == "NEW":
            new_v = Variable(
                key=item.key,
                value=stored_val,
                iv=stored_iv,
                is_sensitive=item.is_sensitive,
                environment_id=env_id
            )
            db.add(new_v)
            db.add(HistoryLog(
                action="CREATE",
                key=item.key,
                old_value=None,
                new_value="[ENCRYPTED]" if item.is_sensitive else item.new_value,
                user_id=current_user.id,
                project_id=env.project_id,
                environment_id=env_id
            ))
        elif item.status == "UPDATE" and var:
            var.value = stored_val
            var.iv = stored_iv
            var.is_sensitive = item.is_sensitive
            db.add(HistoryLog(
                action="UPDATE",
                key=item.key,
                old_value="[ENCRYPTED]" if item.is_sensitive else item.old_value,
                new_value="[ENCRYPTED]" if item.is_sensitive else item.new_value,
                user_id=current_user.id,
                project_id=env.project_id,
                environment_id=env_id
            ))

    db.commit()
    return {"message": "Bulk import applied successfully"}