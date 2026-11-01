from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.db import get_db
from app.models import Article, TopicQuery
from app.schemas import (
    AnalysisAuditListOut,
    AnalysisAuditOut,
    ArticleLookupRequest,
    ArticleLookupResponse,
    ArticleOut,
    IngestTextRequest,
    IngestUrlRequest,
    NormaOut,
    NormaSearchResponse,
    ReanalyzeRequest,
    TopicQueryOut,
    TopicSearchRequest,
)
from app.services.analyze import build_panorama
from app.services.article_lookup import lookup_prior_analysis
from app.services.article_response import build_article_out
from app.services.audit import list_audit_events, record_audit, target_for_text
from app.services.fetch_article import fetch_and_store_article
from app.services.ingest_text import store_pasted_text
from app.services.llm_client import llm_configured
from app.services.narrative_summary import build_topic_narrative
from app.services.themes_catalog import list_themes, normalize_themes
from app.services.topic_search import run_topic_search

router = APIRouter(prefix="/api")


@router.get("/health")
def health() -> dict[str, object]:
    from app.services.nn_runtime import nli_status

    from app.services.llm_client import effective_model, llm_provider

    return {
        "status": "ok",
        "llm_configured": llm_configured(),
        "llm_provider": llm_provider(),
        "llm_model": effective_model(),
        "claim_use_llm": settings.claim_use_llm,
        "topic_relevance_use_llm": settings.topic_relevance_use_llm,
        "topic_relevance_llm_model": settings.topic_relevance_llm_model,
        "narrative_use_llm": settings.narrative_use_llm,
        "crossref_enabled": settings.crossref_enabled,
        "nn": nli_status(),
        "analysis_archive": True,
    }


@router.get("/catalog/bias")
def get_bias_catalog() -> dict:
    from app.services.bias_catalog import load_bias_catalog

    catalog = load_bias_catalog()
    return {
        "version": catalog.get("version"),
        "country": catalog.get("country"),
        "updated_at": catalog.get("updated_at"),
        "methodology": catalog.get("methodology"),
        "sources": catalog.get("sources") or {},
    }


@router.get("/themes")
def get_themes() -> dict:
    """Temas oficiais selecionáveis (multi); hoje só economia."""
    return {"themes": list_themes()}


@router.get("/audit/events", response_model=AnalysisAuditListOut)
def get_audit_events(
    limit: int = 100,
    offset: int = 0,
    x_audit_token: str | None = Header(default=None, alias="X-Audit-Token"),
    db: Session = Depends(get_db),
) -> AnalysisAuditListOut:
    """Histórico de análises (IP + ação + alvo). Exige AUDIT_TOKEN."""
    expected = (settings.audit_token or "").strip()
    if not expected:
        raise HTTPException(status_code=404, detail="Não encontrado")
    if not x_audit_token or x_audit_token != expected:
        raise HTTPException(status_code=401, detail="Token de auditoria inválido")
    lim = max(1, min(limit, 500))
    off = max(0, offset)
    rows = list_audit_events(db, limit=lim, offset=off)
    return AnalysisAuditListOut(
        events=[AnalysisAuditOut.model_validate(r) for r in rows],
        limit=lim,
        offset=off,
    )


@router.get("/normas/search", response_model=NormaSearchResponse)
def search_normas_api(
    q: str,
    vigente: int = 1,
    esfera: str | None = None,
    limit: int | None = None,
    db: Session = Depends(get_db),
) -> NormaSearchResponse:
    """Busca FTS em metadados/ementa de normas (acervo leis-main)."""
    from app.services.norma_search import search_normas

    if not (q or "").strip():
        raise HTTPException(status_code=400, detail="Parâmetro q é obrigatório")
    if not settings.norma_search_enabled:
        raise HTTPException(status_code=503, detail="Busca de normas desabilitada")

    lim = limit if limit is not None else settings.norma_search_limit
    lim = max(1, min(lim, 50))
    hits = search_normas(
        db,
        q.strip(),
        vigente_only=bool(vigente),
        esfera=esfera or None,
        limit=lim,
    )
    results = [
        NormaOut(
            id=h.norma.id,
            urn=h.norma.urn,
            esfera=h.norma.esfera,
            uf=h.norma.uf,
            tipo=h.norma.tipo,
            numero=h.norma.numero,
            data_norma=h.norma.data_norma,
            titulo=h.norma.titulo,
            ementa=h.norma.ementa,
            revogada=h.norma.revogada,
            fonte_url=h.norma.fonte_url,
            path_md=h.norma.path_md,
            score=h.score,
            snippet=h.snippet,
        )
        for h in hits
    ]
    return NormaSearchResponse(
        query=q.strip(),
        vigente_only=bool(vigente),
        esfera=esfera,
        results=results,
    )


