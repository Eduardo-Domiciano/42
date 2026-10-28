# CI/CD — ④② (self-hosted runner)

Baseado na documentação oficial:

- [Adding self-hosted runners](https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/add-runners)
- [Configuring the runner as a service](https://docs.github.com/en/actions/hosting-your-own-runners/configuring-the-self-hosted-runner-application-as-a-service)
- [Self-hosted runners reference (Docker requirement)](https://docs.github.com/en/actions/reference/runners/self-hosted-runners)
- [Docker Desktop Linux FAQ — socket](https://docs.docker.com/desktop/troubleshoot-and-support/faqs/linuxfaqs/)
- [actions/runner#411 — permission denied no docker.sock](https://github.com/actions/runner/issues/411)
- [actions/runner#827 — DOCKER_HOST no `.env` do runner](https://github.com/actions/runner/issues/827)

## O que o GitHub exige

Para workflows que usam Docker no self-hosted:

1. Máquina **Linux**
2. **Docker instalado** e acessível ao usuário que roda o runner
3. Runner **conectado** (`Listening for Jobs`)
4. Label correta no job: `runs-on: [self-hosted, "42"]`

## O problema neste host (Docker Desktop)

No Linux, o Docker Desktop **não** usa `/var/run/docker.sock`.

Socket correto ([docs Docker](https://docs.docker.com/desktop/troubleshoot-and-support/faqs/linuxfaqs/)):

```text
unix:///home/SEU_USER/.docker/desktop/docker.sock
```

Se o runner (serviço systemd) não tiver `DOCKER_HOST`, o CLI tenta `/var/run/docker.sock` → **permission denied** (usuário fora do grupo `docker`).

`$GITHUB_ENV` no workflow **não basta** sozinho para actions JS (`docker/login-action`) nem para o ambiente do serviço. A configuração estável é no **`.env` do runner**.

## Passos obrigatórios no host do runner

Substitua `~/actions-runner/42` pelo diretório real da instalação.

### 1. Docker Desktop aberto

Confirme:

```bash
ls -la ~/.docker/desktop/docker.sock
DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock docker info
```

### 2. Gravar `.env` do runner (sem a palavra `export`)

```bash
cd ~/actions-runner/42   # pasta onde está o svc.sh

cat >> .env <<EOF
DOCKER_HOST=unix://${HOME}/.docker/desktop/docker.sock
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
EOF
```

Importante ([runner#827](https://github.com/actions/runner/issues/827)): no `.env` use `DOCKER_HOST=...`, **nunca** `export DOCKER_HOST=...`.

### 3. Reiniciar o serviço do runner

O `.env` só é lido na subida do serviço:

```bash
sudo ./svc.sh stop
sudo ./svc.sh start
sudo ./svc.sh status
```

### 4. (Opcional) grupo `docker` — fallback do engine do sistema

```bash
sudo usermod -aG docker "$USER"
# logout/login OU reiniciar o serviço do runner
sudo ./svc.sh stop && sudo ./svc.sh start
```

Útil se um dia usar o engine em `/var/run/docker.sock` em vez do Desktop.

### 5. Validar igual ao Actions

```bash
cd /caminho/do/repo/42
./test/test_ci.sh
```

## O que o workflow faz

| Arquivo | Papel |
| --- | --- |
| `.github/workflows/ci.yml` | Só chama `bash ./test/test_ci.sh` |
| `test/test_ci.sh` | `docker compose build` + import do backend |
| `test/common.sh` | `export DOCKER_HOST` para o socket do Desktop |

## Checklist rápido

- [ ] Runner Idle no GitHub com label `42`
- [ ] Docker Desktop ligado
- [ ] `~/.docker/desktop/docker.sock` existe
- [ ] `.env` do runner tem `DOCKER_HOST=unix://…/desktop/docker.sock`
- [ ] Serviço reiniciado depois de editar `.env`
- [ ] `./test/test_ci.sh` passa localmente
- [ ] Push do workflow atualizado
