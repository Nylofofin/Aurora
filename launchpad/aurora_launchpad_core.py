# SPDX-License-Identifier: GPL-3.0-only
"""Small, side-effect-free helpers used by Aurora Launchpad."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
import os
import tempfile
from pathlib import Path
import re
import shutil
import tarfile
from datetime import datetime
from pathlib import PurePosixPath
from urllib.parse import urlsplit


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
MAX_LAUNCHPAD_RPM_BYTES = 64 * 1024 * 1024
OFFICIAL_GITHUB_DOWNLOAD_HOSTS = frozenset({
    "github.com",
    "objects.githubusercontent.com",
    "github-releases.githubusercontent.com",
    # GitHub redirects release assets here before streaming the bytes.
    "release-assets.githubusercontent.com",
})


def is_official_github_download_url(value: str) -> bool:
    """Accept only HTTPS download hosts used by GitHub's release pipeline."""
    try:
        parsed = urlsplit(str(value or ""))
    except ValueError:
        return False
    return parsed.scheme == "https" and parsed.hostname in OFFICIAL_GITHUB_DOWNLOAD_HOSTS


def prepare_first_boot_onboarding(config_path: Path, boot_id: str, *, existing_install: bool,
                                  session_id: str = "") -> bool:
    """Mark a fresh install for onboarding after the next login session."""
    if existing_install or not boot_id:
        return False
    path = Path(config_path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.parent.is_symlink():
        raise ValueError("A pasta de configurações é um link simbólico.")
    path.parent.chmod(0o700)
    if path.is_symlink():
        raise ValueError("O arquivo de configurações é um link simbólico.")
    try:
        settings = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("Não consegui ler as configurações existentes da Aurora.") from exc
    if not isinstance(settings, dict):
        raise ValueError("O arquivo de configurações não contém um objeto JSON.")
    settings["onboarding_pending"] = True
    settings["onboarding_boot_id"] = str(boot_id)
    settings["onboarding_session_id"] = str(session_id or os.environ.get("XDG_SESSION_ID", ""))
    fd, temporary_name = tempfile.mkstemp(prefix=".aurora-settings-", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(settings, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    path.chmod(0o600)
    return True


def schedule_personalization(config_path: Path, session_id: str = "") -> bool:
    """Request the profile wizard again without touching existing choices."""
    path = Path(config_path)
    try:
        settings = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("Não consegui ler as configurações da Aurora.") from exc
    if not isinstance(settings, dict):
        raise ValueError("O arquivo de configurações não contém um objeto JSON.")
    settings["onboarding_pending"] = True
    settings["onboarding_session_id"] = "reopen:" + str(session_id or "launchpad")
    fd, temporary_name = tempfile.mkstemp(prefix=".aurora-settings-", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(settings, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    path.chmod(0o600)
    return True


@dataclass(frozen=True)
class EnvironmentReport:
    supported: bool
    distro: str
    session: str
    desktop: str
    memory_gib: float
    free_gib: float
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class ReleaseRecommendation:
    """A release chosen for a clearly described installer channel."""

    channel: str
    release: dict


@dataclass(frozen=True)
class InstallationHealth:
    """Read-only diagnosis of the managed Aurora payload and user service."""

    state: str
    details: tuple[str, ...]
    repairable: bool


def _rpm_version_key(value: str) -> tuple[int, ...] | None:
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", str(value or "").strip())
    return tuple(int(part) for part in match.groups()) if match else None


def latest_launchpad_update(releases, current_version: str) -> dict | None:
    """Return the newest published Launchpad RPM newer than ``current_version``.

    Release metadata is untrusted: only an exact RPM filename, a GitHub release
    download URL and a SHA-256 digest are accepted.  The caller still verifies
    the bytes before asking dnf to install them.
    """
    current = _rpm_version_key(current_version)
    if current is None:
        return None
    candidates: list[tuple[tuple[int, ...], str, dict, dict]] = []
    for release in releases if isinstance(releases, list) else ():
        if not isinstance(release, dict) or release.get("draft") or release.get("prerelease"):
            continue
        published = str(release.get("published_at") or "")
        for asset in release.get("assets") if isinstance(release.get("assets"), list) else ():
            if not isinstance(asset, dict):
                continue
            name = asset.get("name")
            match = re.fullmatch(r"aurora-launchpad-(\d+\.\d+\.\d+)-[^/]+\.noarch\.rpm", str(name or ""))
            version = _rpm_version_key(match.group(1)) if match else None
            url = asset.get("browser_download_url")
            digest = asset.get("digest")
            size = asset.get("size")
            if (version is None or version <= current or not isinstance(url, str)
                    or not re.fullmatch(r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/releases/download/[A-Za-z0-9._+-]+/[^/]+", url)
                    or not isinstance(digest, str) or not re.fullmatch(r"sha256:[0-9a-fA-F]{64}", digest)
                    or not isinstance(size, int) or size <= 0 or size > MAX_LAUNCHPAD_RPM_BYTES):
                continue
            candidates.append((version, published, release, asset))
    if not candidates:
        return None
    _, _, release, asset = max(candidates, key=lambda item: (item[0], item[1]))
    return {"release": release, "asset": asset}


def newer_aurora_releases(releases, installed_version: str, limit: int = 3) -> tuple[dict, ...]:
    """Return at most ``limit`` published Aurora builds newer than installed."""
    current = _rpm_version_key(installed_version)
    if current is None or not isinstance(limit, int) or limit < 1:
        return ()
    candidates: list[tuple[tuple[int, ...], str, dict]] = []
    for release in releases if isinstance(releases, list) else ():
        if not isinstance(release, dict) or release.get("draft"):
            continue
        tag = release.get("tag_name")
        match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)(?:[-+][A-Za-z0-9.-]+)?", str(tag or ""))
        published = str(release.get("published_at") or "")
        if not match or not isinstance(release.get("prerelease"), bool):
            continue
        version = tuple(int(part) for part in match.groups())
        if version <= current:
            continue
        candidates.append((version, published, release))
    candidates.sort(key=lambda item: (item[0], item[1], item[2].get("tag_name", "")), reverse=True)
    return tuple(item[2] for item in candidates[:limit])


def release_channel_label(release: dict) -> str:
    """Describe a published build's stability channel in plain language."""
    if not isinstance(release, dict) or not isinstance(release.get("prerelease"), bool):
        return "Canal não informado"
    return "Pré-release · experimental" if release["prerelease"] else "Release · estável"


def inspect_installation(managed_app: Path, unit_path: Path, *, service_active: bool) -> InstallationHealth:
    """Classify an installation without starting processes or changing files."""
    managed_app = Path(managed_app)
    unit_path = Path(unit_path)
    required = ("aurora.py", "run.sh", "start-alpha.sh", "install-desktop.sh")
    missing = tuple(name for name in required if not (managed_app / name).is_file())
    details: list[str] = []
    if not managed_app.is_dir():
        return InstallationHealth("missing", ("A pasta gerenciada da Aurora não existe.",), False)
    if missing:
        details.append("Arquivos ausentes: " + ", ".join(missing) + ".")
    if not unit_path.is_file():
        details.append("O serviço aurora.service não está configurado.")
    else:
        try:
            unit = unit_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            unit = ""
        expected = str(managed_app)
        if f"WorkingDirectory={expected}" not in unit or f"ExecStart={expected}/start-alpha.sh" not in unit:
            details.append("O serviço aponta para uma pasta diferente da instalação gerenciada.")
    if not service_active:
        details.append("O serviço não está ativo.")
    if missing:
        return InstallationHealth("broken", tuple(details), False)
    if details:
        return InstallationHealth("repairable", tuple(details), True)
    return InstallationHealth("healthy", ("Arquivos e serviço estão coerentes.",), True)


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


def recommend_releases(releases) -> tuple[ReleaseRecommendation, ...]:
    """Recommend newest prerelease, its preceding prerelease, and newest stable."""
    candidates: dict[str, tuple[datetime, dict]] = {}
    for release in releases if isinstance(releases, list) else ():
        if not isinstance(release, dict) or release.get("draft"):
            continue
        tag = release.get("tag_name")
        published = release.get("published_at")
        if not isinstance(tag, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,99}", tag):
            continue
        if not isinstance(published, str) or not isinstance(release.get("prerelease"), bool):
            continue
        try:
            timestamp = datetime.fromisoformat(published.replace("Z", "+00:00"))
        except ValueError:
            continue
        if timestamp.tzinfo is None:
            continue
        previous = candidates.get(tag)
        if previous is None or timestamp > previous[0]:
            candidates[tag] = (timestamp, release)

    prereleases = sorted(
        (item for item in candidates.values() if item[1]["prerelease"]),
        key=lambda item: (item[0], item[1]["tag_name"]),
        reverse=True,
    )
    stable = sorted(
        (item for item in candidates.values() if not item[1]["prerelease"]),
        key=lambda item: (item[0], item[1]["tag_name"]),
        reverse=True,
    )
    result = []
    if prereleases:
        result.append(ReleaseRecommendation("latest_prerelease", prereleases[0][1]))
        if len(prereleases) > 1:
            result.append(ReleaseRecommendation("previous_prerelease", prereleases[1][1]))
    if stable:
        result.append(ReleaseRecommendation("latest_stable", stable[0][1]))
    return tuple(result)


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


def ollama_storage_creation_command(
    path: Path, *, service_uid: int, service_gid: int
) -> list[str] | None:
    """Return a narrowly scoped mkdir command, or fail on unsafe existing paths."""
    path = Path(path)
    if path.is_symlink():
        raise ValueError("A pasta de dados do Ollama é um link simbólico; não vou alterá-la.")
    if path.exists():
        if not path.is_dir():
            raise ValueError("O caminho de dados do Ollama existe, mas não é uma pasta.")
        details = path.stat()
        if details.st_uid != service_uid or details.st_gid != service_gid:
            raise ValueError("A pasta de dados do Ollama tem proprietário inesperado; verifique-a manualmente.")
        return None
    return [
        "/usr/bin/install", "-d", "-o", str(service_uid), "-g", str(service_gid),
        "-m", "0755", str(path),
    ]


def reject_symlinks_in_tree(root: Path, *, ignored_directories: set[str] | None = None) -> None:
    """Reject symlinks before merging a managed tree, except named data dirs."""
    if root.is_symlink():
        raise ValueError("A pasta da instalação contém um link simbólico.")
    if not root.exists():
        return
    ignored_directories = ignored_directories or set()
    for current, directories, files in os.walk(root, followlinks=False):
        directories[:] = [name for name in directories if name not in ignored_directories]
        for name in (*directories, *files):
            if (Path(current) / name).is_symlink():
                raise ValueError("A instalação contém um link simbólico; nenhum arquivo foi copiado.")
