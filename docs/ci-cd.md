# CI/CD — ④②

## CI (nuvem GitHub)

- Arquivo: `.github/workflows/ci.yml`
- Roda em **`ubuntu-latest`** (máquinas da GitHub)
- **Não usa o seu PC**
- Faz: `docker compose build` + import do backend

## CD (opcional, no seu runner)

- Arquivo: `.github/workflows/cd.yml`
- Só sob demanda (`workflow_dispatch`)
- Usa o runner self-hosted `42` se você disparar manualmente

## Validar local (opcional)

```bash
./test/test_ci.sh
```
