#!/usr/bin/env python3
"""Valida a estrutura dos workflows de CI/CD antes do push (sem Docker)."""

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


def trigger_block(data: dict) -> dict:
    """PyYAML 1.1 interpreta a chave `on` como True."""
    block = data.get("on", data.get(True))
    if not isinstance(block, dict):
        raise AssertionError("bloco on/True ausente ou inválido")
    return block


def runs_on(job: dict) -> list[str]:
    return [str(x) for x in job["runs-on"]]


class WorkflowFilesTest(unittest.TestCase):
    def test_workflow_files_exist(self) -> None:
        self.assertTrue(CI.is_file(), f"faltando {CI}")
        self.assertTrue(CD.is_file(), f"faltando {CD}")


class CiWorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = load(CI)

    def test_name_and_runner(self) -> None:
        self.assertEqual(self.data.get("name"), "CI")
        jobs = self.data["jobs"]
        self.assertIn("build", jobs)
        self.assertEqual(runs_on(jobs["build"]), ["self-hosted", "42"])

    def test_has_docker_build_and_import_check(self) -> None:
        steps = self.data["jobs"]["build"]["steps"]
        joined = "\n".join(str(s.get("run", s.get("uses", ""))) for s in steps)
        self.assertIn('"${DOCKER}" compose build', joined)
        self.assertIn("from app.main import app", joined)
        self.assertIn("DOCKER_HOST", joined)
        self.assertIn("GITHUB_PATH", joined)
        self.assertIn("/usr/bin/docker", joined)


class CdWorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = load(CD)

    def test_name_and_runner(self) -> None:
        self.assertEqual(self.data.get("name"), "CD")
        jobs = self.data["jobs"]
        self.assertIn("deploy", jobs)
        self.assertEqual(runs_on(jobs["deploy"]), ["self-hosted", "42"])

    def test_triggers_after_ci(self) -> None:
        on = trigger_block(self.data)
        self.assertIn("workflow_run", on)
        self.assertEqual(on["workflow_run"]["workflows"], ["CI"])
        self.assertIn("workflow_dispatch", on)

    def test_has_tag_push_deploy_health(self) -> None:
        steps = self.data["jobs"]["deploy"]["steps"]
        joined = "\n".join(str(s.get("run", s.get("uses", ""))) for s in steps)
        self.assertIn('"${DOCKER}" tag', joined)
        self.assertIn('"${DOCKER}" push', joined)
        self.assertIn('"${DOCKER}" compose up -d', joined)
        self.assertIn("/api/health", joined)
        self.assertIn("GITHUB_PATH", joined)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
