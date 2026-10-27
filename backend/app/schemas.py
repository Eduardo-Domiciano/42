from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field, HttpUrl


class IngestUrlRequest(BaseModel):
    url: HttpUrl
    refresh: bool = False
    themes: list[str] = Field(default_factory=list)


class IngestTextRequest(BaseModel):
    text: str = Field(min_length=80, max_length=100_000)
    title: str | None = Field(default=None, max_length=400)
    published_at: date | None = None
    themes: list[str] = Field(default_factory=list)


class TopicSearchRequest(BaseModel):
    topic: str = Field(min_length=2, max_length=300)
    date_from: date | None = None
    date_to: date | None = None
    on_date: date | None = None
    themes: list[str] = Field(default_factory=list)


class OutboundLinkOut(BaseModel):
    id: int
    url: str
    anchor_text: str | None = None


class SourceOut(BaseModel):
    id: int
    slug: str
    name: str
    domain: str | None
    kind: str | None
    authority_tier: str | None
    authority_score: float | None
    ownership_group: str | None
    ownership_name: str | None = None
    bias_score: float | None = None
    bias_label: str | None = None
    bias_note: str | None = None
    bias_catalog_version: str | None = None
    country: str

    model_config = {"from_attributes": True}


class ClaimOut(BaseModel):
    id: int
    canonical_text: str
    checkability: str
    entities: list[str] = Field(default_factory=list)
    time_scope: str | None = None
    place_scope: str | None = None


class ClaimAssessmentOut(BaseModel):
    id: int
    method: str
    verdict: str
    confidence: float
    justification: str | None
    score_temporal: float
    score_geographic: float
    score_partisan: float
    score_distortion: float
    score_internal_support: float
    factors: list[str] = Field(default_factory=list)
    excerpts: list[str] = Field(default_factory=list)
    claim: ClaimOut


class EvidenceItemOut(BaseModel):
    id: int
    stance: str
    weight: float
    stance_confidence: float
    method: str
    same_ownership: bool
    note: str | None
    article_id: int
    article_title: str | None
    article_url: str
    source: SourceOut | None = None
    ownership_name: str | None = None


class CrossReferenceOut(BaseModel):
    claim_id: int
    claim_text: str
    isolated_verdict: str
    consensus_verdict: str
    calibration_score: float
    primary_veto: bool
    independent_voices: int
    factors: list[str] = Field(default_factory=list)
    evidences: list[EvidenceItemOut] = Field(default_factory=list)


class ArticleAnalysisOut(BaseModel):
    content_type_guess: str
    content_type_confidence: float = 0.0
    authority_tier: str | None
    bias_label: str | None = None
    bias_score: float | None = None
    bias_catalog_version: str | None = None
    ownership_name: str | None = None
    source_partiality_note: str
    temporal_coherence: str
    preliminary_verdict: str
    analysis_method: str = "heuristic"
    factors: list[str]


class BcbComparisonOut(BaseModel):
    claim_id: int = 0
    claim_text: str = ""
    indicator_slug: str
    indicator_name: str
    series_code: int = 0
    year: int
    claimed_value: float | None = None
    official_value: float | None = None
    official_date: str | None = None
    status: str
    note: str = ""
    from_cache: bool = True


class ArticleOut(BaseModel):
    id: int
    url: str
    title: str | None
    author: str | None
    excerpt: str | None
    body_preview: str | None = None
    published_at: datetime | None
    content_type: str
    source: SourceOut | None = None
    analysis: ArticleAnalysisOut | None = None
    claims: list[ClaimAssessmentOut] = Field(default_factory=list)
    cross_references: list[CrossReferenceOut] = Field(default_factory=list)
    narrative_summary: str = ""
    analysis_cached: bool = False
    outbound_links: list[OutboundLinkOut] = Field(default_factory=list)
    bcb_comparisons: list[BcbComparisonOut] = Field(default_factory=list)
    analysis_themes: list[str] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class TopicPanoramaOut(BaseModel):
    total_articles: int
    distinct_sources: int
    distinct_ownerships: int = 0
    authority_tiers: dict[str, int]
    bias_labels: dict[str, int] = Field(default_factory=dict)
    content_types: dict[str, int] = Field(default_factory=dict)
    claim_verdicts: dict[str, int] = Field(default_factory=dict)
    consensus_verdicts: dict[str, int] = Field(default_factory=dict)
    total_claims: int = 0
    total_cross_refs: int = 0
    avg_calibration: float | None = None
    candidates_considered: int = 0
    discarded_relevance: int = 0
    discarded_date: int = 0
    notes: list[str]


class TopicQueryOut(BaseModel):
    id: int
    topic_text: str
    date_from: date | None
    date_to: date | None
    status: str
    summary: str | None
    created_at: datetime
    articles: list[ArticleOut]
    panorama: TopicPanoramaOut | None = None
    narrative_summary: str = ""

    model_config = {"from_attributes": True}
