# SPDX-License-Identifier: AGPL-3.0-or-later
"""Detect languages, package managers, and candidate commands from files.

Never executes repository code, package managers, or test runners.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from kronos_engine.domain.policy import Commands


@dataclass(frozen=True, slots=True)
class StackDetection:
    languages: tuple[str, ...]
    package_managers: tuple[str, ...]
    commands: Commands


def detect_stack(root: Path) -> StackDetection:
    languages: list[str] = []
    managers: list[str] = []
    setup: tuple[str, ...] = ()
    test: tuple[str, ...] = ()
    lint: tuple[str, ...] = ()
    build: tuple[str, ...] = ()

    package_json = root / "package.json"
    if package_json.is_file():
        languages.append("javascript")
        scripts = _package_scripts(package_json)
        if (root / "tsconfig.json").is_file() or any(root.glob("*.ts")):
            languages.append("typescript")
        if (root / "pnpm-lock.yaml").is_file():
            managers.append("pnpm")
            runner = ("pnpm",)
        elif (root / "yarn.lock").is_file():
            managers.append("yarn")
            runner = ("yarn",)
        else:
            if (root / "package-lock.json").is_file():
                managers.append("npm")
            runner = ("npm",)
        setup = (*runner, "install")
        test = _script_command(runner, scripts, "test")
        lint = _script_command(runner, scripts, "lint")
        build = _script_command(runner, scripts, "build")

    if (root / "pyproject.toml").is_file() or (root / "requirements.txt").is_file():
        languages.append("python")
        if (root / "poetry.lock").is_file():
            managers.append("poetry")
        else:
            managers.append("pip")
        setup = ("pip", "install", "-e", ".")
        pyproject_path = root / "pyproject.toml"
        pyproject = pyproject_path.read_text(encoding="utf-8") if pyproject_path.is_file() else ""
        if "pytest" in pyproject or (root / "pytest.ini").is_file():
            test = ("pytest",)
        if "[tool.ruff" in pyproject:
            lint = ("ruff", "check")

    if (root / "Cargo.toml").is_file():
        languages.append("rust")
        managers.append("cargo")
        test = ("cargo", "test")
        build = ("cargo", "build")

    if (root / "go.mod").is_file():
        languages.append("go")
        managers.append("go")
        test = ("go", "test", "./...")

    return StackDetection(
        languages=tuple(dict.fromkeys(languages)),
        package_managers=tuple(dict.fromkeys(managers)),
        commands=Commands(setup=setup, test=test, lint=lint, build=build),
    )


def _package_scripts(package_json: Path) -> dict[str, str]:
    try:
        payload = json.loads(package_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    scripts = payload.get("scripts") if isinstance(payload, dict) else None
    if not isinstance(scripts, dict):
        return {}
    return {str(name): str(body) for name, body in scripts.items()}


def _script_command(runner: tuple[str, ...], scripts: dict[str, str], name: str) -> tuple[str, ...]:
    if name not in scripts:
        return ()
    if runner == ("yarn",):
        return ("yarn", name)
    return (*runner, name)
