# Fase 4 — Cross-reference (cruzamento)

## O que faz

Para cada **Claim (afirmativa)** de um artigo:

1. Busca evidências pares (corpus local e/ou web) e fontes oficiais por **tema** do claim (ex.: economia → BCB, IBGE, Fazenda, Tesouro, CVM…). Sem tema detectado, cai no fallback `gov.br` / IBGE / BCB.
2. Classifica **Stance (posição)**: supports / refutes / related / unrelated.
3. Agrega com regras:
   - **Ownership (grupo dono)** repetido = uma voz (peso menor se for o mesmo da matéria)
   - **Primary veto (veto oficial)**: fonte primária que refuta limita o consenso
   - Autoridade pesa mais que volume
4. Compara veredito F3 (isolado) vs F4 (consenso) → **Calibration (calibração)**

## Alertas de Ownership

Se a evidência for do mesmo grupo da matéria original (ex.: G1 citando O Globo), o app marca `same_ownership` e reduz o peso — não conta como consenso independente.

## Modos

- **URL**: busca pares na web + banco local.
- **Tema**: usa os outros artigos do próprio resultado como pool de evidências (mais rápido).

## Comparação BCB (tema economia)

Se o artigo/claims forem de **economia**, além do F4 textual o app:

1. Detecta o tema (`topic_officials.detect_topics`).
2. Garante no SQLite as séries SGS **do ano civil** da matéria (`bcb_series_annual`) — Selic meta, IPCA, IPCA 12m, dólar.
3. Compara números nas afirmativas com o último ponto oficial do ano.
4. Grava o resultado em `article_bcb_comparisons` e expõe em `ArticleOut.bcb_comparisons`.

A busca na API é sempre **anual** (01/01–31/12); anos já baixados reutilizam o cache.

## Limites

- Stance heurística pode errar; LLM opcional via `CROSSREF_USE_LLM_STANCE=true`.
- Sem evidências externas, consenso fica `insufficient`.
- Comparação BCB só cobre indicadores mapeados (Selic/IPCA/dólar) com número explícito no claim.
