from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    domain: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    kind: Mapped[str | None] = mapped_column(String(80), nullable=True)
    authority_tier: Mapped[str | None] = mapped_column(String(40), nullable=True)
    authority_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    ownership_group: Mapped[str | None] = mapped_column(String(120), nullable=True)
    ownership_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    bias_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    bias_label: Mapped[str | None] = mapped_column(String(40), nullable=True)
    bias_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    bias_catalog_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    country: Mapped[str] = mapped_column(String(8), default="BR")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    articles: Mapped[list[Article]] = relationship(back_populates="source")


class Article(Base):
    __tablename__ = "articles"
    __table_args__ = (
        UniqueConstraint("normalized_url", name="uq_articles_normalized_url"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int | None] = mapped_column(ForeignKey("sources.id"), nullable=True)
    url: Mapped[str] = mapped_column(Text)
    normalized_url: Mapped[str] = mapped_column(String(512), index=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    author: Mapped[str | None] = mapped_column(String(255), nullable=True)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, index=True
    )
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    content_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    content_type: Mapped[str] = mapped_column(String(40), default="article")
    excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)

    source: Mapped[Source | None] = relationship(back_populates="articles")
    query_links: Mapped[list[QueryArticle]] = relationship(back_populates="article")
    claim_links: Mapped[list[ArticleClaim]] = relationship(back_populates="article")
    assessments: Mapped[list[ClaimAssessment]] = relationship(back_populates="article")
    analyses: Mapped[list[ArticleAnalysis]] = relationship(back_populates="article")
    outbound_links: Mapped[list[ArticleOutboundLink]] = relationship(
        back_populates="article"
    )


class ArticleAnalysis(Base):
    """Snapshot vigente da análise agregada (reuso sem recalcular)."""

    __tablename__ = "article_analyses"
    __table_args__ = (
        UniqueConstraint(
            "article_id", "content_hash", name="uq_article_analysis_hash"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id"), index=True)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    preliminary_verdict: Mapped[str] = mapped_column(String(40), default="insufficient")
    analysis_method: Mapped[str] = mapped_column(String(40), default="heuristic")
    temporal_coherence: Mapped[str] = mapped_column(Text, default="")
    source_partiality_note: Mapped[str] = mapped_column(Text, default="")
    factors_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    narrative_summary: Mapped[str] = mapped_column(Text, default="")
    ownership_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    bias_label: Mapped[str | None] = mapped_column(String(40), nullable=True)
    bias_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    bias_catalog_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    authority_tier: Mapped[str | None] = mapped_column(String(40), nullable=True)
    content_type_guess: Mapped[str] = mapped_column(String(40), default="article")
    content_type_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    author: Mapped[str | None] = mapped_column(String(255), nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str] = mapped_column(Text, default="")
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    config_note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    article: Mapped[Article] = relationship(back_populates="analyses")


class ArticleOutboundLink(Base):
    """Links citados no HTML/corpo do artigo."""

    __tablename__ = "article_outbound_links"
    __table_args__ = (
        UniqueConstraint("article_id", "url", name="uq_article_outbound_url"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id"), index=True)
    url: Mapped[str] = mapped_column(Text)
    anchor_text: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    article: Mapped[Article] = relationship(back_populates="outbound_links")


class Claim(Base):
    __tablename__ = "claims"
    __table_args__ = (UniqueConstraint("fingerprint", name="uq_claims_fingerprint"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    canonical_text: Mapped[str] = mapped_column(Text)
    fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    checkability: Mapped[str] = mapped_column(String(40), default="unclear")
    entities_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    time_scope: Mapped[str | None] = mapped_column(String(255), nullable=True)
    place_scope: Mapped[str | None] = mapped_column(String(255), nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    article_links: Mapped[list[ArticleClaim]] = relationship(back_populates="claim")
    assessments: Mapped[list[ClaimAssessment]] = relationship(back_populates="claim")


class ArticleClaim(Base):
    __tablename__ = "article_claims"
    __table_args__ = (
        UniqueConstraint("article_id", "claim_id", name="uq_article_claim"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id"))
    claim_id: Mapped[int] = mapped_column(ForeignKey("claims.id"))

    article: Mapped[Article] = relationship(back_populates="claim_links")
    claim: Mapped[Claim] = relationship(back_populates="article_links")


class ClaimAssessment(Base):
    __tablename__ = "claim_assessments"
    __table_args__ = (
        UniqueConstraint(
            "article_id", "claim_id", name="uq_claim_assessment_article_claim"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    claim_id: Mapped[int] = mapped_column(ForeignKey("claims.id"), index=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id"), index=True)
    method: Mapped[str] = mapped_column(String(40), default="heuristic")
    score_temporal: Mapped[float] = mapped_column(Float, default=0.0)
    score_geographic: Mapped[float] = mapped_column(Float, default=0.0)
    score_partisan: Mapped[float] = mapped_column(Float, default=0.0)
    score_distortion: Mapped[float] = mapped_column(Float, default=0.0)
    score_internal_support: Mapped[float] = mapped_column(Float, default=0.0)
    verdict: Mapped[str] = mapped_column(String(40), default="insufficient")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    justification: Mapped[str | None] = mapped_column(Text, nullable=True)
    factors_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    excerpts_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    claim: Mapped[Claim] = relationship(back_populates="assessments")
    article: Mapped[Article] = relationship(back_populates="assessments")


class EvidenceItem(Base):
    __tablename__ = "evidence_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    claim_id: Mapped[int] = mapped_column(ForeignKey("claims.id"), index=True)
    root_article_id: Mapped[int] = mapped_column(ForeignKey("articles.id"), index=True)
    evidence_article_id: Mapped[int] = mapped_column(ForeignKey("articles.id"), index=True)
    stance: Mapped[str] = mapped_column(String(40), default="related")
    weight: Mapped[float] = mapped_column(Float, default=0.0)
    stance_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    method: Mapped[str] = mapped_column(String(40), default="heuristic")
    same_ownership: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CrossReference(Base):
    __tablename__ = "cross_references"
    __table_args__ = (
        UniqueConstraint(
            "root_article_id", "claim_id", name="uq_cross_ref_root_claim"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    root_article_id: Mapped[int] = mapped_column(ForeignKey("articles.id"), index=True)
    claim_id: Mapped[int] = mapped_column(ForeignKey("claims.id"), index=True)
    isolated_verdict: Mapped[str] = mapped_column(String(40), default="insufficient")
    consensus_verdict: Mapped[str] = mapped_column(String(40), default="insufficient")
    calibration_score: Mapped[float] = mapped_column(Float, default=0.0)
    primary_veto: Mapped[bool] = mapped_column(Boolean, default=False)
    independent_voices: Mapped[int] = mapped_column(Integer, default=0)
    factors_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TopicQuery(Base):
    __tablename__ = "topic_queries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    topic_text: Mapped[str] = mapped_column(Text)
    date_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    date_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="pending")
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    articles: Mapped[list[QueryArticle]] = relationship(back_populates="topic_query")


class QueryArticle(Base):
    __tablename__ = "query_articles"
    __table_args__ = (
        UniqueConstraint("topic_query_id", "article_id", name="uq_query_article"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    topic_query_id: Mapped[int] = mapped_column(ForeignKey("topic_queries.id"))
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id"))
    rank: Mapped[int] = mapped_column(Integer, default=0)
    discovery_method: Mapped[str] = mapped_column(String(40), default="web")

    topic_query: Mapped[TopicQuery] = relationship(back_populates="articles")
    article: Mapped[Article] = relationship(back_populates="query_links")
