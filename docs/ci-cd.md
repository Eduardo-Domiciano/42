# CI/CD — deploy na VPS Ubuntu

## O que cada um faz

| Peça | Onde | Papel |
| --- | --- | --- |
| **CI** | `ubuntu-latest` (GitHub) | Só build/teste |
| **CD** | self-hosted label `42` **na VPS** | `compose build` + `up` |
| **Docker** | **Engine** em `/var/run/docker.sock` | Sem Docker Desktop |

## Erro `…/.docker/desktop/docker.sock`

Significa que o runner ainda tem no **`.env` da pasta do actions-runner**:

```env
DOCKER_HOST=unix:///home/eduardo/.docker/desktop/docker.sock
```

Isso é de PC/Desktop. Na VPS esse arquivo não existe.

**Corrija na VPS** (pasta do runner, onde está o `svc.sh`):

```bash
# troque ou apague a linha DOCKER_HOST do Desktop
nano .env
# deixe assim (ou remova DOCKER_HOST):
DOCKER_HOST=unix:///var/run/docker.sock

sudo ./svc.sh stop
sudo ./svc.sh start
```

O script de CD agora também força `docker --host unix:///var/run/docker.sock` (não depende do `.env`).

## Checklist VPS Ubuntu (uma vez)

```bash
# 1) Docker Engine + Compose
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-v2
# se usa Docker Inc. (docker-ce), ok também — desde que exista /var/run/docker.sock
sudo systemctl enable --now docker

# 2) Usuário do runner no grupo docker
sudo usermod -aG docker eduardo   # ou o user que roda o runner

# 3) Runner GitHub com label 42, Idle, SÓ nesta VPS
cd /caminho/actions-runner
# .env SEM desktop:
#   DOCKER_HOST=unix:///var/run/docker.sock
sudo ./svc.sh stop && sudo ./svc.sh start

# 4) Teste SEM sudo
docker --host unix:///var/run/docker.sock info
docker --host unix:///var/run/docker.sock compose version
```

## Depois do push

1. Commit/push do `test/common.sh` novo (senão o Actions usa o script antigo).
2. Rode o workflow **CD** (ou push no `main` após CI).
3. App em `http://IP_DA_VPS:8080` (ou `HOST_PORT` que configurou).

## O que NÃO é necessário

- Docker Desktop
- Runner no seu notebook
- `/home/eduardo/.docker/desktop/docker.sock`
