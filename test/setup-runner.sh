#!/usr/bin/env bash
# Configura a máquina do self-hosted runner para o CI do 42.
# Rode uma vez (pede sudo):
#   bash ./test/setup-runner.sh
set -euo pipefail

echo "== setup runner Docker =="

if ! id -nG | grep -qw docker; then
  echo "Adicionando ${USER} ao grupo docker (engine do sistema)..."
  sudo usermod -aG docker "${USER}"
  echo "OK. Faça logout/login ou: newgrp docker"
else
  echo "Já está no grupo docker."
fi

if [[ -S "${HOME}/.docker/desktop/docker.sock" ]]; then
  echo "Docker Desktop socket OK: ${HOME}/.docker/desktop/docker.sock"
else
  echo "AVISO: abra o Docker Desktop antes de rodar o CI."
fi

# Dica de .env do Actions Runner (se a pasta existir)
for d in "${HOME}/actions-runner/42" "${HOME}/actions-runner"; do
  if [[ -d "$d" ]]; then
    envfile="${d}/.env"
    sock="unix://${HOME}/.docker/desktop/docker.sock"
    touch "${envfile}"
    if ! grep -q '^DOCKER_HOST=' "${envfile}" 2>/dev/null; then
      echo "DOCKER_HOST=${sock}" >> "${envfile}"
      echo "Gravado DOCKER_HOST em ${envfile}"
    fi
    if ! grep -q '^PATH=' "${envfile}" 2>/dev/null; then
      echo 'PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin' >> "${envfile}"
      echo "Gravado PATH em ${envfile}"
    fi
  fi
done

echo
echo "Reinicie o runner depois disso."
echo "Valide: ./test/test_ci.sh"
