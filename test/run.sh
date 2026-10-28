#!/usr/bin/env bash
# Roda a suíte local que valida CI/CD antes do push.
#   ./test/run.sh
#   ./test/run.sh --no-deploy   # não sobe/recria containers
#   ./test/run.sh --push        # CD também publica no GHCR
set -euo pipefail

TEST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${TEST_DIR}/.." && pwd)"
cd "$ROOT_DIR"

EXTRA_CD_ARGS=()
for arg in "$@"; do
  EXTRA_CD_ARGS+=("$arg")
done

echo "########################################"
echo "# 42 — validação local CI/CD"
echo "########################################"

echo
echo "--- workflows (YAML) ---"
if python3 -c "import yaml" 2>/dev/null; then
  python3 "${TEST_DIR}/test_workflows.py"
else
  echo "  WARN  PyYAML ausente; instalando só para este teste..."
  python3 -m pip install --user -q pyyaml
  python3 "${TEST_DIR}/test_workflows.py"
fi

echo
bash "${TEST_DIR}/test_ci.sh"

echo
bash "${TEST_DIR}/test_cd.sh" "${EXTRA_CD_ARGS[@]}"

echo
echo "########################################"
echo "# Tudo OK — seguro para push (CI/CD local)"
echo "########################################"
