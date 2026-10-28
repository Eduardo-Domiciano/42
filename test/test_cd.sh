#!/usr/bin/env bash
# Espelha .github/workflows/cd.yml sem push ao GHCR (salvo com --push).
# Uso:
#   ./test/test_cd.sh           # tag local + deploy + health
#   ./test/test_cd.sh --no-deploy
#   ./test/test_cd.sh --push    # também envia ao GHCR (precisa login)
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

echo "== test CD =="

require_docker

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

info "build + tag (${PREFIX}-*:${SHA})"
docker compose build
docker tag 42-backend:latest "${PREFIX}-backend:latest"
docker tag 42-backend:latest "${PREFIX}-backend:${SHA}"
docker tag 42-frontend:latest "${PREFIX}-frontend:latest"
docker tag 42-frontend:latest "${PREFIX}-frontend:${SHA}"
pass "tags locais criadas"

if [[ "${DO_PUSH}" -eq 1 ]]; then
  info "push para GHCR"
  docker push "${PREFIX}-backend:latest"
  docker push "${PREFIX}-backend:${SHA}"
  docker push "${PREFIX}-frontend:latest"
  docker push "${PREFIX}-frontend:${SHA}"
  pass "imagens publicadas no GHCR"
else
  info "pulando docker push (use --push para publicar)"
  pass "dry-run de publish ok"
fi

if [[ "${DO_DEPLOY}" -eq 1 ]]; then
  free_published_port "${HOST_PORT}"

  info "docker compose up -d (HOST_PORT=${HOST_PORT})"
  docker compose up -d --remove-orphans --force-recreate
  pass "compose no ar"

  health_url="http://127.0.0.1:${HOST_PORT}/api/health"
  info "health check em ${health_url}"
  if ! wait_health "${health_url}" 30; then
    docker compose ps || true
    docker compose logs --tail=80 || true
    fail "health check falhou"
  fi
  pass "app healthy"
else
  info "pulando deploy (--no-deploy)"
fi

echo "== CD OK =="
