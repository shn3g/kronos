# SPDX-License-Identifier: AGPL-3.0-or-later
"""Opt-in local embedding model install from a pinned, checksummed catalog."""

from __future__ import annotations

import hashlib
import shutil
import threading
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from urllib.request import Request

from kronos_engine.adapters.embeddings.local import (
    DOCUMENT_FILENAME,
    DOCUMENT_MODEL_ID,
    DOCUMENT_MODEL_LICENSE,
    TOKENIZER_FILENAME,
    EmbeddingModelConfig,
    LocalEmbeddingAdapter,
)

EMBEDDING_INSTALL_POLICY = (
    "Kronos downloads model weights only when you click Install, "
    "from pinned URLs verified by SHA-256."
)

ACTIVE_KEY_FILENAME = ".active-key"
InstallState = Literal["idle", "downloading", "verifying", "ready", "failed"]

_MINILM_REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
_BGE_REVISION = "5c38ec7c405ec4b44b94cc5a9bb96e735b38267a"


@dataclass(frozen=True, slots=True)
class CatalogFile:
    url: str
    sha256: str
    dest: str


@dataclass(frozen=True, slots=True)
class CatalogEntry:
    key: str
    dim: int
    display_name: str
    document_model_id: str
    document_filename: str
    document_license: str
    files: tuple[CatalogFile, ...]


def catalog_entry(
    *,
    key: str,
    dim: int,
    display_name: str,
    document_model_id: str,
    document_filename: str,
    document_license: str,
    files: tuple[tuple[str, str, str], ...],
) -> CatalogEntry:
    return CatalogEntry(
        key=key,
        dim=dim,
        display_name=display_name,
        document_model_id=document_model_id,
        document_filename=document_filename,
        document_license=document_license,
        files=tuple(CatalogFile(url=url, sha256=sha256, dest=dest) for url, sha256, dest in files),
    )


def default_catalog() -> dict[str, CatalogEntry]:
    return {
        "minilm-l6-v2": catalog_entry(
            key="minilm-l6-v2",
            dim=384,
            display_name="MiniLM L6 v2",
            document_model_id=DOCUMENT_MODEL_ID,
            document_filename=DOCUMENT_FILENAME,
            document_license=DOCUMENT_MODEL_LICENSE,
            files=(
                (
                    "https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2"
                    f"/resolve/{_MINILM_REVISION}/onnx/model.onnx",
                    "6fd5d72fe4589f189f8ebc006442dbb529bb7ce38f8082112682524616046452",
                    DOCUMENT_FILENAME,
                ),
                (
                    "https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2"
                    f"/resolve/{_MINILM_REVISION}/tokenizer.json",
                    "be50c3628f2bf5bb5e3a7f17b1f74611b2561a3a27eeab05e5aa30f411572037",
                    TOKENIZER_FILENAME,
                ),
            ),
        ),
        "bge-small-en-v1.5": catalog_entry(
            key="bge-small-en-v1.5",
            dim=384,
            display_name="bge-small-en-v1.5",
            document_model_id="BAAI/bge-small-en-v1.5",
            document_filename="model.onnx",
            document_license="MIT",
            files=(
                (
                    "https://huggingface.co/BAAI/bge-small-en-v1.5"
                    f"/resolve/{_BGE_REVISION}/onnx/model.onnx",
                    "828e1496d7fabb79cfa4dcd84fa38625c0d3d21da474a00f08db0f559940cf35",
                    "model.onnx",
                ),
                (
                    "https://huggingface.co/BAAI/bge-small-en-v1.5"
                    f"/resolve/{_BGE_REVISION}/tokenizer.json",
                    "d241a60d5e8f04cc1b2b3e9ef7a4921b27bf526d9f6050ab90f9267a1f9e5c66",
                    TOKENIZER_FILENAME,
                ),
            ),
        ),
    }


def resolve_local_models_dir(models_root: Path) -> tuple[Path, str | None]:
    models_root.mkdir(parents=True, exist_ok=True)
    active = _read_active_key(models_root)
    if active and _is_installed(models_root, active):
        return models_root / active, active
    if _legacy_installed(models_root):
        return models_root, None
    for key in default_catalog():
        if _is_installed(models_root, key):
            return models_root / key, key
    return models_root, None


def local_adapter_for(key: str | None, model_dir: Path) -> LocalEmbeddingAdapter:
    if key is None:
        return LocalEmbeddingAdapter(model_dir)
    entry = default_catalog().get(key)
    if entry is None:
        return LocalEmbeddingAdapter(model_dir)
    return LocalEmbeddingAdapter(
        model_dir,
        document=EmbeddingModelConfig(
            model_id=entry.document_model_id,
            license=entry.document_license,
            filename=entry.document_filename,
            sha256=_entry_sha256(entry, entry.document_filename),
        ),
    )


