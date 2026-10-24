# SPDX-License-Identifier: GPL-3.0-only
"""Small, side-effect-free helpers used by Aurora Launchpad."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import shutil
import tarfile
from datetime import datetime
from pathlib import PurePosixPath


MODEL_NAMES = ("gemma3:1b-it-qat", "gemma4:e2b-it-q4_K_M")
MINIMUM_FREE_GIB = 10
# Reviewed upstream installer snapshot fetched from https://ollama.com/install.sh
# on 2026-10-23. Changing this pin requires reviewing the new root-level actions.
OLLAMA_INSTALLER_SHA256 = "25f64b810b947145095956533e1bdf56eacea2673c55a7e586be4515fc882c9f"
OLLAMA_INSTALLER_MAX_BYTES = 1_000_000
GITHUB_REPOSITORY = "Nylofofin/Aurora"
MAX_RELEASE_ARCHIVE_BYTES = 256 * 1024 * 1024
MAX_EXTRACTED_BYTES = 768 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 20_000


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


def select_latest_release(releases):
    """Return the newest published release, stable or prerelease; never a draft."""
    candidates = []
    for release in releases if isinstance(releases, list) else ():
        if not isinstance(release, dict) or release.get("draft"):
            continue
        tag = release.get("tag_name")
        published = release.get("published_at")
        if not isinstance(tag, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,99}", tag):
            continue
        if not isinstance(published, str):
            continue
        try:
            timestamp = datetime.fromisoformat(published.replace("Z", "+00:00"))
        except ValueError:
            continue
        if timestamp.tzinfo is None:
            continue
        candidates.append((timestamp, release))
    if not candidates:
        raise ValueError("Não encontrei uma release publicada válida no GitHub.")
    return max(candidates, key=lambda item: item[0])[1]


def extract_release_tarball(archive: Path, destination: Path) -> Path:
    """Safely extract a bounded GitHub source tarball without links or traversal."""
    archive = Path(archive)
    destination = Path(destination)
    if archive.stat().st_size > MAX_RELEASE_ARCHIVE_BYTES:
        raise ValueError("O arquivo da release excede o limite permitido.")
    destination.mkdir(parents=True, exist_ok=False, mode=0o700)
    total_size = 0
    files_seen = set()
    root_name = None
    try:
        with tarfile.open(archive, mode="r:gz") as bundle:
            members = bundle.getmembers()
            if not members or len(members) > MAX_ARCHIVE_MEMBERS:
                raise ValueError("A release está vazia ou contém itens demais.")
            safe_members = []
            for member in members:
                name = member.name
                path = PurePosixPath(name)
                if path.is_absolute() or ".." in path.parts or "\\" in name or not path.parts:
                    raise ValueError("A release contém um caminho inseguro.")
                if root_name is None:
                    root_name = path.parts[0]
                if path.parts[0] != root_name or member.issym() or member.islnk() or not (member.isdir() or member.isfile()):
                    raise ValueError("A release contém um item ou link não permitido.")
                if member.isfile():
                    total_size += member.size
                    if total_size > MAX_EXTRACTED_BYTES or name in files_seen:
                        raise ValueError("O conteúdo da release excede os limites ou tem caminhos duplicados.")
                    files_seen.add(name)
                safe_members.append((member, path))
            if not root_name or not any(member.isfile() for member, _ in safe_members):
                raise ValueError("A release não contém arquivos de projeto.")
            for member, relative in safe_members:
                target = destination.joinpath(*relative.parts)
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True, mode=0o700)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                source = bundle.extractfile(member)
                if source is None:
                    raise ValueError("Não consegui ler um arquivo da release.")
                with source, target.open("xb") as output:
                    shutil.copyfileobj(source, output, length=1024 * 1024)
                target.chmod(0o755 if member.mode & 0o111 else 0o644)
    except (tarfile.TarError, OSError) as exc:
        shutil.rmtree(destination, ignore_errors=True)
        raise ValueError("Não consegui validar ou extrair o arquivo da release.") from exc
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        raise
    return destination / root_name


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
    destination.chmod(0o600)
    return True


def validate_ollama_installer(script: bytes, expected_sha256: str = OLLAMA_INSTALLER_SHA256) -> None:
    """Fail closed unless the downloaded privileged script matches the reviewed snapshot."""
    if len(script) > OLLAMA_INSTALLER_MAX_BYTES:
        raise ValueError("O instalador do Ollama excede o limite de tamanho.")
    if not script.startswith(b"#!/"):
        raise ValueError("O instalador do Ollama não tem um cabeçalho de script válido.")
    actual = hashlib.sha256(script).hexdigest()
    if not hmac.compare_digest(actual, expected_sha256):
        raise ValueError("O instalador do Ollama mudou desde a revisão desta versão do Launchpad.")


def ollama_tags_response_ready(status: int, body: bytes) -> bool:
    """Recognize only a bounded, successful Ollama tags response from loopback."""
    if status != 200 or len(body) > 65_536:
        return False
    try:
        payload = json.loads(body)
    except (TypeError, ValueError):
        return False
    return isinstance(payload, dict) and isinstance(payload.get("models"), list)


def reject_symlinks_in_tree(root: Path) -> None:
    """Reject symlinks before merging a managed install tree, preventing copy-through."""
    if root.is_symlink():
        raise ValueError("A pasta da instalação contém um link simbólico.")
    if not root.exists():
        return
    for current, directories, files in os.walk(root, followlinks=False):
        for name in (*directories, *files):
            if (Path(current) / name).is_symlink():
                raise ValueError("A instalação contém um link simbólico; nenhum arquivo foi copiado.")
