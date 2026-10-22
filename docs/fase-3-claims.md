# Fase 3 — Claims e scores

## O que faz

1. Extrai **afirmações checáveis** do título/corpo.
2. Pontua cada claim (0–1):
   - `temporal` — coerência de datas
   - `geographic` — âncora BR / instituições
   - `partisan` — framing partidário (alto = mais político)
   - `distortion` — clickbait / título vs corpo
   - `internal_support` — números, citações, links no próprio texto
3. Emite veredito preliminar: `supported` | `disputed` | `insufficient` | `opinion`

`supported` aqui significa só **suporte interno forte**, não verdade absoluta. Cruzamento externo é F4.

## Como roda

- Sem `OPENROUTER_API_KEY`: heurísticas (`method=heuristic`)
- Com chave: OpenRouter (`method=llm`), fallback para heurística se a API falhar
- Em busca por tema: LLM só nos primeiros `CLAIM_LLM_MAX_PER_TOPIC` artigos (padrão 3)

## API

- Incluído em `POST /api/ingest/url` e `POST /api/search/topic`
- `POST /api/articles/{id}/reanalyze` — refaz claims
- `GET /api/health` — mostra `llm_configured`
