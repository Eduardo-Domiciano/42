#!/usr/bin/env bash
# CD real — usado localmente E pelo GitHub Actions (.github/workflows/cd.yml).
#   ./test/test_cd.sh
#   ./test/test_cd.sh --no-deploy
#   ./test/test_cd.sh --push
set -euo pipefail
# shellcheck source=common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

DO_DEPLOY=1
DO_PUSH=0
for arg in "$@"; do
  case "$arg" in
    --no-deploy) DO_DEPLOY=0 ;;
    --push) DO_PUSH=1 ;;
    -h|--help)
      sed -n '2,7p' "$0"
      exit 0
      ;;
    *) fail "flag desconhecida: $arg" ;;
  esac
done

echo "== CD =="

# Env: GitHub vars/secrets OU ~/42.cd.env
# Preferência: Traefik (rede edge) → http://IP:80  |  com DOMAIN → HTTPS
# Sem Traefik: fallback http://IP:8080
load_cd_env() {
  local f
  for f in \
    "${HOME}/42.cd.env" \
    "${HOME}/actions-runner/42.cd.env" \
    "/etc/42/cd.env"
  do
    if [[ -f "$f" ]]; then
      info "carregando ${f}"
      set -a
      # shellcheck disable=SC1090
      source "$f"
      set +a
      return 0
    fi
  done
  return 1
}

detect_pub_ip() {
  curl -4 -fsS --max-time 3 https://ifconfig.me/ip 2>/dev/null \
    || curl -4 -fsS --max-time 3 https://api.ipify.org 2>/dev/null \
    || hostname -I 2>/dev/null | awk '{print $1}'
}

load_cd_env || true

setup_docker

OWNER="$(
  git remote get-url origin 2>/dev/null \
    | sed -E 's#.*(github\.com[:/])##' \
    | cut -d/ -f1 \
    | tr '[:upper:]' '[:lower:]' \
    || true
)"
OWNER="${OWNER:-local}"
SHA="$(git rev-parse --short=7 HEAD 2>/dev/null || echo localdev)"
PREFIX="ghcr.io/${OWNER}/42"

USE_EDGE=0
if [[ "${FORCE_HOST_PORT:-0}" == "1" ]]; then
  USE_EDGE=0
elif [[ -n "${DOMAIN:-}" ]] || docker_cmd network inspect edge >/dev/null 2>&1; then
  USE_EDGE=1
fi

COMPOSE_FILES=( -f docker-compose.yml )
if [[ "${USE_EDGE}" -eq 1 ]]; then
  COMPOSE_FILES+=( -f docker-compose.edge.yml )
  if [[ -n "${DOMAIN:-}" ]]; then
    COMPOSE_FILES+=( -f docker-compose.edge-tls.yml )
  fi
fi

info "build + tag (${PREFIX}-*:${SHA})"
docker_cmd compose "${COMPOSE_FILES[@]}" build
docker_cmd tag 42-backend:latest "${PREFIX}-backend:latest"
docker_cmd tag 42-backend:latest "${PREFIX}-backend:${SHA}"
docker_cmd tag 42-frontend:latest "${PREFIX}-frontend:latest"
docker_cmd tag 42-frontend:latest "${PREFIX}-frontend:${SHA}"
pass "tags locais criadas"

if [[ "${DO_PUSH}" -eq 1 ]]; then
  info "push para GHCR"
  docker_cmd push "${PREFIX}-backend:latest"
  docker_cmd push "${PREFIX}-backend:${SHA}"
  docker_cmd push "${PREFIX}-frontend:latest"
  docker_cmd push "${PREFIX}-frontend:${SHA}"
  pass "imagens publicadas no GHCR"
else
  info "sem push GHCR (build local na máquina do runner)"
  pass "imagens locais ok"
fi

if [[ "${DO_DEPLOY}" -eq 1 ]]; then
  PUB_IP="$(detect_pub_ip || true)"

  if [[ "${USE_EDGE}" -eq 1 ]]; then
    if ! docker_cmd network inspect edge >/dev/null 2>&1; then
      fail "rede Docker 'edge' não existe. Suba o Traefik:
    cd traefik && cp -n .env.example .env && nano .env && docker compose up -d
    Portas do Traefik devem ser 80:80 e 443:443 (não 80:8080)."
    fi

    if [[ -n "${DOMAIN:-}" ]]; then
      export DOMAIN
      export CORS_ORIGINS="${CORS_ORIGINS:-https://${DOMAIN}}"
      info "modo Traefik HTTPS DOMAIN=${DOMAIN}"
    else
      if [[ -z "${CORS_ORIGINS:-}" ]]; then
        if [[ -n "${PUB_IP:-}" ]]; then
          CORS_ORIGINS="http://${PUB_IP},http://${PUB_IP}:80,http://127.0.0.1,http://localhost"
        else
          CORS_ORIGINS="http://127.0.0.1,http://localhost"
        fi
      fi
      export CORS_ORIGINS
      info "modo Traefik HTTP (sem domínio) → http://${PUB_IP:-IP}/"
    fi
    info "CORS_ORIGINS=${CORS_ORIGINS}"
  else
    export HOST_PORT="${HOST_PORT:-8080}"
    if [[ -z "${CORS_ORIGINS:-}" ]]; then
      if [[ -n "${PUB_IP:-}" ]]; then
        CORS_ORIGINS="http://${PUB_IP}:${HOST_PORT},http://127.0.0.1:${HOST_PORT},http://localhost:${HOST_PORT}"
      else
        CORS_ORIGINS="http://127.0.0.1:${HOST_PORT},http://localhost:${HOST_PORT}"
      fi
    fi
    export CORS_ORIGINS
    info "modo host :${HOST_PORT} (Traefik/edge ausente)"
    info "CORS_ORIGINS=${CORS_ORIGINS}"
    free_published_port "${HOST_PORT}"
  fi

  info "docker compose up -d"
  docker_cmd compose "${COMPOSE_FILES[@]}" up -d --remove-orphans --force-recreate
  pass "compose no ar"

  info "health check via container backend"
  ok=0
  for _ in $(seq 1 30); do
    if docker_cmd exec 42-backend python -c \
      "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=2).read()" \
      >/dev/null 2>&1; then
      ok=1
      break
    fi
    sleep 2
  done
  if [[ "${ok}" -ne 1 ]]; then
    docker_cmd compose "${COMPOSE_FILES[@]}" ps || true
    docker_cmd compose "${COMPOSE_FILES[@]}" logs --tail=80 || true
    fail "health check falhou"
  fi
  if [[ "${USE_EDGE}" -eq 1 ]]; then
    if [[ -n "${DOMAIN:-}" ]]; then
      pass "app healthy (https://${DOMAIN})"
    else
      pass "app healthy (http://${PUB_IP:-IP}/ via Traefik :80)"
    fi
  else
    pass "app healthy (http://IP:${HOST_PORT})"
  fi
else
  info "pulando deploy (--no-deploy)"
fi

echo "== CD OK =="
