import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.rate_limit import auth_rate_limiter
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_password_reset_token,
    verify_password_reset_token,
    hash_token,
    RESET_TOKEN_EXPIRE_MINUTES,
)
from app.models.models import User
from app.schemas.schemas import (
    UserRegister,
    UserLogin,
    TokenResponse,
    UserOut,
    ForgotPasswordRequest,
    ResetPasswordRequest,
)
from app.api.deps import get_current_user
from app.services.email import send_password_reset_email

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["Auth"])

@router.post("/register", response_model=TokenResponse)
def register(request: Request, user_in: UserRegister, db: Session = Depends(get_db)):
    auth_rate_limiter.check(request)

    # Normalize email to prevent casing and trailing space mismatches
    normalized_email = user_in.email.strip().lower()

    existing = db.query(User).filter(User.email == normalized_email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    pwd_hash = hash_password(user_in.password)
    new_user = User(
        name=user_in.name.strip(),
        email=normalized_email,
        password_hash=pwd_hash,
        token_version=1
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    token = create_access_token({
        "sub": new_user.id,
        "email": new_user.email,
        "token_version": new_user.token_version
    })
    return {"access_token": token, "token_type": "bearer", "user": new_user}

@router.post("/login", response_model=TokenResponse)
def login(request: Request, login_in: UserLogin, db: Session = Depends(get_db)):
    auth_rate_limiter.check(request)

    # Normalize email on login as well
    normalized_email = login_in.email.strip().lower()

    user = db.query(User).filter(User.email == normalized_email).first()
    if not user or not verify_password(login_in.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    token = create_access_token({
        "sub": user.id,
        "email": user.email,
        "token_version": user.token_version
    })
    return {"access_token": token, "token_type": "bearer", "user": user}

@router.get("/me", response_model=UserOut)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user

@router.post("/forgot-password")
def forgot_password(request: Request, payload: ForgotPasswordRequest, db: Session = Depends(get_db)):
    auth_rate_limiter.check(request)

    normalized_email = payload.email.strip().lower()
    user = db.query(User).filter(User.email == normalized_email).first()
    
    # Issue reset token only if user exists
    if user:
        raw_token = create_password_reset_token(user.email)
        token_hash = hash_token(raw_token)
        from datetime import timedelta
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=RESET_TOKEN_EXPIRE_MINUTES)

        # Invalidate any previous outstanding token by overwriting with newest hash
        user.reset_token_hash = token_hash
        user.reset_token_expires_at = expires_at
        db.commit()

        try:
            send_password_reset_email(user.email, raw_token)
        except Exception as e:
            # Log error without passwords, reset tokens, or secrets (AUTH-03)
            logger.error("Failed to send password reset email: %s", type(e).__name__)

    # Generic response prevents account enumeration even when email fails (AUTH-03)
    return {"message": "If an account matches that email, a password reset link has been sent."}

@router.post("/reset-password")
def reset_password(request: Request, payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    auth_rate_limiter.check(request)

    token_data = verify_password_reset_token(payload.token)
    if not token_data or "sub" not in token_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset token is invalid or has expired."
        )

    incoming_hash = hash_token(payload.token)
    now = datetime.now(timezone.utc)

    # Atomic consumption of the token: check hash + unexpired, update password,
    # increment token_version (invalidating active sessions), and clear reset token (AUTH-01, CONFIG-04)
    updated_count = db.query(User).filter(
        User.reset_token_hash == incoming_hash,
        User.reset_token_expires_at > now
    ).update({
        User.password_hash: hash_password(payload.new_password),
        User.token_version: User.token_version + 1,
        User.reset_token_hash: None,
        User.reset_token_expires_at: None
    }, synchronize_session=False)

    db.commit()

    if updated_count == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset token is invalid, expired, or has already been used."
        )

    return {"message": "Password updated successfully. You can now log in with your new credentials."}