@router.post("/ingest/url", response_model=ArticleOut)
def ingest_url(
    payload: IngestUrlRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> ArticleOut:
    target = str(payload.url)
    try:
        article = fetch_and_store_article(
            db, str(payload.url), refresh=payload.refresh
        )
    except Exception as exc:
        record_audit(
            db,
            request=request,
            action="ingest_url",
            target=target,
            status="error",
            detail=str(exc)[:500],
        )
        raise HTTPException(status_code=400, detail=f"Falha ao buscar URL: {exc}") from exc

    article = db.scalar(
        select(Article)
        .options(joinedload(Article.source))
        .where(Article.id == article.id)
    )
    if not article:
        record_audit(
            db,
            request=request,
            action="ingest_url",
            target=target,
            status="error",
            detail="Artigo não persistido",
        )
        raise HTTPException(status_code=500, detail="Artigo não persistido")
    out = build_article_out(
        db,
        article,
        allow_llm=True,
        run_crossref=True,
        themes=normalize_themes(payload.themes),
    )
    record_audit(
        db,
        request=request,
        action="ingest_url",
        target=target,
        article_id=article.id,
        status="ok",
    )
    return out


@router.post("/ingest/text", response_model=ArticleOut)
def ingest_text(
    payload: IngestTextRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> ArticleOut:
    target = target_for_text(payload.text, payload.title)
    try:
        article = store_pasted_text(
            db,
            text=payload.text,
            title=payload.title,
            published_at=payload.published_at,
        )
    except ValueError as exc:
        record_audit(
            db,
            request=request,
            action="ingest_text",
            target=target,
            status="error",
            detail=str(exc)[:500],
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        record_audit(
            db,
            request=request,
            action="ingest_text",
            target=target,
            status="error",
            detail=str(exc)[:500],
        )
        raise HTTPException(
            status_code=400, detail=f"Falha ao gravar texto: {exc}"
        ) from exc

    article = db.scalar(
        select(Article)
        .options(joinedload(Article.source))
        .where(Article.id == article.id)
    )
    if not article:
        record_audit(
            db,
            request=request,
            action="ingest_text",
            target=target,
            status="error",
            detail="Texto não persistido",
        )
        raise HTTPException(status_code=500, detail="Texto não persistido")
    out = build_article_out(
        db,
        article,
        allow_llm=True,
        run_crossref=True,
        themes=normalize_themes(payload.themes),
    )
    record_audit(
        db,
        request=request,
        action="ingest_text",
        target=target,
        article_id=article.id,
        status="ok",
    )
    return out


@router.post("/search/topic", response_model=TopicQueryOut)
def search_topic(
    payload: TopicSearchRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> TopicQueryOut:
    from dateutil.relativedelta import relativedelta

    if payload.date_from and payload.date_to and payload.date_from > payload.date_to:
        raise HTTPException(status_code=400, detail="date_from não pode ser após date_to")
    if (
        payload.date_from
        and payload.date_to
        and payload.date_to > payload.date_from + relativedelta(months=1)
    ):
        raise HTTPException(
            status_code=400,
            detail="O intervalo entre De e Até não pode passar de 1 mês",
        )
    try:
        result = run_topic_search(
            db,
            topic=payload.topic,
            date_from=payload.date_from,
            date_to=payload.date_to,
            on_date=payload.on_date,
            themes=normalize_themes(payload.themes),
        )
    except Exception as exc:
        record_audit(
            db,
            request=request,
            action="search_topic",
            target=payload.topic.strip()[:500],
            status="error",
            detail=str(exc)[:500],
        )
        raise
    record_audit(
        db,
        request=request,
        action="search_topic",
        target=payload.topic.strip()[:500],
        status="ok",
        detail=f"query_id={result.id} articles={len(result.articles)}",
    )
    return result


@router.get("/topic-queries/{query_id}", response_model=TopicQueryOut)
def get_topic_query(query_id: int, db: Session = Depends(get_db)) -> TopicQueryOut:
    from app.models import QueryArticle

    topic_query = db.scalar(select(TopicQuery).where(TopicQuery.id == query_id))
    if not topic_query:
        raise HTTPException(status_code=404, detail="Consulta não encontrada")

    articles = list(
        db.scalars(
            select(Article)
            .options(joinedload(Article.source))
            .join(QueryArticle, QueryArticle.article_id == Article.id)
            .where(QueryArticle.topic_query_id == query_id)
            .order_by(QueryArticle.rank)
        )
        .unique()
        .all()
    )
    outs = []
    claims_map = {}
    xrefs_map = {}
    for idx, article in enumerate(articles):
        allow_llm = idx < settings.claim_llm_max_per_topic
        out = build_article_out(
            db,
            article,
            allow_llm=allow_llm,
            run_crossref=settings.crossref_on_topic,
            peer_pool=articles,
        )
        outs.append(out)
        claims_map[article.id] = out.claims
        xrefs_map[article.id] = out.cross_references

    panorama = build_panorama(
        articles, article_claims=claims_map, article_xrefs=xrefs_map
    )
    return TopicQueryOut(
        id=topic_query.id,
        topic_text=topic_query.topic_text,
        date_from=topic_query.date_from,
        date_to=topic_query.date_to,
        status=topic_query.status,
        summary=topic_query.summary,
        created_at=topic_query.created_at,
        articles=outs,
        panorama=panorama,
        narrative_summary=build_topic_narrative(
            topic=topic_query.topic_text,
            panorama=panorama,
            articles_count=len(outs),
        ),
    )


@router.post("/articles/lookup", response_model=ArticleLookupResponse)
def lookup_article(
    payload: ArticleLookupRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> ArticleLookupResponse:
    """
    Checa se URL/título/texto (+ data) já tem análise no acervo.
    Sem match → found=false (fluxo normal de ingestão).
    """
    if payload.url:
        target = str(payload.url)
    elif payload.title:
        target = f"title:{payload.title.strip()[:200]}"
    elif payload.text:
        target = target_for_text(payload.text, payload.title)
    else:
        target = "(vazio)"
    result = lookup_prior_analysis(
        db,
        url=payload.url,
        title=payload.title,
        text=payload.text,
        published_at=payload.published_at,
    )
    article_id = result.match.article_id if result.found and result.match else None
    record_audit(
        db,
        request=request,
        action="lookup",
        target=target,
        article_id=article_id,
        status="ok",
        detail="found" if result.found else "not_found",
    )
    return result


@router.get("/articles/{article_id}", response_model=ArticleOut)
def get_article(
    article_id: int,
    themes: str | None = None,
    db: Session = Depends(get_db),
) -> ArticleOut:
    article = db.scalar(
        select(Article)
        .options(joinedload(Article.source))
        .where(Article.id == article_id)
    )
    if not article:
        raise HTTPException(status_code=404, detail="Artigo não encontrado")
    theme_list = [t.strip() for t in (themes or "").split(",") if t.strip()]
    return build_article_out(
        db, article, themes=normalize_themes(theme_list)
    )


@router.post("/articles/{article_id}/reanalyze", response_model=ArticleOut)
def reanalyze_article(
    article_id: int,
    request: Request,
    payload: ReanalyzeRequest | None = None,
    db: Session = Depends(get_db),
) -> ArticleOut:
    body = payload or ReanalyzeRequest()
    article = db.scalar(
        select(Article)
        .options(joinedload(Article.source))
        .where(Article.id == article_id)
    )
    if not article:
        record_audit(
            db,
            request=request,
            action="reanalyze",
            target=f"article:{article_id}",
            article_id=article_id,
            status="error",
            detail="Artigo não encontrado",
        )
        raise HTTPException(status_code=404, detail="Artigo não encontrado")

    target = article.url or f"article:{article_id}"

    # Rebaixa a página quando for URL real (não texto colado)
    if body.refresh and not (article.normalized_url or "").startswith("text://"):
        try:
            article = fetch_and_store_article(db, article.url, refresh=True)
            article = db.scalar(
                select(Article)
                .options(joinedload(Article.source))
                .where(Article.id == article.id)
            )
        except Exception as exc:
            record_audit(
                db,
                request=request,
                action="reanalyze",
                target=target,
                article_id=article_id,
                status="error",
                detail=str(exc)[:500],
            )
            raise HTTPException(
                status_code=400, detail=f"Falha ao atualizar URL: {exc}"
            ) from exc
        if not article:
            record_audit(
                db,
                request=request,
                action="reanalyze",
                target=target,
                article_id=article_id,
                status="error",
                detail="Artigo não persistido",
            )
            raise HTTPException(status_code=500, detail="Artigo não persistido")

    # force: invalida claims/F4 e regenera snapshot
    out = build_article_out(
        db,
        article,
        run_claims=True,
        run_crossref=True,
        force=True,
        allow_llm=True,
        themes=normalize_themes(body.themes),
    )
    record_audit(
        db,
        request=request,
        action="reanalyze",
        target=target,
        article_id=article.id,
        status="ok",
    )
    return out
