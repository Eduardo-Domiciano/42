# test

Scripts e checagens para validar CI/CD localmente antes do push.

## Arquivos

| Arquivo | O que faz |
| --- | --- |
| `common.sh` | PATH, socket do Docker Desktop e helpers `pass`/`fail`. |
| `test_ci.sh` | Espelha o workflow CI: build Compose + import do backend. |
| `test_cd.sh` | Espelha o CD: tag, health; push GHCR só com `--push`. |
| `test_workflows.py` | Unitários da estrutura dos YAMLs de CI/CD. |
| `run.sh` | Roda workflows + CI + CD em sequência. |
| `setup-runner.sh` | Setup único: grupo docker + `.env` do runner. |
| `docdir.md` | Este arquivo. |

## Observacoes

- Na raiz do projeto: `./test/run.sh`
- Sem recriar containers: `./test/run.sh --no-deploy`
- Docker Desktop precisa estar ligado.
- Actions chama `test_ci.sh` / `test_cd.sh` (mesma lógica).
- Se a porta 8080 estiver presa: `sudo fuser -k 8080/tcp` ou `HOST_PORT=8088`.
- Detalhes: `docs/ci-cd.md`.
