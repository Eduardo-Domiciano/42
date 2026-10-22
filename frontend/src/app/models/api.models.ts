export interface SourceOut {
  id: number;
  slug: string;
  name: string;
  domain: string | null;
  kind: string | null;
  authority_tier: string | null;
  authority_score: number | null;
  ownership_group: string | null;
  ownership_name: string | null;
  bias_score: number | null;
  bias_label: string | null;
  bias_note: string | null;
  bias_catalog_version: string | null;
  country: string;
}

export interface ClaimOut {
  id: number;
  canonical_text: string;
  checkability: string;
  entities: string[];
  time_scope: string | null;
  place_scope: string | null;
}

export interface ClaimAssessmentOut {
  id: number;
  method: string;
  verdict: string;
  confidence: number;
  justification: string | null;
  score_temporal: number;
  score_geographic: number;
  score_partisan: number;
  score_distortion: number;
  score_internal_support: number;
  factors: string[];
  excerpts: string[];
  claim: ClaimOut;
}

export interface EvidenceItemOut {
  id: number;
  stance: string;
  weight: number;
  stance_confidence: number;
  method: string;
  same_ownership: boolean;
  note: string | null;
  article_id: number;
  article_title: string | null;
  article_url: string;
  source: SourceOut | null;
  ownership_name: string | null;
}

export interface CrossReferenceOut {
  claim_id: number;
  claim_text: string;
  isolated_verdict: string;
  consensus_verdict: string;
  calibration_score: number;
  primary_veto: boolean;
  independent_voices: number;
  factors: string[];
  evidences: EvidenceItemOut[];
}

export interface ArticleAnalysisOut {
  content_type_guess: string;
  content_type_confidence: number;
  authority_tier: string | null;
  bias_label: string | null;
  bias_score: number | null;
  bias_catalog_version: string | null;
  ownership_name: string | null;
  source_partiality_note: string;
  temporal_coherence: string;
  preliminary_verdict: string;
  analysis_method: string;
  factors: string[];
}

export interface OutboundLinkOut {
  id: number;
  url: string;
  anchor_text: string | null;
}

export interface ArticleOut {
  id: number;
  url: string;
  title: string | null;
  author: string | null;
  excerpt: string | null;
  body_preview: string | null;
  published_at: string | null;
  content_type: string;
  source: SourceOut | null;
  analysis: ArticleAnalysisOut | null;
  claims: ClaimAssessmentOut[];
  cross_references: CrossReferenceOut[];
  narrative_summary: string;
  analysis_cached?: boolean;
  outbound_links?: OutboundLinkOut[];
}

export interface TopicPanoramaOut {
  total_articles: number;
  distinct_sources: number;
  distinct_ownerships: number;
  authority_tiers: Record<string, number>;
  bias_labels: Record<string, number>;
  content_types: Record<string, number>;
  claim_verdicts: Record<string, number>;
  consensus_verdicts: Record<string, number>;
  total_claims: number;
  total_cross_refs: number;
  avg_calibration: number | null;
  candidates_considered?: number;
  discarded_relevance?: number;
  discarded_date?: number;
  notes: string[];
}

export interface TopicQueryOut {
  id: number;
  topic_text: string;
  date_from: string | null;
  date_to: string | null;
  status: string;
  summary: string | null;
  created_at: string;
  articles: ArticleOut[];
  panorama: TopicPanoramaOut | null;
  narrative_summary: string;
}
