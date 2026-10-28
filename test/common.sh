#!/usr/bin/env bash
# Helpers compartilhados — fonte da verdade do Docker para CI/CD local e Actions.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:${PATH:-}"
export HOST_PORT="${HOST_PORT:-8080}"

pass() { printf '  PASS  %s\n' "$*"; }
fail() { printf '  FAIL  %s\n' "$*" >&2; exit 1; }
info() { printf '  ....  %s\n' "$*"; }

# Resolve binário + socket. SEMPRE exporta no shell atual (GITHUB_ENV não
# vale no mesmo step do Actions — foi isso que quebrou o CI).
setup_docker() {
  local c
  DOCKER=""
  for c in /usr/bin/docker /usr/local/bin/docker /bin/docker; do
    if [[ -x "$c" ]]; then
      DOCKER="$c"
      break
    fi
  done
  [[ -n "${DOCKER}" ]] || fail "docker não encontrado em /usr/bin|/usr/local/bin|/bin"
  export DOCKER

  # 1) Docker Desktop (este projeto usa Desktop; usuário NÃO está no grupo docker)
  if [[ -S "${HOME}/.docker/desktop/docker.sock" ]]; then
    export DOCKER_HOST="unix://${HOME}/.docker/desktop/docker.sock"
    # context default + DOCKER_HOST evita cair em /var/run/docker.sock
    export DOCKER_CONTEXT=default
    info "DOCKER_HOST=${DOCKER_HOST}"
  # 2) Engine do sistema, só se o socket for utilizável
  elif [[ -S /var/run/docker.sock ]]; then
    export DOCKER_HOST="unix:///var/run/docker.sock"
    export DOCKER_CONTEXT=default
    if ! "${DOCKER}" info >/dev/null 2>&1; then
      fail "sem permissão em /var/run/docker.sock.
  Opção A (recomendada aqui): abra o Docker Desktop e garanta o socket
    ${HOME}/.docker/desktop/docker.sock
  Opção B: sudo usermod -aG docker \"${USER:-$(id -un)}\" && newgrp docker"
    fi
  else
    fail "nenhum socket Docker. Abra o Docker Desktop e rode de novo."
  fi

  "${DOCKER}" version >/dev/null
  "${DOCKER}" compose version >/dev/null
  pass "docker ok (${DOCKER}, host=${DOCKER_HOST})"
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
    pass "porta ${port} livre (sudo fuser)"
    return 0
  fi

  fail "porta ${port} presa. Rode: sudo fuser -k ${port}/tcp
  Ou: HOST_PORT=8088 ./test/run.sh"
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
