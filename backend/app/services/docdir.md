# services

Regras de negócio da coleta e análise preliminar.

## Arquivos

| Arquivo | O que faz |
| --- | --- |
| `__init__.py` | Marca o pacote. |
| `seed.py` | Carrega fontes BR do YAML. |
| `fetch_article.py` | Baixa URL, extrai corpo/links citados e grava artigo. |
| `topic_search.py` | Busca local + web por tema/período com filtro de relevância. |
| `topic_relevance.py` | Tokeniza tema, score lexical/semântico e aceita/descarta artigos. |
| `analyze.py` | Scores/notas preliminares por artigo e panorama. |
| `analysis_cache.py` | Snapshot `article_analyses` e links outbound. |
| `article_response.py` | Monta `ArticleOut` com cache do acervo. |
| `bias_catalog.py` | Leitura do YAML de bias e labels em PT. |
| `content_classifier.py` | Classifica tipo de conteúdo (artigo, opinião, oficial…). |
| `heuristic_claims.py` | Extração e scores de claims sem LLM. |
| `llm_client.py` | Cliente OpenRouter (JSON). |
| `claim_pipeline.py` | Orquestra LLM/heurística e persiste assessments. |
| `web_search.py` | Busca URLs via DuckDuckGo (prioriza news; text só se faltar). |
| `stance.py` | Classifica se evidência apoia/refuta o claim (heurística + NLI). |
| `cross_reference.py` | Cruzamento F4: evidências, ownership, veto, calibração. |
| `narrative_summary.py` | Texto corrido (parágrafos) resumindo cada ponto da análise. |
| `nn_runtime.py` | Carrega lazy modelos NLI/embeddings; status e flags. |
| `nn_nli.py` | Stance complementar via mDeBERTa XNLI. |
| `nn_embeddings.py` | Similaridade e ranking de pares por embeddings. |
| `nn_clickbait.py` | Score clickbait (título×corpo) fundido à Distortion. |
