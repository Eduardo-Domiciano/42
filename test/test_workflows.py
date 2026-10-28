#!/usr/bin/env python3
"""Valida a estrutura dos workflows CI/CD."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

ROOT = Path(__file__).resolve().parents[1]
CI = ROOT / ".github" / "workflows" / "ci.yml"
CD = ROOT / ".github" / "workflows" / "cd.yml"


def load(path: Path) -> dict:
    if yaml is None:
        raise unittest.SkipTest("PyYAML não instalado (pip install pyyaml)")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise AssertionError(f"{path.name}: YAML raiz deve ser um mapping")
    return data


def all_runs(data: dict) -> str:
    jobs = data.get("jobs") or {}
    chunks: list[str] = []
    for job in jobs.values():
        for step in job.get("steps") or []:
            chunks.append(str(step.get("run", step.get("uses", ""))))
    return "\n".join(chunks)


class CiWorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = load(CI)

    def test_runs_on_github_hosted(self) -> None:
        self.assertEqual(self.data.get("name"), "CI")
        self.assertEqual(self.data["jobs"]["build"]["runs-on"], "ubuntu-latest")
        joined = all_runs(self.data)
        self.assertIn("docker compose build", joined)
        self.assertIn("from app.main import app", joined)


class CdWorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = load(CD)

    def test_manual_only_on_self_hosted(self) -> None:
        self.assertEqual(self.data.get("name"), "CD")
        on = self.data.get("on", self.data.get(True))
        self.assertIn("workflow_dispatch", on)
        self.assertEqual(
            [str(x) for x in self.data["jobs"]["deploy"]["runs-on"]],
            ["self-hosted", "42"],
        )


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
