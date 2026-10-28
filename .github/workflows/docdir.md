# workflows

Pipelines do GitHub Actions para o ④②.

## Arquivos

| Arquivo | O que faz |
| --- | --- |
| `ci.yml` | CI: valida backend, build do Angular e `docker compose build`. |
| `cd.yml` | CD: após CI ok no `main`, publica imagens no GHCR e sobe o Compose no runner. |
| `docdir.md` | Este arquivo. |

## Observacoes

- CD também pode ser disparado manualmente (`workflow_dispatch`).
- Deploy local no runner: `http://127.0.0.1:8080`.
