#!/usr/bin/env bash
# Helpers Docker — alvo principal: Docker Engine em Ubuntu (VPS).
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:${PATH:-}"
export HOST_PORT="${HOST_PORT:-8080}"

pass() { printf '  PASS  %s\n' "$*"; }
fail() { printf '  FAIL  %s\n' "$*" >&2; exit 1; }
info() { printf '  ....  %s\n' "$*"; }

_docker_bin() {
  local c
  for c in /usr/bin/docker /usr/local/bin/docker /bin/docker; do
    if [[ -x "$c" ]]; then
      printf '%s' "$c"
      return 0
    fi
  done
  return 1
}

# Docker Engine em /var/run/docker.sock (Ubuntu VPS).
setup_docker() {
  DOCKER="$(_docker_bin)" || fail "binário docker não encontrado.
  Na VPS Ubuntu:
    sudo apt-get update
    sudo apt-get install -y docker.io docker-compose-v2
    sudo systemctl enable --now docker"
  export DOCKER

  export DOCKER_HOST="${DOCKER_HOST:-unix:///var/run/docker.sock}"
  export DOCKER_CONTEXT=default

  if [[ ! -S /var/run/docker.sock ]]; then
    fail "socket /var/run/docker.sock ausente — Docker Engine parado ou não instalado.
  Na VPS:
    sudo systemctl enable --now docker
    sudo systemctl status docker"
  fi

  local err
  if ! err="$("${DOCKER}" info 2>&1)"; then
    info "diagnóstico: user=$(id -un) groups=$(id -nG)"
    info "diagnóstico: $(ls -la /var/run/docker.sock 2>&1 || true)"
    if echo "${err}" | grep -qi 'permission denied'; then
      fail "sem permissão no Docker Engine (/var/run/docker.sock).
  Na VPS Ubuntu (usuário do runner = $(id -un)):
    sudo usermod -aG docker $(id -un)
    # reinicie o serviço do runner para carregar o grupo:
    cd /caminho/do/actions-runner && sudo ./svc.sh stop && sudo ./svc.sh start"
    fi
    fail "docker info falhou:
  ${err}"
  fi

  if ! "${DOCKER}" compose version >/dev/null 2>&1; then
    fail "plugin 'docker compose' ausente.
  Na VPS: sudo apt-get install -y docker-compose-v2"
  fi

  pass "docker ok (${DOCKER} → ${DOCKER_HOST})"
}

require_docker() {
  setup_docker
}

docker_cmd() {
  "${DOCKER:?rode setup_docker antes}" "$@"
}

image_exists() {
  docker_cmd image inspect "$1" >/dev/null 2>&1
}

port_is_free() {
  ! ss -tln | grep -q ":${1} "
}

free_published_port() {
  local port="${1:?porta}"
  info "liberando host :${port}"
  docker_cmd compose down --remove-orphans >/dev/null 2>&1 || true

  local ids
  ids="$(docker_cmd ps -aq --filter "publish=${port}" || true)"
  if [[ -n "${ids}" ]]; then
    # shellcheck disable=SC2086
    docker_cmd rm -f ${ids} >/dev/null
    info "removidos containers que publicavam :${port}"
  fi

  if port_is_free "${port}"; then
    pass "porta ${port} livre"
    return 0
  fi

  if sudo -n fuser -k "${port}/tcp" >/dev/null 2>&1; then
    sleep 1
  fi

  if port_is_free "${port}"; then
    pass "porta ${port} livre (fuser)"
    return 0
  fi

  fail "porta ${port} em uso. Na VPS: sudo fuser -k ${port}/tcp
  Ou defina HOST_PORT para outra porta."
}

wait_health() {
  local url="${1:?url}"
  local tries="${2:-30}"
  local i
  for i in $(seq 1 "${tries}"); do
    if curl -fsS "${url}" 2>/dev/null | grep -q '"status"'; then
      return 0
    fi
    sleep 2
  done
  return 1
}
