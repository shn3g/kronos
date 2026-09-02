# SPDX-License-Identifier: AGPL-3.0-or-later
"""Build a PyInstaller onedir engine bundle for the desktop installer."""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def bundle_target() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == "linux":
        return f"linux-{machine}"
    if system == "darwin":
        return f"darwin-{machine}"
    if system == "windows":
        return "windows-x64" if machine in {"amd64", "x86_64"} else f"windows-{machine}"
    return f"{system}-{machine}"


def stage_root(root: Path) -> Path:
    return root / "apps" / "desktop" / "src-tauri" / "engine"


def ensure_pyinstaller() -> None:
    try:
        import PyInstaller  # noqa: F401
    except ImportError as exc:
        raise SystemExit(
            "PyInstaller is required. Install with: python -m pip install pyinstaller"
        ) from exc


def run_pyinstaller(engine_dir: Path, *, clean: bool) -> Path:
    spec = engine_dir / "kronos_engine.spec"
    if not spec.is_file():
        raise SystemExit(f"Missing PyInstaller spec: {spec}")

    dist_dir = engine_dir / "dist"
    build_dir = engine_dir / "build"
    if clean and dist_dir.exists():
        shutil.rmtree(dist_dir)
    if clean and build_dir.exists():
        shutil.rmtree(build_dir)

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        str(spec),
        "--noconfirm",
        "--distpath",
        str(dist_dir),
        "--workpath",
        str(build_dir),
    ]
    subprocess.run(command, cwd=engine_dir, check=True)

    onedir = dist_dir / "kronos-engine"
    binary_name = "kronos-engine.exe" if os.name == "nt" else "kronos-engine"
    binary = onedir / binary_name
    if not binary.is_file():
        raise SystemExit(f"PyInstaller onedir binary not found: {binary}")
    return onedir


def copy_tree(source: Path, destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination)


def link_or_copy(source: Path, destination: Path) -> None:
    if destination.exists() or destination.is_symlink():
        if destination.is_dir() and not destination.is_symlink():
            shutil.rmtree(destination)
        else:
            destination.unlink()
    try:
        destination.symlink_to(source, target_is_directory=True)
    except OSError:
        copy_tree(source, destination)


def stage_bundle(onedir: Path, *, target: str, root: Path) -> Path:
    stage = stage_root(root)
    target_dir = stage / target / "kronos-engine"
    bundle_link = stage / "kronos-engine"

    stage.mkdir(parents=True, exist_ok=True)
    copy_tree(onedir, target_dir)
    link_or_copy(target_dir, bundle_link)

    binary_name = "kronos-engine.exe" if os.name == "nt" else "kronos-engine"
    staged_binary = bundle_link / binary_name
    if not staged_binary.is_file():
        raise SystemExit(f"Staged engine binary not found: {staged_binary}")
    return staged_binary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove previous PyInstaller build artifacts before building.",
    )
    parser.add_argument(
        "--target",
        default=None,
        help="Bundle target folder name (default: auto-detect from the host OS).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = repo_root()
    engine_dir = root / "engine"
    target = args.target or bundle_target()

    ensure_pyinstaller()
    onedir = run_pyinstaller(engine_dir, clean=args.clean)
    staged_binary = stage_bundle(onedir, target=target, root=root)
    print(f"Bundled engine ready at {staged_binary}")


if __name__ == "__main__":
    main()
