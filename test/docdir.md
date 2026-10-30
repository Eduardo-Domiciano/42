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

- `./test/run.sh` — rolling deploy (só recria o que mudou).
- `./test/run.sh --no-deploy` — valida build/YAML sem tocar nos containers.
- `./test/run.sh --recreate` — force-recreate (downtime curto).
- Actions chama `test_ci.sh` / `test_cd.sh` (mesma lógica).
- Detalhes: `docs/ci-cd.md`.
