#!/usr/bin/env bash
# CI real — usado localmente E pelo GitHub Actions (.github/workflows/ci.yml).
set -euo pipefail
# shellcheck source=common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

echo "== CI =="

setup_docker

info "docker compose build"
DOMAIN="${DOMAIN:-localhost}" docker_cmd compose build
pass "imagens buildadas"

image_exists "42-backend:latest" || fail "falta 42-backend:latest"
image_exists "42-frontend:latest" || fail "falta 42-frontend:latest"
pass "imagens locais ok"

info "import check do backend"
TITLE="$(
  docker_cmd run --rm --entrypoint python 42-backend:latest \
    -c "from app.main import app; print(app.title)"
)"
[[ -n "${TITLE}" ]] || fail "app.title vazio"
pass "backend import ok (${TITLE})"

echo "== CI OK =="
