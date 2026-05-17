import json
from datetime import datetime
from contextlib import asynccontextmanager
from sqlalchemy import (
    Column, Integer, String, Text, DateTime,
    Boolean, BigInteger, JSON, ForeignKey, Index,
)
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, relationship
from config import DATABASE_URL

_url = DATABASE_URL
if _url.startswith("postgresql://"):
    _url = _url.replace("postgresql://", "postgresql+asyncpg://", 1)
elif _url.startswith("postgres://"):
    _url = _url.replace("postgres://", "postgresql+asyncpg://", 1)

# Strip sslmode from query string — asyncpg uses connect_args instead
import re as _re
_url = _re.sub(r"[?&]sslmode=[^&]*", "", _url)

engine = create_async_engine(
    _url,
    echo=False,
    pool_pre_ping=True,
)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    project_name = Column(String(255), nullable=True, default="default")
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    message_type = Column(String(50), default="text")
    metadata_ = Column("metadata", JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (Index("ix_messages_user_project", "user_id", "project_name"),)


class Project(Base):
    __tablename__ = "projects"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, default="")
    language = Column(String(50), default="python")
    github_repo = Column(String(500), nullable=True)
    local_path = Column(String(1000), nullable=True)
    is_active = Column(Boolean, default=True)
    metadata_ = Column("metadata", JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    __table_args__ = (Index("ix_projects_user_name", "user_id", "name"),)


class Memory(Base):
    __tablename__ = "memories"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    content = Column(Text, nullable=False)
    memory_type = Column(String(50), default="general")
    importance = Column(Integer, default=5)
    tags = Column(JSON, default=list)
    created_at = Column(DateTime, default=datetime.utcnow)


class UserSettings(Base):
    __tablename__ = "user_settings"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, unique=True, nullable=False, index=True)
    username = Column(String(255), nullable=True)
    preferred_language = Column(String(50), default="python")
    preferred_model_tier = Column(String(20), default="balanced")
    active_project = Column(String(255), default="default")
    coding_style = Column(Text, default="")
    notifications = Column(Boolean, default=True)
    webapp_theme = Column(String(20), default="dark")
    settings = Column(JSON, default=dict)
    total_messages = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


@asynccontextmanager
async def get_session():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_chat_history(user_id: int, project: str = "default", limit: int = 50) -> list[dict]:
    async with get_session() as session:
        from sqlalchemy import select
        result = await session.execute(
            select(Message)
            .where(Message.user_id == user_id, Message.project_name == project)
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        messages = result.scalars().all()
        return [
            {"role": m.role, "content": m.content}
            for m in reversed(messages)
        ]


async def save_message(user_id: int, role: str, content: str,
                       project: str = "default", msg_type: str = "text",
                       metadata: dict = None):
    async with get_session() as session:
        msg = Message(
            user_id=user_id, project_name=project,
            role=role, content=content,
            message_type=msg_type, metadata_=metadata or {},
        )
        session.add(msg)


async def get_or_create_settings(user_id: int, username: str = "") -> UserSettings:
    async with get_session() as session:
        from sqlalchemy import select
        result = await session.execute(
            select(UserSettings).where(UserSettings.user_id == user_id)
        )
        settings = result.scalar_one_or_none()
        if not settings:
            settings = UserSettings(user_id=user_id, username=username)
            session.add(settings)
        return settings


async def get_user_projects(user_id: int) -> list[Project]:
    async with get_session() as session:
        from sqlalchemy import select
        result = await session.execute(
            select(Project)
            .where(Project.user_id == user_id, Project.is_active == True)
            .order_by(Project.updated_at.desc())
        )
        return result.scalars().all()
