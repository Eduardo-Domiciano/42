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
| `docdir.md` | Este arquivo. |

## Observacoes

- Na raiz do projeto: `./test/run.sh`
- Sem recriar containers: `./test/run.sh --no-deploy`
- Docker Desktop precisa estar ligado.
- Se a porta 8080 estiver presa por `sudo docker` antigo: `sudo fuser -k 8080/tcp`
- Porta alternativa: `HOST_PORT=8088 ./test/run.sh`
