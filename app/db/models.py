from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    license_number: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    business_name: Mapped[str] = mapped_column(String(512))
    business_type: Mapped[str | None] = mapped_column(String(128))
    address: Mapped[str | None] = mapped_column(String(512))
    city: Mapped[str | None] = mapped_column(String(128))
    state: Mapped[str | None] = mapped_column(String(8))
    zip_code: Mapped[str | None] = mapped_column(String(16))
    county: Mapped[str | None] = mapped_column(String(64), index=True)
    phone_raw: Mapped[str | None] = mapped_column(String(64))
    phone_e164: Mapped[str | None] = mapped_column(String(32), index=True)
    phone_type: Mapped[str | None] = mapped_column(String(32))
    domain: Mapped[str | None] = mapped_column(String(255), index=True)
    website_url: Mapped[str | None] = mapped_column(String(512))
    classifications: Mapped[str | None] = mapped_column(String(128))
    license_status: Mapped[str | None] = mapped_column(String(64))
    issue_date: Mapped[str | None] = mapped_column(String(32))
    expiration_date: Mapped[str | None] = mapped_column(String(32))
    years_in_business: Mapped[float | None] = mapped_column(Float)
    source_url: Mapped[str] = mapped_column(String(512))
    sourced_at: Mapped[str] = mapped_column(String(32))
    merge_cluster_id: Mapped[int | None] = mapped_column(Integer, index=True)
    is_primary_in_cluster: Mapped[bool] = mapped_column(Boolean, default=True)
    pipeline_stage: Mapped[str | None] = mapped_column(String(64))
    excluded_reason: Mapped[str | None] = mapped_column(String(256))
    suppressed: Mapped[bool] = mapped_column(Boolean, default=False)
    suppression_reason: Mapped[str | None] = mapped_column(String(256))
    owner_name: Mapped[str | None] = mapped_column(String(256))
    owner_status: Mapped[str | None] = mapped_column(String(32))
    owner_evidence: Mapped[str | None] = mapped_column(Text)
    mock_site_slug: Mapped[str | None] = mapped_column(String(128))
    synthetic: Mapped[bool] = mapped_column(Boolean, default=False)

    people: Mapped[list["Person"]] = relationship(back_populates="company")
    contacts: Mapped[list["Contact"]] = relationship(back_populates="company")
    facts: Mapped[list["Fact"]] = relationship(back_populates="company")
    signals: Mapped[list["Signal"]] = relationship(back_populates="company")
    scores: Mapped[list["Score"]] = relationship(back_populates="company")
    drafts: Mapped[list["Draft"]] = relationship(back_populates="company")


class Person(Base):
    __tablename__ = "people"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    name: Mapped[str] = mapped_column(String(256))
    title: Mapped[str | None] = mapped_column(String(128))
    source_url: Mapped[str] = mapped_column(String(512))
    sourced_at: Mapped[str] = mapped_column(String(32))

    company: Mapped[Company] = relationship(back_populates="people")


class Contact(Base):
    __tablename__ = "contacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    contact_type: Mapped[str] = mapped_column(String(16))
    value: Mapped[str] = mapped_column(String(256), index=True)
    status: Mapped[str] = mapped_column(String(32), default="unknown")
    is_guessed: Mapped[bool] = mapped_column(Boolean, default=False)
    is_role_based: Mapped[bool] = mapped_column(Boolean, default=False)
    verifier: Mapped[str | None] = mapped_column(String(64))
    verified_at: Mapped[str | None] = mapped_column(String(32))
    source_url: Mapped[str] = mapped_column(String(512))
    sourced_at: Mapped[str] = mapped_column(String(32))

    company: Mapped[Company] = relationship(back_populates="contacts")


class Fact(Base):
    __tablename__ = "facts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    kind: Mapped[str] = mapped_column(String(64), index=True)
    value: Mapped[str] = mapped_column(Text)
    evidence_url: Mapped[str] = mapped_column(String(512))
    snippet: Mapped[str] = mapped_column(Text)
    observed_at: Mapped[str] = mapped_column(String(32))

    company: Mapped[Company] = relationship(back_populates="facts")


class Signal(Base):
    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    kind: Mapped[str] = mapped_column(String(64))
    strength: Mapped[float] = mapped_column(Float, default=1.0)
    detail: Mapped[str | None] = mapped_column(Text)
    evidence_url: Mapped[str | None] = mapped_column(String(512))
    observed_at: Mapped[str] = mapped_column(String(32))
    decays_at: Mapped[str | None] = mapped_column(String(32))

    company: Mapped[Company] = relationship(back_populates="signals")


class Score(Base):
    __tablename__ = "scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    icp_version: Mapped[str] = mapped_column(String(64))
    score: Mapped[int] = mapped_column(Integer)
    tier: Mapped[str] = mapped_column(String(16), index=True)
    reasons_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    created_at: Mapped[str] = mapped_column(String(32))

    company: Mapped[Company] = relationship(back_populates="scores")


class Draft(Base):
    __tablename__ = "drafts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    first_line: Mapped[str] = mapped_column(Text)
    snippet: Mapped[str | None] = mapped_column(Text)
    fact_id: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), default="pending")

    company: Mapped[Company] = relationship(back_populates="drafts")


class Suppression(Base):
    __tablename__ = "suppressions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(32))
    value: Mapped[str] = mapped_column(String(256), index=True)
    reason: Mapped[str | None] = mapped_column(String(256))
    sourced_at: Mapped[str] = mapped_column(String(32))


class MergeCluster(Base):
    __tablename__ = "merge_clusters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_keys: Mapped[dict[str, Any]] = mapped_column(JSON)
    company_ids: Mapped[list[int]] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String(32))


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    started_at: Mapped[str] = mapped_column(String(32))
    finished_at: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32))
    funnel_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    stats_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class SyncLog(Base):
    __tablename__ = "sync_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    destination: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32))
    detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(32))