class EmbeddingInstaller:
    def __init__(
        self,
        models_root: Path,
        *,
        catalog: Mapping[str, CatalogEntry] | None = None,
        urlopen: Callable[[Request], Any] | None = None,
    ) -> None:
        self._models_root = models_root
        self._catalog = dict(catalog or default_catalog())
        self._urlopen = urlopen or urllib.request.urlopen
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._state: InstallState = "idle"
        self._model_key: str | None = None
        self._bytes_done = 0
        self._bytes_total = 0
        self._error: str | None = None

    def catalog(self) -> tuple[CatalogEntry, ...]:
        return tuple(self._catalog[key] for key in sorted(self._catalog))

    def is_installed(self, key: str) -> bool:
        return _is_installed(self._models_root, key, self._catalog)

    def installed_keys(self) -> list[str]:
        return [key for key in self._catalog if self.is_installed(key)]

    def active_key(self) -> str | None:
        active = _read_active_key(self._models_root)
        if active and self.is_installed(active):
            return active
        return None

    def start(self, key: str) -> None:
        if key not in self._catalog:
            raise KeyError(key)
        if self.is_installed(key):
            raise RuntimeError("already installed")
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                raise RuntimeError("install already in progress")
            self._state = "downloading"
            self._model_key = key
            self._bytes_done = 0
            self._bytes_total = 0
            self._error = None
            self._thread = threading.Thread(
                target=self._run_install,
                args=(key,),
                daemon=True,
                name=f"kronos-embed-install-{key}",
            )
            self._thread.start()

    def status(self) -> dict[str, object]:
        with self._lock:
            return {
                "state": self._state,
                "bytes_done": self._bytes_done,
                "bytes_total": self._bytes_total,
                "model_key": self._model_key,
                "error": self._error,
            }

    def remove(self, key: str) -> None:
        if key not in self._catalog:
            raise KeyError(key)
        with self._lock:
            if self._thread is not None and self._thread.is_alive() and self._model_key == key:
                raise RuntimeError("cannot remove model while install is in progress")
        target = self._models_root / key
        if target.exists():
            shutil.rmtree(target)
        if _read_active_key(self._models_root) == key:
            _clear_active_key(self._models_root)
        with self._lock:
            if self._model_key == key and self._state in {"ready", "failed"}:
                self._state = "idle"
                self._model_key = None
                self._bytes_done = 0
                self._bytes_total = 0
                self._error = None

    def _run_install(self, key: str) -> None:
        entry = self._catalog[key]
        dest_dir = self._models_root / key
        staging = dest_dir.with_suffix(".staging")
        try:
            total = 0
            for spec in entry.files:
                total += _remote_size(spec.url, self._urlopen)
            with self._lock:
                self._bytes_total = total
            if staging.exists():
                shutil.rmtree(staging)
            staging.mkdir(parents=True, exist_ok=True)
            for spec in entry.files:
                part = staging / f"{spec.dest}.part"
                final = staging / spec.dest
                self._download(spec.url, part)
                with self._lock:
                    self._state = "verifying"
                digest = _sha256_file(part)
                if digest != spec.sha256.lower():
                    raise ValueError(f"checksum mismatch for {spec.dest}")
                part.replace(final)
            if dest_dir.exists():
                shutil.rmtree(dest_dir)
            staging.replace(dest_dir)
            _write_active_key(self._models_root, key)
            with self._lock:
                self._state = "ready"
                self._error = None
        except Exception as exc:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)
            with self._lock:
                self._state = "failed"
                self._error = str(exc)
        finally:
            with self._lock:
                self._thread = None

    def _download(self, url: str, dest: Path) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        request = Request(url, headers={"User-Agent": "kronos-engine/embedding-install"})
        with self._urlopen(request) as response:
            with dest.open("wb") as handle:
                while True:
                    block = response.read(1024 * 1024)
                    if not block:
                        break
                    handle.write(block)
                    with self._lock:
                        self._bytes_done += len(block)
                        self._state = "downloading"


def _legacy_installed(models_root: Path) -> bool:
    return (models_root / DOCUMENT_FILENAME).is_file() and (
        models_root / TOKENIZER_FILENAME
    ).is_file()


def _is_installed(
    models_root: Path,
    key: str,
    catalog: Mapping[str, CatalogEntry] | None = None,
) -> bool:
    entries = catalog or default_catalog()
    entry = entries.get(key)
    if entry is None:
        return False
    dest_dir = models_root / key
    return all((dest_dir / spec.dest).is_file() for spec in entry.files)


def _entry_sha256(entry: CatalogEntry, dest: str) -> str:
    for spec in entry.files:
        if spec.dest == dest:
            return spec.sha256
    return ""


def _read_active_key(models_root: Path) -> str | None:
    path = models_root / ACTIVE_KEY_FILENAME
    if not path.is_file():
        return None
    key = path.read_text(encoding="utf-8").strip()
    return key or None


def _write_active_key(models_root: Path, key: str) -> None:
    models_root.mkdir(parents=True, exist_ok=True)
    (models_root / ACTIVE_KEY_FILENAME).write_text(key, encoding="utf-8")


def _clear_active_key(models_root: Path) -> None:
    path = models_root / ACTIVE_KEY_FILENAME
    if path.is_file():
        path.unlink()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            block = handle.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def _remote_size(url: str, urlopen: Callable[[Request], Any]) -> int:
    request = Request(url, method="HEAD", headers={"User-Agent": "kronos-engine/embedding-install"})
    try:
        with urlopen(request) as response:
            length = response.headers.get("Content-Length")
            if length is not None:
                return max(0, int(length))
    except Exception:
        return 0
    return 0
