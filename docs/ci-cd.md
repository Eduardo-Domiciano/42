# CI/CD — ④②

## CI

- `.github/workflows/ci.yml`
- Roda em **`ubuntu-latest`** (nuvem GitHub)
- Não usa PC nem VPS

## CD (VPS + self-hosted runner)

- `.github/workflows/cd.yml`
- Roda no runner **`[self-hosted, "42"]` instalado NA VPS**
- Dispara após CI ok no `main` (push) ou manualmente (`workflow_dispatch`)
- Na VPS: `docker compose build` + `up -d` + health em `/api/health`

### Checklist na VPS

1. Docker Engine + Compose instalados
2. Usuário do runner no grupo `docker` (`sudo usermod -aG docker $USER`)
3. Runner GitHub instalado, label **`42`**, status **Idle**
4. (Opcional) Variables no repo GitHub:
   - `HOST_PORT` — padrão `8080` (use `80` se for a porta pública)
   - `CORS_ORIGINS` — ex. `http://SEU_IP:8080,https://seu.dominio`

### Não fazer

- Não deixar o runner `42` rodando no PC se o CD deve ir para a VPS (um label, uma máquina).
