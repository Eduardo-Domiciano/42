#!/usr/bin/env bash
# Aplica a configuração oficial para self-hosted + Docker Desktop no Linux.
# Docs: docs/ci-cd.md
#
# Uso:
#   bash ./test/setup-runner.sh
#   bash ./test/setup-runner.sh /caminho/para/actions-runner/42
set -euo pipefail

SOCK="unix://${HOME}/.docker/desktop/docker.sock"
RUNNER_DIR="${1:-}"

echo "== setup runner (Docker Desktop + GitHub Actions) =="

if [[ ! -S "${HOME}/.docker/desktop/docker.sock" ]]; then
  echo "ERRO: socket do Desktop ausente: ${HOME}/.docker/desktop/docker.sock"
  echo "Abra o Docker Desktop e rode de novo."
  exit 1
fi
echo "OK socket Desktop"

if ! DOCKER_HOST="${SOCK}" /usr/bin/docker info >/dev/null 2>&1; then
  echo "ERRO: docker info falhou com DOCKER_HOST=${SOCK}"
  exit 1
fi
echo "OK docker info via Desktop"

if [[ -z "${RUNNER_DIR}" ]]; then
  for cand in \
    "${HOME}/actions-runner/42" \
    "${HOME}/actions-runner" \
    "${HOME}/actions-runner/_work/.." \
    ; do
    if [[ -x "${cand}/svc.sh" || -f "${cand}/.runner" ]]; then
      RUNNER_DIR="$(cd "${cand}" && pwd)"
      break
    fi
  done
fi

if [[ -z "${RUNNER_DIR}" || ! -d "${RUNNER_DIR}" ]]; then
  echo
  echo "Pasta do runner não encontrada automaticamente."
  echo "Passe o caminho: bash ./test/setup-runner.sh /caminho/actions-runner/42"
  echo
  echo "Enquanto isso, configure manualmente na pasta do runner:"
  echo "  echo 'DOCKER_HOST=${SOCK}' >> .env"
  echo "  echo 'PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin' >> .env"
  echo "  sudo ./svc.sh stop && sudo ./svc.sh start"
  exit 2
fi

echo "OK runner em ${RUNNER_DIR}"
ENV_FILE="${RUNNER_DIR}/.env"
touch "${ENV_FILE}"

# Sem 'export' — exigência do .env do actions-runner
if grep -q '^DOCKER_HOST=' "${ENV_FILE}"; then
  sed -i "s|^DOCKER_HOST=.*|DOCKER_HOST=${SOCK}|" "${ENV_FILE}"
else
  echo "DOCKER_HOST=${SOCK}" >> "${ENV_FILE}"
fi

if ! grep -q '^PATH=' "${ENV_FILE}"; then
  echo 'PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin' >> "${ENV_FILE}"
fi

echo "OK .env:"
grep -E '^(DOCKER_HOST|PATH)=' "${ENV_FILE}" || true

if id -nG | grep -qw docker; then
  echo "OK já no grupo docker"
else
  echo "Adicionando ${USER} ao grupo docker (fallback do engine do sistema)..."
  sudo usermod -aG docker "${USER}"
  echo "OK usermod (reinicie sessão/serviço para valer)"
fi

if [[ -x "${RUNNER_DIR}/svc.sh" ]]; then
  echo "Reiniciando serviço do runner..."
  sudo "${RUNNER_DIR}/svc.sh" stop || true
  sudo "${RUNNER_DIR}/svc.sh" start
  sudo "${RUNNER_DIR}/svc.sh" status || true
else
  echo "AVISO: svc.sh não encontrado — reinicie o runner manualmente (./run.sh)."
fi

echo
echo "Pronto. Valide no repo:"
echo "  ./test/test_ci.sh"
echo "Depois faça push e rode o workflow CI."
