"""Safe extraction helpers for downloaded model archives."""
# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

from pathlib import Path, PurePosixPath
import shutil
import stat
import zipfile


MAX_ARCHIVE_FILES = 10_000
MAX_ARCHIVE_UNPACKED_BYTES = 256 * 1024 * 1024


def extract_zip_safely(archive: str | Path, destination: str | Path,
                       max_unpacked_bytes: int = MAX_ARCHIVE_UNPACKED_BYTES) -> None:
    """Extract regular ZIP files under a fresh destination, rejecting traversal."""
    root = Path(destination)
    if root.is_symlink():
        raise ValueError("A pasta temporária de extração não pode ser um link simbólico.")
    root.mkdir(parents=True, exist_ok=True)
    root = root.resolve(strict=True)
    if any(root.iterdir()):
        raise ValueError("A pasta temporária de extração precisa estar vazia.")
    with zipfile.ZipFile(archive) as zipped:
        members = zipped.infolist()
        if len(members) > MAX_ARCHIVE_FILES:
            raise ValueError("O arquivo contém entradas demais.")
        declared_size = sum(info.file_size for info in members)
        if declared_size > max_unpacked_bytes:
            raise ValueError("O conteúdo descompactado excede o limite permitido.")

        normalized: set[str] = set()
        for info in members:
            raw_name = info.filename
            parts = raw_name.split("/")
            path = PurePosixPath(raw_name)
            if (not raw_name or raw_name.startswith("/") or "\\" in raw_name
                    or any(part in ("", ".", "..") for part in parts if part)
                    or path.is_absolute() or (path.parts and ":" in path.parts[0])):
                raise ValueError("O arquivo contém um caminho de extração inválido.")
            key = "/".join(path.parts)
            if key in normalized:
                raise ValueError("O arquivo contém caminhos duplicados.")
            normalized.add(key)

            mode = info.external_attr >> 16
            kind = stat.S_IFMT(mode)
            if stat.S_ISLNK(mode) or kind not in (0, stat.S_IFREG, stat.S_IFDIR):
                raise ValueError("O arquivo contém um tipo de entrada não permitido.")
            if info.is_dir():
                target = root.joinpath(*path.parts)
                target.mkdir(parents=True, exist_ok=True)
                if not target.resolve(strict=True).is_relative_to(root):
                    raise ValueError("O caminho de extração saiu da pasta temporária.")
                continue

            target = root.joinpath(*path.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            resolved_parent = target.parent.resolve(strict=True)
            if not resolved_parent.is_relative_to(root):
                raise ValueError("O caminho de extração saiu da pasta temporária.")
            written = 0
            with zipped.open(info) as source, target.open("xb") as output:
                while True:
                    chunk = source.read(64 * 1024)
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > info.file_size or written > max_unpacked_bytes:
                        raise ValueError("O arquivo excede o tamanho declarado ou permitido.")
                    output.write(chunk)
            if written != info.file_size:
                raise ValueError("O arquivo extraído não corresponde ao tamanho declarado.")

