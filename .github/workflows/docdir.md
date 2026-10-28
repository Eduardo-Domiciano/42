# workflows

Pipelines do GitHub Actions para o ④②.

## Arquivos

| Arquivo | O que faz |
| --- | --- |
| `ci.yml` | CI: `docker compose build` + import do backend na imagem (sem Node/Python no host). |
| `cd.yml` | CD: após CI ok no `main`, publica imagens no GHCR e sobe o Compose no runner. |
| `docdir.md` | Este arquivo. |

## Observacoes

- CD também pode ser disparado manualmente (`workflow_dispatch`).
- Deploy local no runner: `http://127.0.0.1:8080`.
