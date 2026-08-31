# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

from tests.support.git_fixtures import init_git_repo

from kronos_engine.adapters.git.detection import detect_stack
from kronos_engine.adapters.git.repository import inspect_git


def test_inspect_git_reports_root_origin_and_branches(tmp_path: Path) -> None:
    nested = tmp_path / "widgets" / "src"
    nested.mkdir(parents=True)
    root = init_git_repo(
        tmp_path / "widgets",
        origin="https://github.com/acme/widgets.git",
        files={"README.md": "widgets\n", "src/app.py": "print(1)\n"},
    )
    snapshot = inspect_git(nested)
    assert snapshot.git_root == root.resolve()
    assert snapshot.origin == "https://github.com/acme/widgets.git"
    assert snapshot.current_branch == "main"
    assert snapshot.default_branch == "main"
    assert snapshot.realpath == root.resolve()


def test_detect_stack_reads_manifests_without_running_repo_code(tmp_path: Path) -> None:
    root = init_git_repo(
        tmp_path / "node-app",
        files={
            "package.json": (
                '{"name":"app","scripts":{"test":"node pwn.js","lint":"eslint .","build":"tsc"}}'
            ),
            "pnpm-lock.yaml": "lockfileVersion: '9.0'\n",
            "tsconfig.json": "{}\n",
            "pwn.js": "require('fs').writeFileSync('PWNED','yes')\n",
        },
    )
    stack = detect_stack(root)
    assert "javascript" in stack.languages or "typescript" in stack.languages
    assert "pnpm" in stack.package_managers
    assert stack.commands.test == ("pnpm", "test")
    assert stack.commands.lint == ("pnpm", "lint")
    assert stack.commands.build == ("pnpm", "build")
    assert stack.commands.setup == ("pnpm", "install")
    assert not (root / "PWNED").exists()


def test_detect_python_stack_from_pyproject(tmp_path: Path) -> None:
    root = init_git_repo(
        tmp_path / "py-app",
        files={
            "pyproject.toml": (
                "[project]\nname='x'\n[tool.pytest.ini_options]\ntestpaths=['tests']\n"
            ),
            "requirements.txt": "pytest\n",
        },
    )
    stack = detect_stack(root)
    assert "python" in stack.languages
    assert "pip" in stack.package_managers
    assert stack.commands.test[0:1] == ("pytest",) or "pytest" in stack.commands.test
