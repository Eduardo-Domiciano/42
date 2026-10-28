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

# DOMAIN pode vir do GitHub (vars/secrets) OU de arquivo na VPS.
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

info "build + tag (${PREFIX}-*:${SHA})"
docker_cmd compose build
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
  if [[ -z "${DOMAIN:-}" ]]; then
    fail "DOMAIN vazio. Faça UMA destas opções:

  A) Na VPS (mais simples):
     echo 'DOMAIN=seu.dominio.com' > ~/42.cd.env
     echo 'CORS_ORIGINS=https://seu.dominio.com' >> ~/42.cd.env

  B) No GitHub:
     Settings → Secrets and variables → Actions → Variables
     DOMAIN = seu.dominio.com  (aba Variables, NÃO Secrets)
     (sem https://)"
  fi
  export DOMAIN
  export CORS_ORIGINS="${CORS_ORIGINS:-https://${DOMAIN}}"
  info "DOMAIN=${DOMAIN}"
  info "CORS_ORIGINS=${CORS_ORIGINS}"

  if ! docker_cmd network inspect edge >/dev/null 2>&1; then
    fail "rede Docker 'edge' não existe. Suba o Traefik antes:
    cd traefik && docker compose up -d"
  fi

  info "docker compose up -d (frontend na rede edge → Traefik)"
  docker_cmd compose up -d --remove-orphans --force-recreate
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
    docker_cmd compose ps || true
    docker_cmd compose logs --tail=80 || true
    fail "health check falhou"
  fi
  pass "app healthy (DOMAIN=${DOMAIN})"
else
  info "pulando deploy (--no-deploy)"
fi

echo "== CD OK =="
