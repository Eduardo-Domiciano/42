#!/usr/bin/env bash
# Espelha .github/workflows/ci.yml — rode antes do push.
set -euo pipefail
# shellcheck source=common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

echo "== test CI =="

require_docker

info "docker compose build"
docker compose build
pass "imagens 42-backend e 42-frontend buildadas"

image_exists "42-backend:latest" || fail "imagem 42-backend:latest ausente"
image_exists "42-frontend:latest" || fail "imagem 42-frontend:latest ausente"
pass "imagens locais encontradas"

info "import check do backend na imagem"
TITLE="$(
  docker run --rm --entrypoint python 42-backend:latest \
    -c "from app.main import app; print(app.title)"
)"
[[ -n "${TITLE}" ]] || fail "app.title vazio"
pass "backend import ok (${TITLE})"

echo "== CI OK =="
