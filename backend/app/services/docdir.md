# services

Regras de negócio da coleta e análise preliminar.

## Arquivos

| Arquivo | O que faz |
| --- | --- |
| `__init__.py` | Marca o pacote. |
| `seed.py` | Carrega fontes BR do YAML (tier, topics, host_patterns, source_role). |
| `fetch_article.py` | Baixa URL, extrai corpo/links citados e grava artigo; resolve fonte multi-host. |
| `ingest_text.py` | Grava texto colado (sem URL) e prepara para o mesmo pipeline. |
| `topic_officials.py` | Monta `site:` dos oficiais primary conforme temas selecionados. |
| `bcb_sgs.py` | API SGS do BCB + cache anual (`bcb_series_annual`). |
| `bcb_compare.py` | Compara claims com séries BCB se o tema economia foi selecionado. |
| `themes_catalog.py` | Temas oficiais selecionáveis (hoje: economia). |
| `topic_search.py` | Busca local + web por tema/período com filtro de relevância. |
| `topic_relevance.py` | Tokeniza tema, score lexical/semântico e aceita/descarta (camadas). |
| `topic_relevance_llm.py` | Juiz LLM opcional (desligado; filtro usa heurística). |
| `analyze.py` | Scores/notas preliminares por artigo e panorama. |
| `analysis_cache.py` | Snapshot `article_analyses` e links outbound. |
| `article_response.py` | Monta `ArticleOut` com cache do acervo. |
| `bias_catalog.py` | Leitura do YAML de bias e labels em PT. |
| `content_classifier.py` | Classifica tipo de conteúdo (artigo, opinião, oficial…). |
| `heuristic_claims.py` | Extração, fingerprint/near-dup e scores de claims sem LLM. |
| `llm_client.py` | Cliente LLM opcional (desligado por padrão). |
| `claim_pipeline.py` | Orquestra LLM/heurística, deduplica e persiste assessments. |
| `web_search.py` | Busca URLs via DuckDuckGo (prioriza news; text só se faltar). |
| `stance.py` | Classifica se evidência apoia/refuta o claim (heurística + NLI). |
| `cross_reference.py` | Cruzamento F4: evidências, ownership, veto, calibração. |
| `narrative_summary.py` | Resumo em português simples (templates; sem LLM). |
| `nn_runtime.py` | Carrega lazy modelos NLI/embeddings; status e flags. |
| `nn_nli.py` | Stance complementar via mDeBERTa XNLI. |
| `nn_embeddings.py` | Similaridade e ranking de pares por embeddings. |
| `nn_clickbait.py` | Score clickbait (título×corpo) fundido à Distortion. |
