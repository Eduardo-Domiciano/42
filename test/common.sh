#!/usr/bin/env bash
# Helpers Docker — só Docker Engine (Ubuntu VPS). Sem Docker Desktop.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:${PATH:-}"
export HOST_PORT="${HOST_PORT:-8080}"

# Socket fixo do Engine. Nunca Desktop.
ENGINE_SOCK="unix:///var/run/docker.sock"

pass() { printf '  PASS  %s\n' "$*"; }
fail() { printf '  FAIL  %s\n' "$*" >&2; exit 1; }
info() { printf '  ....  %s\n' "$*"; }

# Carrega .env sem `source` (htpasswd tem $apr1$... — bash quebraria com set -u).
# Aceita $$ do Compose e exporta com $ simples (valor real para o Traefik).
load_dotenv() {
  local f="$1" line key val
  [[ -f "$f" ]] || return 1
  info "carregando ${f}"
  while IFS= read -r line || [[ -n "${line}" ]]; do
    line="${line%$'\r'}"
    [[ -z "${line}" || "${line}" =~ ^[[:space:]]*# ]] && continue
    [[ "${line}" =~ ^[[:space:]]*[A-Za-z_][A-Za-z0-9_]*[[:space:]]*= ]] || continue
    key="${line%%=*}"
    key="${key#"${key%%[![:space:]]*}"}"
    key="${key%"${key##*[![:space:]]}"}"
    val="${line#*=}"
    if [[ "${val}" =~ ^\"(.*)\"$ ]]; then
      val="${BASH_REMATCH[1]}"
    elif [[ "${val}" =~ ^\'(.*)\'$ ]]; then
      val="${BASH_REMATCH[1]}"
    fi
    val="${val//\$\$/\$}"
    printf -v "${key}" '%s' "${val}"
    export "${key}"
  done < "${f}"
  return 0
}

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

setup_docker() {
  DOCKER="$(_docker_bin)" || fail "docker não instalado.
  Na VPS Ubuntu:
    sudo apt-get update
    sudo apt-get install -y docker.io docker-compose-v2
    # ou o pacote docker-ce da Docker Inc.
    sudo systemctl enable --now docker"
  export DOCKER

  # Limpa herança do runner (.env com Desktop, context desktop-linux, etc.)
  unset DOCKER_HOST DOCKER_CONTEXT || true
  export DOCKER_HOST="${ENGINE_SOCK}"
  # config limpa: ignora ~/.docker/config.json com currentContext=desktop-linux
  export DOCKER_CONFIG="${ROOT_DIR}/.docker-cd-config"
  mkdir -p "${DOCKER_CONFIG}"
  printf '%s\n' '{"auths":{}}' > "${DOCKER_CONFIG}/config.json"

  if [[ ! -S /var/run/docker.sock ]]; then
    fail "/var/run/docker.sock não existe. Na VPS:
    sudo systemctl enable --now docker
    sudo systemctl status docker --no-pager"
  fi

  info "usando Engine: ${ENGINE_SOCK} (user=$(id -un) groups=$(id -nG))"

  local err
  if ! err="$(docker_cmd info 2>&1)"; then
    info "ls sock: $(ls -la /var/run/docker.sock 2>&1 || true)"
    info "env DOCKER_HOST was: ${DOCKER_HOST:-<empty>}"
    if echo "${err}" | grep -qi 'permission denied'; then
      fail "sem permissão em /var/run/docker.sock.
  sudo usermod -aG docker $(id -un)
  # reinicie o runner (senão o grupo não vale):
  sudo ./svc.sh stop && sudo ./svc.sh start"
    fi
    fail "docker info falhou:
  ${err}"
  fi

  if ! docker_cmd compose version >/dev/null 2>&1; then
    fail "falta docker compose. Na VPS: sudo apt-get install -y docker-compose-v2"
  fi

  pass "docker ok (${DOCKER} -H ${ENGINE_SOCK})"
}

require_docker() {
  setup_docker
}

# Sempre passa --host do Engine (anula .env do runner e context Desktop).
docker_cmd() {
  "${DOCKER:?rode setup_docker antes}" --host "${ENGINE_SOCK}" "$@"
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

  fail "porta ${port} em uso. sudo fuser -k ${port}/tcp  ou  HOST_PORT=outra"
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
