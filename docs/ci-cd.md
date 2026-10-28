# CI/CD — ④②

## CI

- `.github/workflows/ci.yml` → `ubuntu-latest` (nuvem GitHub)

## CD (VPS Ubuntu + self-hosted runner)

- `.github/workflows/cd.yml` → `[self-hosted, "42"]` **na VPS**
- Usa **Docker Engine** (`/var/run/docker.sock`) — **não** Docker Desktop

### Setup único na VPS

```bash
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-v2
sudo systemctl enable --now docker
sudo usermod -aG docker SEU_USUARIO_DO_RUNNER

# reiniciar o runner para pegar o grupo docker
cd /caminho/do/actions-runner
sudo ./svc.sh stop
sudo ./svc.sh start
```

Confirme:

```bash
docker info
docker compose version
```

O runner com label `42` deve aparecer **Idle** no GitHub e rodar **só na VPS**.
