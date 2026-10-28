#!/usr/bin/env python3
"""Valida que os workflows delegam aos scripts test/ (fonte única)."""

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


def runs_on(job: dict) -> list[str]:
    return [str(x) for x in job["runs-on"]]


def all_runs(data: dict) -> str:
    jobs = data.get("jobs") or {}
    chunks: list[str] = []
    for job in jobs.values():
        for step in job.get("steps") or []:
            chunks.append(str(step.get("run", step.get("uses", ""))))
    return "\n".join(chunks)


class WorkflowFilesTest(unittest.TestCase):
    def test_files_and_scripts_exist(self) -> None:
        self.assertTrue(CI.is_file())
        self.assertTrue(CD.is_file())
        self.assertTrue((ROOT / "test" / "test_ci.sh").is_file())
        self.assertTrue((ROOT / "test" / "test_cd.sh").is_file())
        self.assertTrue((ROOT / "test" / "common.sh").is_file())


class CiWorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = load(CI)

    def test_delegates_to_script(self) -> None:
        self.assertEqual(self.data.get("name"), "CI")
        self.assertEqual(runs_on(self.data["jobs"]["build"]), ["self-hosted", "42"])
        self.assertIn("./test/test_ci.sh", all_runs(self.data))


class CdWorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = load(CD)

    def test_delegates_to_script(self) -> None:
        self.assertEqual(self.data.get("name"), "CD")
        self.assertEqual(runs_on(self.data["jobs"]["deploy"]), ["self-hosted", "42"])
        self.assertIn("./test/test_cd.sh --push", all_runs(self.data))


class CommonShContractTest(unittest.TestCase):
    def test_exports_docker_host_in_shell(self) -> None:
        text = (ROOT / "test" / "common.sh").read_text(encoding="utf-8")
        self.assertIn("export DOCKER_HOST=", text)
        self.assertIn(".docker/desktop/docker.sock", text)
        self.assertIn("setup_docker", text)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
