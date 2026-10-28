import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from app.core.database import Base

def generate_uuid() -> str:
    return str(uuid.uuid4())

class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=generate_uuid)
    email = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    memberships = relationship("ProjectMember", back_populates="user", cascade="all, delete-orphan")
    history_logs = relationship("HistoryLog", back_populates="user")

class Project(Base):
    __tablename__ = "projects"

    id = Column(String, primary_key=True, default=generate_uuid)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    members = relationship("ProjectMember", back_populates="project", cascade="all, delete-orphan")
    environments = relationship("Environment", back_populates="project", cascade="all, delete-orphan")
    history_logs = relationship("HistoryLog", back_populates="project", cascade="all, delete-orphan")

class ProjectMember(Base):
    __tablename__ = "project_members"

    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    project_id = Column(String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    role = Column(String, default="MEMBER")  # OWNER, MEMBER

    user = relationship("User", back_populates="memberships")
    project = relationship("Project", back_populates="members")

    __table_args__ = (UniqueConstraint("user_id", "project_id", name="uq_user_project"),)

class Environment(Base):
    __tablename__ = "environments"

    id = Column(String, primary_key=True, default=generate_uuid)
    name = Column(String, nullable=False)  # "Development", "Staging", "Production"
    project_id = Column(String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    project = relationship("Project", back_populates="environments")
    variables = relationship("Variable", back_populates="environment", cascade="all, delete-orphan")
    history_logs = relationship("HistoryLog", back_populates="environment", cascade="all, delete-orphan")

    __table_args__ = (UniqueConstraint("project_id", "name", name="uq_project_env_name"),)

class Variable(Base):
    __tablename__ = "variables"

    id = Column(String, primary_key=True, default=generate_uuid)
    key = Column(String, nullable=False)
    value = Column(String, nullable=False)
    iv = Column(String, nullable=True)
    is_sensitive = Column(Boolean, default=False)
    environment_id = Column(String, ForeignKey("environments.id", ondelete="CASCADE"), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    environment = relationship("Environment", back_populates="variables")

    __table_args__ = (UniqueConstraint("environment_id", "key", name="uq_env_var_key"),)

class HistoryLog(Base):
    __tablename__ = "history_logs"

    id = Column(String, primary_key=True, default=generate_uuid)
    action = Column(String, nullable=False)  # CREATE, UPDATE, DELETE, BULK_IMPORT
    key = Column(String, nullable=True)
    old_value = Column(String, nullable=True)
    new_value = Column(String, nullable=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    project_id = Column(String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    environment_id = Column(String, ForeignKey("environments.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="history_logs")
    project = relationship("Project", back_populates="history_logs")
    environment = relationship("Environment", back_populates="history_logs")