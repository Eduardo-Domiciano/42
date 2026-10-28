# CI/CD — ④②

## O que o CI faz

1. `docker compose build` (backend Python + frontend Angular no Dockerfile)
2. Import do FastAPI dentro da imagem `42-backend`

Script único: `test/test_ci.sh` (local **e** GitHub Actions).

## Requisitos do runner self-hosted (label `42`)

| Requisito | Por quê |
| --- | --- |
| Docker Desktop **ligado** | Socket em `~/.docker/desktop/docker.sock` |
| Binário `/usr/bin/docker` | CLI |
| **Não** usar `sudo docker` | Cria proxy zumbi em portas (ex.: 8080) |
| Opcional: grupo `docker` | Fallback para `/var/run/docker.sock` |

Setup único:

```bash
bash ./test/setup-runner.sh
# abra o Docker Desktop
./test/test_ci.sh
```

## Por que falhava antes

1. `env.PATH` no YAML é sobrescrito pelo runner → `docker: not found`
2. Gravar `DOCKER_HOST` só em `$GITHUB_ENV` **não vale no mesmo step** → o cliente ia para `/var/run/docker.sock`
3. Usuário **fora** do grupo `docker` → `permission denied` nesse socket

Correção: `test/common.sh` faz `export DOCKER_HOST=...` **no shell atual** apontando ao Desktop.

## Validar antes do push

```bash
./test/run.sh --no-deploy   # CI + tag CD
./test/run.sh               # + deploy local
```
