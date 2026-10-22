# Fase 4 — Cross-reference (cruzamento)

## O que faz

Para cada **Claim (afirmativa)** de um artigo:

1. Busca evidências pares (corpus local e/ou web) e fontes oficiais (`gov.br`, IBGE, etc.).
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

## Limites

- Stance heurística pode errar; LLM opcional via `CROSSREF_USE_LLM_STANCE=true`.
- Sem evidências externas, consenso fica `insufficient`.
