"""Auditoria de pedidos de análise (IP + ação + alvo)."""

from __future__ import annotations

import hashlib
import re

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AnalysisAudit


def client_ip_from_request(request: Request) -> str:
    """IP do visitante: X-Forwarded-For (1º) → X-Real-IP → request.client."""
    xff = (request.headers.get("x-forwarded-for") or "").strip()
    if xff:
        # "client, proxy1, proxy2" — o primeiro é o original
        first = xff.split(",")[0].strip()
        if first:
            return first[:80]
    xri = (request.headers.get("x-real-ip") or "").strip()
    if xri:
        return xri[:80]
    if request.client and request.client.host:
        return str(request.client.host)[:80]
    return ""


def user_agent_from_request(request: Request) -> str | None:
    ua = (request.headers.get("user-agent") or "").strip()
    return ua[:400] if ua else None


def target_for_text(text: str, title: str | None = None) -> str:
    """Não grava o corpo inteiro: título + hash + trecho curto."""
    body = (text or "").strip()
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]
    snippet = re.sub(r"\s+", " ", body)[:120]
    prefix = (title or "").strip()
    if prefix:
        return f"text:{digest} | {prefix[:80]} | {snippet}"
    return f"text:{digest} | {snippet}"


def record_audit(
    db: Session,
    *,
    request: Request | None = None,
    client_ip: str | None = None,
    action: str,
    target: str = "",
    article_id: int | None = None,
    status: str = "ok",
    detail: str | None = None,
    user_agent: str | None = None,
) -> AnalysisAudit:
    ip = client_ip
    ua = user_agent
    if request is not None:
        if not ip:
            ip = client_ip_from_request(request)
        if ua is None:
            ua = user_agent_from_request(request)
    row = AnalysisAudit(
        client_ip=(ip or "")[:80],
        action=(action or "")[:40],
        target=(target or "")[:2000],
        article_id=article_id,
        status=(status or "ok")[:20],
        detail=(detail[:500] if detail else None),
        user_agent=ua,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_audit_events(
    db: Session, *, limit: int = 100, offset: int = 0
) -> list[AnalysisAudit]:
    lim = max(1, min(limit, 500))
    off = max(0, offset)
    return list(
        db.scalars(
            select(AnalysisAudit)
            .order_by(AnalysisAudit.created_at.desc(), AnalysisAudit.id.desc())
            .offset(off)
            .limit(lim)
        ).all()
    )
