# backend

API e persistência do app: ingestão de URLs, busca por tema e análise preliminar.

## Arquivos

| Arquivo | O que faz |
| --- | --- |
| `requirements.txt` | Dependências Python base. |
| `requirements-nn.txt` | Dependências opcionais de redes neurais (torch, transformers). |
| `source_profiles.yml` | Catálogo de fontes BR/US (tier, topics, hosts; seed só importa BR). |
| `Dockerfile` | Imagem da API (uvicorn; `INSTALL_NN=1` inclui NN). |
| `.dockerignore` | Arquivos excluídos do build da imagem. |

## Subpastas

| Pasta | O que guarda |
| --- | --- |
| `app/` | Código da API, modelos e serviços. |
| `data/` | Banco SQLite local (gerado em runtime). |
| `catalog/` | YAML de bias/ownership BR versionado. |
| `.venv/` | Ambiente virtual Python (não versionado). |
