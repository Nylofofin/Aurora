# SPDX-License-Identifier: GPL-3.0-only
"""Small, side-effect-free helpers used by Aurora Launchpad."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil


MODEL_NAMES = ("gemma3:1b-it-qat", "gemma4:e2b-it-q4_K_M")
MINIMUM_FREE_GIB = 10


@dataclass(frozen=True)
class EnvironmentReport:
    supported: bool
    distro: str
    session: str
    desktop: str
    memory_gib: float
    free_gib: float
    warnings: tuple[str, ...]


def assess_environment(
    os_release: dict[str, str],
    env: dict[str, str],
    memory_bytes: int,
    free_bytes: int,
) -> EnvironmentReport:
    distro = os_release.get("PRETTY_NAME", os_release.get("NAME", "Linux"))
    session = env.get("XDG_SESSION_TYPE", "desconhecida").lower()
    desktop = env.get("XDG_CURRENT_DESKTOP", env.get("XDG_SESSION_DESKTOP", "desconhecido"))
    gnome = "gnome" in desktop.lower() or "gnome" in env.get("XDG_SESSION_DESKTOP", "").lower()
    workstation = os_release.get("ID", "").lower() == "fedora" and os_release.get("VARIANT_ID", "").lower() == "workstation"
    supported = workstation and session == "wayland" and gnome
    memory_gib = memory_bytes / (1024**3)
    free_gib = free_bytes / (1024**3)
    warnings = []
    if memory_gib < 8:
        warnings.append("Menos de 8 GiB de RAM; os modelos podem ficar lentos ou não carregar.")
    if free_gib < MINIMUM_FREE_GIB:
        warnings.append(f"Espaço insuficiente: reserve pelo menos {MINIMUM_FREE_GIB} GiB livres para os modelos e dependências.")
    return EnvironmentReport(supported, distro, session, desktop, memory_gib, free_gib, tuple(warnings))


def parse_ollama_models(output: str) -> set[str]:
    """Parse the name column from ``ollama list`` output."""
    lines = output.splitlines()
    return {line.split()[0] for line in lines[1:] if line.split() and line.split()[0] != "NAME"}


def missing_models(output: str) -> tuple[str, ...]:
    present = parse_ollama_models(output)
    return tuple(name for name in MODEL_NAMES if name not in present)


def format_size(num_bytes: int) -> str:
    value = float(num_bytes)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{value:.1f} TiB"


def remove_owned_models(ollama_binary: str, manifest_path: Path, run) -> list[str]:
    """Remove only model tags the installer recorded as newly downloaded."""
    if not manifest_path.is_file():
        return []
    names = [line.strip() for line in manifest_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    removed = []
    for name in names:
        if name in MODEL_NAMES:
            run([ollama_binary, "rm", name])
            removed.append(name)
    manifest_path.unlink(missing_ok=True)
    return removed


def disk_free_bytes(path: Path) -> int:
    return shutil.disk_usage(path).free


def copy_existing_memory(old_root: Path, new_root: Path) -> bool:
    """Copy user memory into a new managed install without deleting the source."""
    source = old_root / "aurora-memory.json"
    destination = new_root / "aurora-memory.json"
    if not source.is_file() or source.is_symlink() or destination.exists():
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return True
