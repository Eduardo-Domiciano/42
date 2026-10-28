#!/usr/bin/env bash
# Helpers compartilhados pelos testes locais de CI/CD.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:${PATH:-}"
export HOST_PORT="${HOST_PORT:-8080}"

if [[ -S "${HOME}/.docker/desktop/docker.sock" ]]; then
  export DOCKER_HOST="unix://${HOME}/.docker/desktop/docker.sock"
fi

pass() { printf '  PASS  %s\n' "$*"; }
fail() { printf '  FAIL  %s\n' "$*" >&2; exit 1; }
info() { printf '  ....  %s\n' "$*"; }

require_docker() {
  command -v docker >/dev/null 2>&1 || fail "docker não encontrado no PATH"
  docker version >/dev/null 2>&1 || fail "docker não responde (Docker Desktop ligado?)"
  pass "docker disponível"
}

image_exists() {
  docker image inspect "$1" >/dev/null 2>&1
}

port_is_free() {
  ! ss -tln | grep -q ":${1} "
}

# Libera porta publicada por containers (Desktop). Proxies do dockerd do
# sistema (ex.: após `sudo docker`) exigem sudo.
free_published_port() {
  local port="${1:?porta}"
  info "liberando host :${port}"
  docker compose down --remove-orphans >/dev/null 2>&1 || true

  local ids
  ids="$(docker ps -aq --filter "publish=${port}" || true)"
  if [[ -n "${ids}" ]]; then
    # shellcheck disable=SC2086
    docker rm -f ${ids} >/dev/null
    info "removidos containers (Desktop) que publicavam :${port}"
  fi

  if port_is_free "${port}"; then
    pass "porta ${port} livre"
    return 0
  fi

  # Tenta sem senha (NOPASSWD). Senão, instruções claras.
  if sudo -n fuser -k "${port}/tcp" >/dev/null 2>&1; then
    sleep 1
  fi

  if port_is_free "${port}"; then
    pass "porta ${port} livre (sudo fuser)"
    return 0
  fi

  fail "porta ${port} presa por docker-proxy do sistema (provável 'sudo docker'). Rode uma vez:
    sudo fuser -k ${port}/tcp
  Ou use outra porta:
    HOST_PORT=8088 ./test/run.sh"
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
