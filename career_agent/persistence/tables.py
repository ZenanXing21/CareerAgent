"""Persistence-only SQLAlchemy mappings."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class JobRow(Base):
    __tablename__ = "jobs"
    __table_args__ = (UniqueConstraint("platform", "external_job_id"),)

    id: Mapped[str] = mapped_column(String(200), primary_key=True)
    platform: Mapped[str] = mapped_column(String(100), nullable=False)
    external_job_id: Mapped[str] = mapped_column(String(200), nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ApplicationRow(Base):
    __tablename__ = "applications"

    job_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    platform: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    match_score: Mapped[float | None] = mapped_column(Float)
    resume_version: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ResumeVersionRow(Base):
    __tablename__ = "resume_versions"
    __table_args__ = (UniqueConstraint("resume_id", "version", "target_job_id"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    resume_id: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[str] = mapped_column(String(200), nullable=False)
    target_job_id: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    validation_passed: Mapped[bool] = mapped_column(nullable=False)
    approved: Mapped[bool] = mapped_column(nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
