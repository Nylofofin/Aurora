#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-only
"""Animated Fedora Workstation setup wizard for Aurora Desktop."""
from __future__ import annotations

import os
import grp
import hashlib
import hmac
from pathlib import Path
import http.client
import pwd
import queue
import shutil
import subprocess
import tempfile
import threading
import time
import json
import re
from datetime import datetime
from urllib.parse import quote, urlsplit
import urllib.request

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from aurora_launchpad_core import (
    MODEL_NAMES,
    OLLAMA_INSTALLER_MAX_BYTES,
    OLLAMA_INSTALLER_SHA256,
    assess_environment,
    copy_existing_memory,
    disk_free_bytes,
    extract_release_tarball,
    format_size,
    missing_models,
    ollama_tags_response_ready,
    reject_symlinks_in_tree,
    remove_owned_models,
    recommend_releases,
    ollama_storage_creation_command,
    validate_ollama_installer,
    GITHUB_REPOSITORY,
    MAX_RELEASE_ARCHIVE_BYTES,
    inspect_installation,
    voice_assets_ready,
    is_official_github_download_url,
    latest_launchpad_update,
    newer_aurora_releases,
    MAX_LAUNCHPAD_RPM_BYTES,
    parse_ollama_models,
    prepare_first_boot_onboarding,
    schedule_personalization,
    InstallationHealth,
)


APP_ID = "com.nylofofin.AuroraLaunchpad"
INSTALLER_VERSION = "0.5.4"
PKEXEC = "/usr/bin/pkexec"
SYSTEMCTL = "/usr/bin/systemctl"
DNF = "/usr/bin/dnf"
SYSTEM_PATH = "/usr/local/bin:/usr/bin:/bin"
MANAGED_APP = Path.home() / ".local/share/aurora"
OWNED_MODELS = Path.home() / ".local/share/aurora-launchpad/owned-models.txt"
PRESERVED_MEMORY = Path.home() / ".local/share/aurora-launchpad/aurora-memory.json"
CSS = """
window.launchpad { background: #0e0e14; color: #f6f3fb; }
headerbar { background: #111117; border-bottom: 1px solid #282631; min-height: 48px; }
.hero { background: linear-gradient(135deg, #211a2d, #17151d 74%); border: 1px solid #393143; border-radius: 22px; padding: 21px; }
.panel { background: #17171f; border: 1px solid #302e39; border-radius: 20px; padding: 17px; }
.release-card { background: #1a1922; border: 1px solid #35313f; border-radius: 18px; padding: 15px; transition: background 160ms ease, border-color 160ms ease; }
button.release-card:hover { background: #24212e; border-color: #73608c; }
button.release-card.selected { background: #2a2239; border: 2px solid #b79be8; }
.subtle { color: #b9b3c3; }
.caption { color: #b7a9ce; font-size: 10px; letter-spacing: .10em; font-weight: 700; }
.brand-mark { color: #d6c1ff; background: #312741; border: 1px solid #514263; border-radius: 12px; min-width: 30px; min-height: 30px; font-size: 18px; font-weight: 800; }
.brand-title { color: #f6f3fb; font-size: 14px; font-weight: 700; }
.brand-subtitle { color: #aaa2b5; font-size: 10px; }
.title-1 { font-size: 25px; font-weight: 750; letter-spacing: -.025em; }
.title-2 { font-size: 16px; font-weight: 700; }
.status-good { color: #8ce4c4; }
.status-bad { color: #ff9b9b; }
.status-warn { color: #f0cb81; }
.step { color: #c5bfce; font-size: 12px; }
.log { font-family: monospace; font-size: 10px; color: #c5bfce; }
progressbar trough { min-height: 8px; border-radius: 99px; background: #302d3a; }
progressbar progress { min-height: 8px; border-radius: 99px; background: #a98ade; }
button { color: #f2edf8; border-radius: 14px; min-height: 38px; padding: 7px 15px; }
button:hover { background: #292630; }
button.suggested-action { background: #8b6bc2; color: #ffffff; font-weight: 700; }
button.suggested-action:hover { background: #a17bd8; }
button.pill { border-radius: 999px; }
checkbutton { color: #ddd7e6; }
"""


def read_os_release() -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        for line in Path("/etc/os-release").read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.startswith("#"):
                key, value = line.split("=", 1)
                values[key] = value.strip().strip('"')
    except OSError:
        pass
    return values


def memory_total_bytes() -> int:
    try:
        for line in Path("/proc/meminfo").read_text(encoding="ascii").splitlines():
            if line.startswith("MemTotal:"):
                return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        pass
    return 0


def ollama_api_ready(timeout: float = 1.0) -> bool:
    connection = http.client.HTTPConnection("127.0.0.1", 11434, timeout=timeout)
    try:
        connection.request("GET", "/api/tags", headers={"Host": "127.0.0.1:11434"})
        response = connection.getresponse()
        body = response.read(65_537)
        return ollama_tags_response_ready(response.status, body)
    except (OSError, http.client.HTTPException):
        return False
    finally:
        connection.close()


def _github_json(url: str, *, maximum: int = 4 * 1024 * 1024) -> dict | list:
    request = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": f"Aurora-Launchpad/{INSTALLER_VERSION}",
        "X-GitHub-Api-Version": "2022-11-28",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    })
    with urllib.request.urlopen(request, timeout=20) as response:
        if response.status != 200:
            raise RuntimeError(f"GitHub respondeu HTTP {response.status}.")
        content = response.read(maximum + 1)
    if len(content) > maximum:
        raise RuntimeError("A resposta do GitHub excede o limite permitido.")
    try:
        return json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("O GitHub retornou metadados inválidos.") from exc


def fetch_release_recommendations():
    """Fetch and classify the three release choices shown by Launchpad."""
    api = f"https://api.github.com/repos/{GITHUB_REPOSITORY}"
    releases = _github_json(api + "/releases?per_page=100")
    return recommend_releases(releases)


def fetch_launchpad_update():
    """Return the newest verified Launchpad RPM, including beta releases."""
    api = f"https://api.github.com/repos/{GITHUB_REPOSITORY}"
    releases = _github_json(api + "/releases?per_page=100")
    return latest_launchpad_update(releases, INSTALLER_VERSION)


def installed_aurora_version(root: Path) -> str:
    """Read the managed build version without importing the installed app."""
    version_file = Path(root) / "aurora_core" / "version.py"
    try:
        text = version_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "0.0.0"
    match = re.search(
        r'^__version__\s*=\s*["\'](\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?(?:\+[A-Za-z0-9.-]+)?)',
        text, re.MULTILINE,
    )
    return match.group(1) if match else "0.0.0"


def download_launchpad_update(workspace: Path, update: dict) -> Path:
    asset = update.get("asset") if isinstance(update, dict) else None
    if not isinstance(asset, dict):
        raise RuntimeError("O GitHub não retornou um pacote válido do Launchpad.")
    name = asset.get("name")
    url = asset.get("browser_download_url")
    digest = asset.get("digest")
    size = asset.get("size")
    if (not isinstance(name, str) or not re.fullmatch(r"aurora-launchpad-\d+\.\d+\.\d+-[^/]+\.noarch\.rpm", name)
            or not isinstance(url, str) or not isinstance(digest, str) or not isinstance(size, int)
            or size <= 0 or size > MAX_LAUNCHPAD_RPM_BYTES):
        raise RuntimeError("Os metadados do pacote do Launchpad são inválidos.")
    target = Path(workspace) / name
    request = urllib.request.Request(url, headers={
        "Accept": "application/octet-stream",
        "User-Agent": f"Aurora-Launchpad/{INSTALLER_VERSION}",
    })
    with urllib.request.urlopen(request, timeout=30) as response:
        if response.status != 200 or not is_official_github_download_url(response.geturl()):
            raise RuntimeError("O pacote não veio de um host oficial do GitHub.")
        received = 0
        checksum = hashlib.sha256()
        with target.open("xb") as output:
            while True:
                block = response.read(1024 * 1024)
                if not block:
                    break
                received += len(block)
                if received > MAX_LAUNCHPAD_RPM_BYTES:
                    raise RuntimeError("O pacote do Launchpad excede o limite permitido.")
                checksum.update(block)
                output.write(block)
    expected = digest.partition(":")[2].lower()
    if received != size or not hmac.compare_digest(checksum.hexdigest(), expected):
        target.unlink(missing_ok=True)
        raise RuntimeError("A assinatura SHA-256 do pacote não confere com o GitHub.")
    return target


def download_release_payload(workspace: Path, release: dict, on_status=None) -> tuple[Path, dict]:
    """Fetch the user-selected release through its immutable commit archive."""
    if not isinstance(release, dict) or release.get("draft"):
        raise RuntimeError("A release escolhida não é válida ou ainda não foi publicada.")
    tag = release.get("tag_name")
    if not isinstance(tag, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,99}", tag):
        raise RuntimeError("A tag da release escolhida não é válida.")
    if not isinstance(release.get("prerelease"), bool):
        raise RuntimeError("O canal da release escolhida não é válido.")
    api = f"https://api.github.com/repos/{GITHUB_REPOSITORY}"
    if on_status:
        channel = "pré-release" if release.get("prerelease") else "release"
        on_status(f"Versão escolhida: {tag} ({channel}). Resolvendo commit…")
    commit = _github_json(api + "/commits/" + quote(tag, safe=""))
    sha = commit.get("sha") if isinstance(commit, dict) else None
    if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-fA-F]{40}", sha):
        raise RuntimeError("O GitHub não confirmou o commit da release escolhida.")

    archive_path = Path(workspace) / "aurora-source.tar.gz"
    url = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/tarball/{sha}"
    request = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": f"Aurora-Launchpad/{INSTALLER_VERSION}",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    with urllib.request.urlopen(request, timeout=30) as response:
        final = urlsplit(response.geturl())
        if response.status != 200 or final.scheme != "https" or final.hostname != "codeload.github.com":
            raise RuntimeError("O download da release não veio do host oficial do GitHub.")
        length = response.headers.get("Content-Length")
        if length and int(length) > MAX_RELEASE_ARCHIVE_BYTES:
            raise RuntimeError("O arquivo da release excede o limite permitido.")
        received = 0
        with archive_path.open("xb") as output:
            while True:
                block = response.read(1024 * 1024)
                if not block:
                    break
                received += len(block)
                if received > MAX_RELEASE_ARCHIVE_BYTES:
                    raise RuntimeError("O arquivo da release excede o limite permitido.")
                output.write(block)
    extracted = extract_release_tarball(archive_path, Path(workspace) / "source")
    if not (extracted / "aurora.py").is_file() or not (extracted / "aurora_core").is_dir():
        raise RuntimeError("A release do GitHub não contém o payload de desktop esperado.")
    return extracted, release


def is_rpm_install() -> bool:
    launcher = shutil.which("aurora-launchpad", path=SYSTEM_PATH)
    if not launcher:
        return False
    return subprocess.run(["/usr/bin/rpm", "-qf", launcher], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0


def run_process(command: list[str], on_line=None, cwd: Path | None = None, timeout: int | None = None) -> str:
    proc = subprocess.Popen(
        command,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        env={
            **{key: value for key, value in os.environ.items()
               if key not in {"PYTHONPATH", "PYTHONHOME", "LD_PRELOAD", "LD_LIBRARY_PATH"}
               and not key.startswith("PIP_")},
            "PATH": SYSTEM_PATH,
            "PIP_CONFIG_FILE": os.devnull,
            "PIP_NO_INPUT": "1",
            "PIP_DISABLE_PIP_VERSION_CHECK": "1",
            "OLLAMA_HOST": "127.0.0.1:11434",
            "OLLAMA_NO_CLOUD": "1",
        },
    )
    lines: list[str] = []
    output_queue: queue.Queue[str | None] = queue.Queue(maxsize=512)
    started = time.monotonic()
    assert proc.stdout is not None
    def read_output():
        assert proc.stdout is not None
        for output_line in proc.stdout:
            output_queue.put(output_line)
        output_queue.put(None)

    threading.Thread(target=read_output, daemon=True).start()
    stream_done = False
    while not stream_done:
        if timeout is not None and time.monotonic() - started > timeout:
            proc.kill()
            proc.wait()
            raise RuntimeError(f"Tempo esgotado executando {Path(command[0]).name}.")
        try:
            line = output_queue.get(timeout=0.2)
        except queue.Empty:
            continue
        if line is None:
            stream_done = True
            continue
        text = line.rstrip("\r\n")
        lines.append(text)
        if len(lines) > 2000:
            del lines[:500]
        if on_line:
            on_line(text)
    try:
        code = proc.wait(timeout=max(1, timeout - (time.monotonic() - started)) if timeout is not None else None)
    except subprocess.TimeoutExpired:
        proc.kill(); proc.wait()
        raise RuntimeError(f"Tempo esgotado executando {Path(command[0]).name}.")
    output = "\n".join(lines)
    if code:
        tail = "\n".join(lines[-8:]) or f"código {code}"
        raise RuntimeError(f"{Path(command[0]).name} terminou com erro:\n{tail}")
    return output


class Launchpad(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self.connect("activate", self.on_activate)
        self.window = None
        self.stack = None
        self.log_label = None
        self.progress_bar = None
        self.progress_title = None
        self.progress_subtitle = None
        self.report = None
        self.releases_box = None
        self.release_status = None
        self.release_options = ()
        self.release_cards = []
        self.selected_release = None
        self.install_acknowledged = False
        self.loading_releases = False
        self.aurora_update_in_progress = False
        self.aurora_update_mode = False
        self.ollama = shutil.which("ollama", path=SYSTEM_PATH)
        self.existing_install = (MANAGED_APP / "aurora.py").is_file()
        self.onboarding_scheduled = not self.existing_install
        self.failed = False
        self.failed_operation = "install"
        self.last_uninstall_options = (False, False, False)
        self.lines: list[str] = []
        self.install_health = None
        self.install_health_error = None
        self.health_label = None
        self.repair_button = None
        self.update_panel = None
        self.update_button = None
        self.launchpad_update = None
        self.update_in_progress = False
        self.installed_aurora_version = installed_aurora_version(MANAGED_APP)
        self.new_aurora_releases = ()
        self.aurora_update_status = None
        self.aurora_update_button = None
        self.refresh_releases_button = None
        self.done_detail = None
        self._deployment_backup = None
        self._deployment_workspace = None
        self._update_runtime_state = None

    def _installation_health(self):
        unit = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home()/".config"))) / "systemd/user/aurora.service"
        try:
            active = subprocess.run(
                [SYSTEMCTL, "--user", "is-active", "--quiet", "aurora.service"],
                timeout=5,
            ).returncode == 0
        except subprocess.TimeoutExpired:
            self.install_health_error = "O serviço não respondeu dentro do tempo limite."
            return InstallationHealth("unknown", (self.install_health_error,), False)
        self.install_health_error = None
        data_root = Path(os.environ.get("XDG_DATA_HOME", str(Path.home()/".local/share"))) / "aurora"
        return inspect_installation(
            MANAGED_APP,
            unit,
            service_active=active,
            whisper_model=data_root / "models/ggml-base-q5_1.bin",
        )

    def on_activate(self, _app):
        if self.window:
            self.window.present()
            return
        Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.FORCE_DARK)
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS.encode())
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.report = assess_environment(read_os_release(), dict(os.environ), memory_total_bytes(), disk_free_bytes(Path.home()))
        self.install_health = self._installation_health()
        self.window = Adw.ApplicationWindow(application=self, title="Aurora Studio", default_width=820, default_height=660)
        self.window.add_css_class("launchpad")
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        header = Adw.HeaderBar()
        brand = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=9)
        mark = Gtk.Label(label="✦")
        mark.add_css_class("brand-mark")
        brand.append(mark)
        brand_text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        brand_title = Gtk.Label(label="Aurora", xalign=0)
        brand_title.add_css_class("brand-title")
        brand_subtitle = Gtk.Label(label="STUDIO", xalign=0)
        brand_subtitle.add_css_class("brand-subtitle")
        brand_text.append(brand_title)
        brand_text.append(brand_subtitle)
        brand.append(brand_text)
        header.set_title_widget(brand)
        header.add_css_class("flat")
        outer.append(header)
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, transition_duration=240)
        self.stack.add_named(self._maintenance_page() if self.existing_install else self._welcome_page(), "welcome")
        self.stack.add_named(self._progress_page(), "progress")
        self.stack.add_named(self._done_page(), "done")
        outer.append(self.stack)
        self.window.set_content(outer)
        self.window.present()
        if self.existing_install:
            threading.Thread(target=self._maintenance_probe_worker, daemon=True).start()
        self._load_releases()

    def _maintenance_probe_worker(self):
        if not self.ollama:
            GLib.idle_add(self.model_status.set_text, "Modelos presentes: comando ollama não encontrado.")
            return
        try:
            result = subprocess.run([self.ollama, "list"], capture_output=True, text=True, timeout=20)
            if result.returncode:
                raise RuntimeError(result.stderr.strip() or "ollama list falhou")
            present = parse_ollama_models(result.stdout)
            missing = [model for model in MODEL_NAMES if model not in present]
            text = "Modelos presentes: todos os modelos esperados." if not missing else "Modelos ausentes: " + ", ".join(missing)
        except Exception as exc:
            text = f"Modelos presentes: não foi possível consultar ({type(exc).__name__})."
        GLib.idle_add(self.model_status.set_text, text)

    def _maintenance_page(self) -> Gtk.Widget:
        col = self._column()
        hero = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        hero.add_css_class("hero")
        hero.append(self._label("AURORA STUDIO · PAINEL LOCAL", "caption"))
        hero.append(self._label("Sua assistente, do seu jeito", "title-1"))
        hero.append(self._label("Acompanhe a instalação, personalize como a Aurora fala e se comporta, e mantenha tudo atualizado.", "subtle", True))
        col.append(hero)

        status = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        status.add_css_class("panel")
        status.append(self._label("ESTADO BÁSICO", "caption"))
        self.maintenance_status = self._label("Consultando o serviço…", "subtle", True)
        status.append(self.maintenance_status)
        status.append(self._label(f"Build instalada: {self.installed_aurora_version}", "subtle", True))
        status.append(self._label(f"Modelos esperados: {', '.join(MODEL_NAMES)}", "subtle", True))
        self.model_status = self._label("Modelos presentes: consultando…", "subtle", True)
        status.append(self.model_status)
        status.append(self._label(f"Pasta gerenciada: {MANAGED_APP}", "subtle", True))

        health = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        health.add_css_class("panel")
        health.append(self._label("INTEGRIDADE", "caption"))
        health_title = {"healthy": "Instalação íntegra", "repairable": "Instalação precisa de reparo", "broken": "Instalação incompleta", "missing": "Aurora não encontrada"}.get(self.install_health.state, "Estado desconhecido")
        health.append(self._label(health_title, "status-good" if self.install_health.state == "healthy" else "status-warn", True))
        for detail in self.install_health.details:
            health.append(self._label(detail, "subtle", True))
        if self.install_health.repairable and self.install_health.state != "healthy":
            health.append(self._button("Parar e reparar", self._repair_install, suggested=True))

        overview = Gtk.Grid(column_spacing=12, row_spacing=12)
        overview.set_column_homogeneous(True)
        overview.attach(status, 0, 0, 1, 1)
        overview.attach(health, 1, 0, 1, 1)
        col.append(overview)

        personalization = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        personalization.add_css_class("panel")
        personalization.append(self._label("PERSONALIZAÇÃO", "caption"))
        personalization.append(self._label("Ajuste identidade, personalidade, tom, nível de detalhe, voz, aparência e sons sem reinstalar.", "subtle", True))
        self.personalization_status = self._label("Seu perfil só muda depois que você concluir e salvar a personalização.", "subtle", True)
        personalization.append(self.personalization_status)
        personalization.append(self._button("Abrir personalização", self._open_personalization, suggested=True))

        self.update_panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.update_panel.add_css_class("panel")
        self.update_panel.append(self._label("ATUALIZAÇÃO DO LAUNCHPAD", "caption"))
        self.update_status = self._label("Verificando se há uma versão nova…", "subtle", True)
        self.update_panel.append(self.update_status)
        self.update_button = self._button("Atualizar Aurora Studio", self._start_launchpad_update, suggested=True)
        self.update_button.set_visible(False)
        self.update_panel.append(self.update_button)
        self.refresh_releases_button = self._button("Tentar novamente", self._load_releases)
        self.refresh_releases_button.set_visible(False)
        self.update_panel.append(self.refresh_releases_button)

        actions_grid = Gtk.Grid(column_spacing=12, row_spacing=12)
        actions_grid.set_column_homogeneous(True)
        actions_grid.attach(personalization, 0, 0, 1, 1)
        actions_grid.attach(self.update_panel, 1, 0, 1, 1)
        col.append(actions_grid)

        aurora_update = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        aurora_update.add_css_class("panel")
        aurora_update.append(self._label("ATUALIZAÇÃO DA AURORA", "caption"))
        self.aurora_update_status = self._label(
            f"Versão instalada: {self.installed_aurora_version}. O perfil, nome, voz, aparência e dados locais serão preservados.",
            "subtle", True,
        )
        aurora_update.append(self.aurora_update_status)
        self.aurora_update_button = self._button("Atualizar Aurora", self._start_aurora_update, suggested=True)
        self.aurora_update_button.set_sensitive(False)
        aurora_update.append(self.aurora_update_button)
        col.append(aurora_update)

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12, halign=Gtk.Align.END)
        actions.append(self._button("Remover Aurora…", self._confirm_uninstall))
        col.append(actions)
        return self._page(col)

    def _page(self, child: Gtk.Widget) -> Gtk.Widget:
        scroll = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_child(child)
        return scroll

    def _column(self, spacing=15) -> Gtk.Box:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=spacing)
        box.set_margin_top(22); box.set_margin_bottom(22); box.set_margin_start(24); box.set_margin_end(24)
        return box

    def _label(self, text: str, css: str | None = None, wrap=False) -> Gtk.Label:
        label = Gtk.Label(label=text, xalign=0, wrap=wrap)
        if css: label.add_css_class(css)
        return label

    def _button(self, label, callback, suggested=False) -> Gtk.Button:
        button = Gtk.Button(label=label)
        button.add_css_class("pill")
        if suggested: button.add_css_class("suggested-action")
        button.connect("clicked", callback)
        return button

    def _welcome_page(self) -> Gtk.Widget:
        col = self._column()
        hero = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        hero.add_css_class("hero")
        hero.append(self._label("AURORA STUDIO · FEDORA WORKSTATION", "caption"))
        hero.append(self._label("Escolha sua versão da Aurora", "title-1"))
        hero.append(self._label("Compare as versões recomendadas. A instalação só começa depois que você escolher e confirmar.", "subtle", True))
        col.append(hero)

        status = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        status.add_css_class("panel")
        status.append(self._label("COMPATIBILIDADE DO COMPUTADOR", "caption"))
        facts = [
            ("Sistema", self.report.distro, self.report.supported),
            ("Sessão", f"{self.report.desktop} · {self.report.session}", self.report.supported),
            ("Memória", f"{self.report.memory_gib:.1f} GiB" if self.report.memory_gib else "não detectada", self.report.memory_gib >= 8),
            ("Espaço livre", f"{self.report.free_gib:.1f} GiB · mínimo sugerido 10 GiB", self.report.free_gib >= 10),
            ("Ollama", "instalado" if self.ollama else "será instalado pelo assistente", bool(self.ollama or Path(PKEXEC).is_file())),
        ]
        for name, value, good in facts:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            row.set_margin_top(9); row.set_margin_bottom(7)
            row.append(self._label(name, "subtle"))
            value_label = Gtk.Label(label=value, xalign=1, hexpand=True)
            value_label.add_css_class("status-good" if good else "status-warn")
            row.append(value_label); status.append(row)
        for warning in self.report.warnings:
            status.append(self._label("⚠  " + warning, "status-warn", True))
        if not self.report.supported:
            status.append(self._label("Disponível somente no Fedora Workstation com GNOME em Wayland.", "status-bad", True))
        if not self.ollama and not Path(PKEXEC).is_file():
            status.append(self._label("Ollama não está instalado e pkexec não está disponível para instalá-lo.", "status-bad", True))

        health = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        health.add_css_class("panel")
        health.append(self._label("ESTADO DA INSTALAÇÃO", "caption"))
        health_title = {
            "healthy": "Instalação íntegra",
            "repairable": "Instalação precisa de reparo",
            "broken": "Instalação incompleta",
            "missing": "Aurora ainda não instalada",
        }.get(self.install_health.state, "Estado desconhecido")
        self.health_label = self._label(health_title, "status-good" if self.install_health.state == "healthy" else "status-warn", True)
        health.append(self.health_label)
        for detail in self.install_health.details:
            health.append(self._label(detail, "subtle", True))
        if self.install_health.repairable and self.install_health.state != "healthy":
            self.repair_button = self._button("Parar e reparar", self._repair_install, suggested=True)
            health.append(self.repair_button)
        elif self.install_health.state == "healthy":
            health.append(self._label("Nenhuma correção é necessária agora.", "subtle", True))

        self.update_panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.update_panel.add_css_class("panel")
        self.update_panel.append(self._label("ATUALIZAÇÃO DO LAUNCHPAD", "caption"))
        self.update_status = self._label("Verificando se há uma versão nova…", "subtle", True)
        self.update_panel.append(self.update_status)
        self.update_button = self._button("Atualizar Aurora Studio", self._start_launchpad_update, suggested=True)
        self.update_button.set_visible(False)
        self.update_panel.append(self.update_button)
        self.refresh_releases_button = self._button("Tentar novamente", self._load_releases)
        self.refresh_releases_button.set_visible(False)
        self.update_panel.append(self.refresh_releases_button)

        overview = Gtk.Grid(column_spacing=12, row_spacing=12)
        overview.set_column_homogeneous(True)
        overview.attach(status, 0, 0, 1, 1)
        overview.attach(health, 1, 0, 1, 1)
        overview.attach(self.update_panel, 0, 1, 2, 1)
        col.append(overview)

        section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        section.append(self._label("Versões recomendadas", "title-2"))
        self.release_status = self._label("Buscando versões no GitHub…", "subtle", True)
        section.append(self.release_status)
        self.releases_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        section.append(self.releases_box)
        col.append(section)

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12, halign=Gtk.Align.END)
        if self.existing_install:
            actions.append(self._button("Remover Aurora…", self._confirm_uninstall))
        col.append(actions)
        col.append(self._label("Clique em uma versão para revisar e confirmar a instalação. Pré-releases são experimentais e podem conter falhas.", "subtle", True))
        return self._page(col)

    def _load_releases(self, *_):
        if self.loading_releases:
            return
        self.loading_releases = True
        self.launchpad_update = None
        self.new_aurora_releases = ()
        if self.aurora_update_button:
            self.aurora_update_button.set_sensitive(False)
        if self.update_button:
            self.update_button.set_visible(False)
        if self.refresh_releases_button:
            self.refresh_releases_button.set_sensitive(False)
            self.refresh_releases_button.set_visible(True)
        if self.release_status:
            self.release_status.set_text("Buscando versões no GitHub…")
        threading.Thread(target=self._load_releases_worker, daemon=True).start()

    def _load_releases_worker(self):
        try:
            api = f"https://api.github.com/repos/{GITHUB_REPOSITORY}"
            releases = _github_json(api + "/releases?per_page=100")
            options = recommend_releases(releases)
            update = latest_launchpad_update(releases, INSTALLER_VERSION)
            newer = newer_aurora_releases(
                releases, self.installed_aurora_version, 100
            ) if self.existing_install else ()
            GLib.idle_add(self._show_release_options, options, None, update, newer)
        except Exception as exc:
            GLib.idle_add(self._show_release_options, (), str(exc), None, ())

    def _show_release_options(self, options, error, update=None, newer=()):
        self.loading_releases = False
        if self.refresh_releases_button:
            self.refresh_releases_button.set_sensitive(True)
        self.release_options = options
        self.launchpad_update = update
        self.new_aurora_releases = tuple(newer or ())
        # An installed Aurora opens the maintenance dashboard, which does not
        # create the fresh-install release widgets. Keep that path isolated so
        # an older Launchpad can still present its self-update action instead
        # of crashing while dereferencing ``releases_box``.
        if self.existing_install:
            if error:
                self.update_status.set_text("Não consegui consultar as atualizações agora. Tente novamente.")
                self.aurora_update_status.set_text(f"Falha ao consultar as versões: {str(error)[:180]}")
                self.aurora_update_button.set_sensitive(False)
                self.refresh_releases_button.set_label("Tentar novamente")
                self.refresh_releases_button.set_visible(True)
                return False
            self.refresh_releases_button.set_visible(False)
            if update:
                version = update["asset"]["name"].split("aurora-launchpad-", 1)[1].split("-", 1)[0]
                self.update_status.set_text(
                    f"Esta cópia é {INSTALLER_VERSION}; a versão {version} está disponível. Atualize antes de continuar."
                )
                self.update_button.set_visible(True)
                self.aurora_update_status.set_text("Atualize o Aurora Studio antes de atualizar a Aurora.")
                self.aurora_update_button.set_sensitive(False)
                return False
            self.aurora_update_button.set_sensitive(bool(self.new_aurora_releases))
            self.update_status.set_text(f"Aurora Studio {INSTALLER_VERSION} está atualizado.")
            if self.new_aurora_releases:
                release = self.new_aurora_releases[0]
                self.aurora_update_status.set_text(
                    f"Versão {release['tag_name']} disponível. Nome, voz, aparência, modelos e dados locais serão preservados."
                )
            else:
                self.aurora_update_status.set_text(
                    f"Aurora {self.installed_aurora_version} já está na versão publicada mais recente."
                )
            self._refresh_maintenance_status()
            return False
        self.release_cards.clear()
        while self.releases_box.get_first_child():
            self.releases_box.remove(self.releases_box.get_first_child())
        if error:
            self.release_status.set_text("Não consegui consultar as versões agora. Confira a conexão e tente novamente.")
            self.refresh_releases_button.set_label("Tentar novamente")
            self.refresh_releases_button.set_visible(True)
            return False
        self.refresh_releases_button.set_visible(False)
        if update:
            version = update["asset"]["name"].split("aurora-launchpad-", 1)[1].split("-", 1)[0]
            self.update_status.set_text(
                f"Esta cópia é {INSTALLER_VERSION}; a versão {version} está disponível. Atualize antes de instalar uma Aurora."
            )
            self.update_button.set_visible(True)
            self.releases_box.set_sensitive(False)
            self.release_status.set_text("Atualização obrigatória do Aurora Studio disponível.")
            return False
        self.update_status.set_text(f"Aurora Studio {INSTALLER_VERSION} está atualizado.")
        if not options:
            self.release_status.set_text("O GitHub não retornou releases publicadas válidas.")
            return False

        self.release_status.set_text("Escolha uma versão. Datas e canais vêm das releases publicadas no GitHub.")
        grid = Gtk.Grid(column_spacing=12, row_spacing=12)
        grid.set_column_homogeneous(True)
        self.releases_box.append(grid)
        for index, option in enumerate(options):
            button = Gtk.Button()
            button.add_css_class("release-card")
            button.set_valign(Gtk.Align.FILL)
            button.set_hexpand(True)
            button.set_sensitive(
                self.report.supported
                and self.report.free_gib >= 10
                and bool(self.ollama or Path(PKEXEC).is_file())
            )
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, halign=Gtk.Align.FILL)
            channel_title, description = self._channel_copy(option.channel)
            card.append(self._label(channel_title, "caption", True))
            release = option.release
            title = release.get("name")
            if not isinstance(title, str) or not title.strip():
                title = release["tag_name"]
            name_label = self._label(title.strip(), "title-2", True)
            name_label.set_valign(Gtk.Align.START)
            card.append(name_label)
            card.append(self._label(release["tag_name"], "subtle", True))
            card.append(self._label(self._format_release_date(release.get("published_at")), "subtle", True))
            card.append(self._label(description, "subtle", True))
            button.set_child(card)
            button.connect("clicked", self._choose_release, option)
            grid.attach(button, index, 0, 1, 1)
            self.release_cards.append((button, option))

        return False

    def _start_aurora_update(self, *_):
        if self.aurora_update_in_progress:
            return
        if self.launchpad_update:
            self.aurora_update_status.set_text("Atualize o Aurora Studio antes de atualizar a Aurora.")
            return
        self.aurora_update_in_progress = True
        self.aurora_update_button.set_sensitive(False)
        self.aurora_update_status.set_text("Buscando a versão publicada mais recente no GitHub, incluindo pré-releases…")
        threading.Thread(target=self._aurora_update_worker, daemon=True).start()

    def _aurora_update_worker(self):
        try:
            api = f"https://api.github.com/repos/{GITHUB_REPOSITORY}"
            releases = _github_json(api + "/releases?per_page=100")
            candidates = newer_aurora_releases(
                releases, self.installed_aurora_version, 100
            )
            if not candidates:
                GLib.idle_add(self._aurora_already_current)
                return
            GLib.idle_add(self._begin_aurora_update, candidates[0])
        except Exception as exc:
            GLib.idle_add(self._aurora_update_failed, str(exc))

    def _aurora_already_current(self):
        self.aurora_update_in_progress = False
        self.aurora_update_button.set_sensitive(True)
        self.aurora_update_status.set_text(
            f"Aurora {self.installed_aurora_version} já está na versão publicada mais recente."
        )
        return False

    def _begin_aurora_update(self, release):
        self.selected_release = release
        self.install_acknowledged = True
        self.aurora_update_mode = True
        self.failed_operation = "update"
        self.progress_title.set_text("Atualizando Aurora")
        channel = "pré-release experimental" if release.get("prerelease") else "versão estável"
        self.progress_subtitle.set_text(f"Preparando {channel} {release['tag_name']}.")
        self.stack.set_visible_child_name("progress")
        self.lines.clear()
        self._append(f"Atualizando Aurora para {release['tag_name']}…")
        self.cancel_button.set_sensitive(False)
        threading.Thread(target=self._install_worker, args=(release,), daemon=True).start()
        return False

    def _aurora_update_failed(self, message):
        self.aurora_update_in_progress = False
        self.aurora_update_button.set_sensitive(True)
        self.aurora_update_status.set_text(f"Não foi possível atualizar a Aurora: {message[:180]}")
        return False

    def _refresh_maintenance_status(self):
        if not hasattr(self, "maintenance_status"):
            return
        health = self._installation_health()
        if health.state == "unknown":
            self.maintenance_status.set_text(
                "Não consegui consultar o serviço. Tente atualizar o status novamente."
            )
            return
        active = health.state == "healthy"
        self.maintenance_status.set_text(
            "Serviço ativo e instalação íntegra." if active else "Serviço ou instalação precisam de atenção."
        )

    def _open_personalization(self, *_):
        try:
            config_root = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home()/".config")))
            config_path = config_root / "aurora" / "aurora-settings.json"
            schedule_personalization(config_path, os.environ.get("XDG_SESSION_ID", ""))
            self.personalization_status.set_text("Personalização agendada. Reiniciando a Aurora…")
            subprocess.Popen([SYSTEMCTL, "--user", "restart", "aurora.service"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as exc:
            self.personalization_status.set_text(f"Não consegui abrir a personalização: {type(exc).__name__}.")
        return False

    def _start_launchpad_update(self, *_):
        if self.update_in_progress or not self.launchpad_update:
            return
        self.update_in_progress = True
        self.update_button.set_sensitive(False)
        self.update_status.set_text("Baixando e verificando a atualização…")
        threading.Thread(target=self._launchpad_update_worker, daemon=True).start()

    def _launchpad_update_worker(self):
        try:
            with tempfile.TemporaryDirectory(prefix="aurora-launchpad-update-") as workspace:
                rpm = download_launchpad_update(Path(workspace), self.launchpad_update)
                run_process([PKEXEC, DNF, "install", "-y", str(rpm)], timeout=600)
            GLib.idle_add(self._finish_launchpad_update)
        except Exception as exc:
            GLib.idle_add(self._launchpad_update_failed, str(exc))

    def _finish_launchpad_update(self):
        self.update_status.set_text("Aurora Studio atualizado. Reabrindo a versão nova…")
        GLib.timeout_add(700, self._restart_launchpad)
        return False

    def _launchpad_update_failed(self, message):
        self.update_in_progress = False
        self.update_button.set_sensitive(True)
        self.update_status.set_text(f"Não foi possível atualizar: {message}")
        return False

    @staticmethod
    def _restart_launchpad():
        executable = shutil.which("aurora-launchpad", path=SYSTEM_PATH) or "/usr/bin/aurora-launchpad"
        os.execv(executable, [executable])
        return False

    @staticmethod
    def _channel_copy(channel: str) -> tuple[str, str]:
        if channel == "latest_prerelease":
            return "PRÉ-RELEASE · MAIS RECENTE", "A versão de testes mais nova. Pode mudar e conter falhas."
        if channel == "previous_prerelease":
            return "PRÉ-RELEASE · ANTERIOR", "Publicação anterior à mais recente. Isso não garante mais estabilidade; confira o nome e as notas."
        return "RELEASE · ESTÁVEL MAIS RECENTE", "A versão estável publicada mais recentemente."

    @staticmethod
    def _format_release_date(value) -> str:
        if not isinstance(value, str):
            return "Data de publicação indisponível"
        try:
            published = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return "Publicada em " + published.astimezone().strftime("%d/%m/%Y")
        except ValueError:
            return "Data de publicação indisponível"

    def _choose_release(self, button, option):
        self.selected_release = option.release
        for card_button, _ in self.release_cards:
            card_button.remove_css_class("selected")
        button.add_css_class("selected")
        self._confirm_install()

    def _confirm_install(self, *_):
        if not self.selected_release:
            return
        if not self.report.supported or self.report.free_gib < 10 or not (self.ollama or Path(PKEXEC).is_file()):
            return
        release = self.selected_release
        channel, channel_detail = self._channel_copy(
            next((item.channel for item in self.release_options if item.release is release), "latest_stable")
        )
        dialog = Gtk.Dialog(title="Confirmar instalação", transient_for=self.window, modal=True)
        dialog.add_button("Voltar", Gtk.ResponseType.CANCEL)
        confirm = dialog.add_button("Confirmar e instalar", Gtk.ResponseType.ACCEPT)
        confirm.set_sensitive(False)
        content = dialog.get_content_area()
        content.set_spacing(12)
        content.set_margin_top(20); content.set_margin_bottom(20)
        content.set_margin_start(22); content.set_margin_end(22)
        content.append(self._label("A versão escolhida", "title-2"))
        content.append(self._label(f"{release.get('name') or release['tag_name']} · {release['tag_name']}", wrap=True))
        content.append(self._label(f"{channel}\n{channel_detail}", "subtle", True))
        content.append(self._label(
            "O Aurora Studio baixará essa versão do GitHub, instalará dependências Python e o modelo de voz, baixará os modelos Gemma que faltarem e configurará o serviço da Aurora. Se o Ollama estiver ausente, a instalação poderá solicitar autenticação e alterar componentes do sistema, incluindo serviços e drivers.",
            "subtle", True,
        ))
        acknowledgement = Gtk.CheckButton(label="Entendi os downloads e as possíveis alterações do Ollama no sistema.")
        acknowledgement.connect("toggled", lambda check: confirm.set_sensitive(check.get_active()))
        content.append(acknowledgement)
        dialog.connect("response", self._install_confirmation_response, acknowledgement)
        dialog.present()

    def _install_confirmation_response(self, dialog, response, acknowledgement):
        accepted = response == Gtk.ResponseType.ACCEPT and acknowledgement.get_active()
        dialog.close()
        if accepted:
            self.install_acknowledged = True
            self._start_install()

    def _progress_page(self) -> Gtk.Widget:
        col = self._column()
        col.append(self._label("Preparando a Aurora", "title-1"))
        self.progress_title = self._label("Aguardando início…", "title-2")
        col.append(self.progress_title)
        self.progress_bar = Gtk.ProgressBar(show_text=True, fraction=0)
        self.progress_bar.set_text("0%")
        col.append(self.progress_bar)
        self.progress_subtitle = self._label("Nenhuma alteração começou.", "subtle", True)
        col.append(self.progress_subtitle)
        log_panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        log_panel.add_css_class("panel")
        log_panel.append(self._label("ETAPAS", "caption"))
        self.log_label = Gtk.Label(label="", xalign=0, yalign=0, wrap=True, selectable=True)
        self.log_label.add_css_class("log")
        log_panel.append(self.log_label); col.append(log_panel)
        self.cancel_button = self._button("Fechar janela", self._progress_action)
        self.cancel_button.set_sensitive(False)
        col.append(self.cancel_button)
        return self._page(col)

    def _done_page(self) -> Gtk.Widget:
        col = self._column()
        col.append(self._label("Aurora pronta para despertar.", "title-1"))
        detail = ("A instalação terminou. Reinicie o computador ou encerre a sessão e entre novamente. No próximo login, a Aurora abrirá o assistente de personalização."
                  if self.onboarding_scheduled else
                  "A instalação terminou. Reinicie o computador para carregar todos os componentes e testar a Aurora.")
        self.done_detail = self._label(detail, "subtle", True)
        col.append(self.done_detail)
        self.reboot_status = self._label("Você também pode reiniciar ou sair da sessão mais tarde.", "subtle", True)
        col.append(self.reboot_status)
        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12, halign=Gtk.Align.END)
        buttons.append(self._button("Abrir status do serviço", self._show_service_status))
        self.done_action_buttons = []
        for label, callback, suggested in (
            ("Sair da sessão", self._request_logout, False),
            ("Reiniciar depois", lambda *_: self.window.close(), False),
            ("Reiniciar agora", self._request_reboot, True),
        ):
            button = self._button(label, callback, suggested=suggested)
            self.done_action_buttons.append(button)
            buttons.append(button)
        col.append(buttons)
        return self._page(col)

    def _append(self, message: str):
        if not message:
            return
        self.lines.append(message.strip())
        self.lines = self.lines[-8:]
        if self.log_label:
            self.log_label.set_text("\n".join(self.lines))

    def _status(self, title=None, detail=None, fraction=None, log=None):
        if title is not None and self.progress_title:
            self.progress_title.set_text(title)
        if detail is not None and self.progress_subtitle:
            self.progress_subtitle.set_text(detail)
        if fraction is not None and self.progress_bar:
            self.progress_bar.set_fraction(max(0, min(1, fraction)))
            self.progress_bar.set_text(f"{round(fraction*100)}%")
        if log:
            self._append(log)
        return False

    def _start_install(self, *_):
        if not self.install_acknowledged or not self.selected_release:
            return
        if not self.report.supported or (not self.aurora_update_mode and self.report.free_gib < 10):
            return
        self.failed_operation = "update" if self.aurora_update_mode else "install"
        self.stack.set_visible_child_name("progress")
        self.lines.clear(); self._append("Preparando o ambiente…")
        self.cancel_button.set_sensitive(False)
        threading.Thread(target=self._install_worker, args=(self.selected_release,), daemon=True).start()

    def _set_stage(self, title: str, detail: str, fraction: float):
        GLib.idle_add(self._status, title, detail, fraction, title)

    def _stream_line(self, line: str):
        if line.strip():
            GLib.idle_add(self._status, None, None, None, line)

    def _install_worker(self, selected_release: dict):
        try:
            action = "Atualizando a Aurora" if self.aurora_update_mode else "Baixando a Aurora"
            self._set_stage("1/7 · " + action, f"Preparando {selected_release['tag_name']}.", .03)
            with tempfile.TemporaryDirectory(prefix="aurora-release-") as workspace:
                source, release = download_release_payload(
                    Path(workspace),
                    selected_release,
                    on_status=lambda message: self._stream_line(message),
                )
                self._set_stage(
                    "1/7 · Preparando os arquivos",
                    f"Instalando {release['tag_name']} ({'pré-release' if release.get('prerelease') else 'release'}).",
                    .07,
                )
                self._update_runtime_state = self._capture_update_runtime_state(source)
                self._set_stage("2/7 · Parando a Aurora", "Encerrando o serviço antes de substituir os arquivos.", .10)
                stop_old = subprocess.run([SYSTEMCTL, "--user", "stop", "aurora.service"], capture_output=True, text=True, timeout=30)
                if stop_old.returncode and subprocess.run([SYSTEMCTL, "--user", "is-active", "--quiet", "aurora.service"], timeout=15).returncode == 0:
                    raise RuntimeError("Não consegui parar a Aurora; os arquivos atuais foram preservados.")
                self._install_payload(source)
            self._migrate_existing_memory()
            state = self._update_runtime_state or {}
            # This is a fast import/dependency check; run.sh only invokes pip
            # when an import is missing. It repairs an incomplete venv without
            # re-downloading voice or Ollama models on every app update.
            setup_python = True
            setup_voice = (not self.aurora_update_mode or not state.get("venv_present")
                           or state.get("voice_requirements_changed") or not state.get("voice_assets_present"))
            if setup_python:
                self._set_stage("3/7 · Preparando dependências", "Conferindo e instalando apenas os pacotes Python necessários.", .20)
                run_process([str(MANAGED_APP / "run.sh"), "--setup-only"], self._stream_line, cwd=MANAGED_APP, timeout=1800)
            if setup_voice:
                self._set_stage("4/7 · Preparando a voz local", "Conferindo o runtime e baixando apenas modelos de voz ausentes.", .36)
                run_process([str(MANAGED_APP / "setup-voice.sh")], self._stream_line, cwd=MANAGED_APP, timeout=1800)
            if not self.aurora_update_mode:
                self.ollama = shutil.which("ollama", path=SYSTEM_PATH)
                if not self.ollama:
                    self._set_stage("5/7 · Instalando Ollama", "O instalador oficial solicitará autenticação do sistema.", .47)
                    self._install_ollama()
                    self.ollama = shutil.which("ollama", path=SYSTEM_PATH)
                if not self.ollama:
                    raise RuntimeError("O comando ollama não apareceu após a instalação.")
                self._wait_for_ollama()
                before = set(__import__("aurora_launchpad_core").parse_ollama_models(
                    run_process([self.ollama, "list"], self._stream_line, timeout=30)
                ))
                absent = [name for name in MODEL_NAMES if name not in before]
                self._set_stage("5/7 · Conferindo modelos", f"{len(absent)} modelo(s) precisam ser baixados; o progresso aparece aqui.", .50)
                for index, model in enumerate(absent):
                    fraction = .52 + (.37 * index / max(1, len(absent)))
                    self._set_stage(f"6/7 · Baixando {model}", "O tamanho e a duração dependem da rede; os dados ficam no armazenamento do Ollama.", fraction)
                    run_process([self.ollama, "pull", model], self._stream_line, timeout=7200)
                    if model not in before:
                        OWNED_MODELS.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                        OWNED_MODELS.parent.chmod(0o700)
                        if OWNED_MODELS.is_symlink():
                            raise RuntimeError("O manifesto de modelos Aurora é um link simbólico; não vou alterá-lo.")
                        with OWNED_MODELS.open("a", encoding="utf-8") as manifest:
                            manifest.write(model + "\n")
                        OWNED_MODELS.chmod(0o600)
                if not absent:
                    self._set_stage("Modelos encontrados", "Os dois modelos já estavam disponíveis; nenhum download foi repetido.", .89)
            else:
                self._set_stage("5/7 · Preservando modelos", "A atualização não baixa novamente os modelos do Ollama.", .83)
            self._set_stage("7/7 · Ativando a Aurora", "Configurando o serviço da sessão e iniciando a bolha.", .94)
            if not self.existing_install:
                config_root = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home()/".config")))
                boot_id_path = Path("/proc/sys/kernel/random/boot_id")
                try:
                    boot_id = boot_id_path.read_text(encoding="utf-8").strip()
                except OSError as exc:
                    raise RuntimeError("Não consegui identificar a sessão atual para agendar a personalização inicial.") from exc
                prepare_first_boot_onboarding(config_root/"aurora"/"aurora-settings.json", boot_id,
                                              existing_install=False)
            run_process([str(MANAGED_APP / "install-desktop.sh")], self._stream_line, cwd=MANAGED_APP, timeout=180)
            active = subprocess.run([SYSTEMCTL, "--user", "is-active", "--quiet", "aurora.service"], timeout=15).returncode == 0
            if not active:
                raise RuntimeError("O serviço foi configurado, mas não ficou ativo. Consulte journalctl --user -u aurora.service.")
            GLib.idle_add(self._finish_install)
        except Exception as exc:
            if self.aurora_update_mode:
                try:
                    self._rollback_payload()
                    subprocess.run([SYSTEMCTL, "--user", "start", "aurora.service"],
                                   capture_output=True, text=True, timeout=30)
                except Exception as rollback_error:
                    print(f"[launchpad-update] rollback failed: {rollback_error}", flush=True)
            GLib.idle_add(self._install_failed, str(exc))

    def _capture_update_runtime_state(self, source: Path) -> dict:
        """Decide which costly setup steps an update actually needs."""
        old_venv = MANAGED_APP / ".venv" / "bin" / "python"
        new_voice = source / "requirements-voice.txt"
        old_voice = MANAGED_APP / "requirements-voice.txt"
        def same_file(left, right):
            try:
                return left.read_bytes() == right.read_bytes()
            except OSError:
                return False
        data_root = Path(os.environ.get("XDG_DATA_HOME", str(Path.home()/".local/share"))) / "aurora"
        return {
            "venv_present": old_venv.is_file(),
            "voice_requirements_changed": same_file(old_voice, new_voice) is False,
            "voice_assets_present": voice_assets_ready(
                source, data_root / "models/ggml-base-q5_1.bin"
            ),
        }

    def _install_payload(self, source: Path):
        ignored = {".git", ".venv", "__pycache__", ".pytest_cache", "android-client", "tests", "reports", ".github", "packaging", "launchpad", "aurora-settings.json", "aurora-memory.json"}
        try:
            reject_symlinks_in_tree(source)
            reject_symlinks_in_tree(MANAGED_APP, ignored_directories={".venv"})
        except ValueError as exc:
            raise RuntimeError(str(exc)) from exc
        MANAGED_APP.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        workspace = Path(tempfile.mkdtemp(prefix=".aurora-deploy-", dir=MANAGED_APP.parent))
        staged = workspace / "payload"
        staged.mkdir(mode=0o700)
        backup = workspace / "previous"
        moved_runtime = []

        def restore_original_tree():
            if backup.exists():
                # Restore preserved runtime data inside the backup tree first;
                # recreating MANAGED_APP here would block the directory swap.
                for old, new in reversed(moved_runtime):
                    if new.exists():
                        target = backup / old.relative_to(MANAGED_APP)
                        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                        os.replace(new, target)
                if MANAGED_APP.exists():
                    shutil.rmtree(MANAGED_APP, ignore_errors=True)
                os.replace(backup, MANAGED_APP)
            else:
                for old, new in reversed(moved_runtime):
                    if new.exists() and not old.exists():
                        old.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                        os.replace(new, old)

        try:
            for entry in source.iterdir():
                if entry.name in ignored or entry.name.endswith("-preview.png"):
                    continue
                if entry.is_symlink():
                    raise RuntimeError(f"O pacote contém um link simbólico inesperado: {entry.name}.")
                dest = staged / entry.name
                if entry.is_dir():
                    shutil.copytree(entry, dest, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".venv", "vosk-model"))
                else:
                    shutil.copy2(entry, dest)

            # Settings and user logs have lived beside the old code in some
            # installations. Keep them out of the downloaded source and carry
            # them forward explicitly, along with costly local runtimes.
            preserve = (".venv", "reports", "aurora-settings.json", "aurora-memory.json", "assets/vosk-model")
            for relative in preserve:
                old = MANAGED_APP / relative
                if not old.exists() or old.is_symlink():
                    continue
                if relative == ".venv" and not old.is_dir():
                    continue
                new = staged / relative
                new.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                if new.exists():
                    if new.is_dir(): shutil.rmtree(new)
                    else: new.unlink()
                os.replace(old, new)
                moved_runtime.append((old, new))

            if MANAGED_APP.exists():
                os.replace(MANAGED_APP, backup)
            try:
                os.replace(staged, MANAGED_APP)
            except Exception:
                restore_original_tree()
                raise
            MANAGED_APP.chmod(0o700)
            self._deployment_backup = backup if backup.exists() else None
            self._deployment_workspace = workspace
        except Exception:
            restore_original_tree()
            shutil.rmtree(workspace, ignore_errors=True)
            raise
        for script in ("run.sh", "start-alpha.sh", "install-desktop.sh", "install-service.sh", "setup-voice.sh", "uninstall-service.sh"):
            path = MANAGED_APP / script
            if path.is_file():
                path.chmod(path.stat().st_mode | 0o111)

    def _rollback_payload(self):
        backup = self._deployment_backup
        if not backup or not backup.exists():
            return
        failed = backup.parent / "failed-payload"
        if failed.exists():
            shutil.rmtree(failed, ignore_errors=True)
        for relative in (".venv", "reports", "aurora-settings.json", "aurora-memory.json", "assets/vosk-model"):
            active = MANAGED_APP / relative
            previous = backup / relative
            if active.exists() and not previous.exists():
                previous.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                os.replace(active, previous)
        if MANAGED_APP.exists():
            os.replace(MANAGED_APP, failed)
        os.replace(backup, MANAGED_APP)
        shutil.rmtree(failed, ignore_errors=True)
        shutil.rmtree(backup.parent, ignore_errors=True)
        self._deployment_backup = None
        self._deployment_workspace = None

    def _migrate_existing_memory(self):
        copy_existing_memory(PRESERVED_MEMORY.parent, MANAGED_APP)
        unit = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home()/".config"))) / "systemd/user/aurora.service"
        if not unit.is_file():
            return
        old_root = None
        for line in unit.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("WorkingDirectory="):
                old_root = Path(line.partition("=")[2].replace("%h", str(Path.home())))
                break
        if not old_root or old_root.resolve() == MANAGED_APP.resolve():
            return
        if copy_existing_memory(old_root, MANAGED_APP):
            GLib.idle_add(self._status, None, None, None, "Memória local migrada; a cópia antiga foi preservada.")

    def _install_ollama(self):
        if not Path(PKEXEC).is_file():
            raise RuntimeError("Polkit pkexec não está disponível para autenticar o instalador do Ollama.")
        request = urllib.request.Request("https://ollama.com/install.sh", headers={"User-Agent": "Aurora-Launchpad/0.1.0"})
        with urllib.request.urlopen(request, timeout=20) as response:
            script = response.read(OLLAMA_INSTALLER_MAX_BYTES + 1)
        try:
            validate_ollama_installer(script)
        except ValueError as exc:
            raise RuntimeError(f"{exc} Atualize o Aurora Studio antes de continuar.") from exc
        with tempfile.NamedTemporaryFile(prefix="aurora-ollama-install-", suffix=".sh", delete=False) as temp:
            temp.write(script); path = Path(temp.name)
        try:
            run_process([PKEXEC, "/bin/sh", str(path)], self._stream_line, timeout=900)
        finally:
            path.unlink(missing_ok=True)

    def _wait_for_ollama(self):
        if not ollama_api_ready():
            if not Path(PKEXEC).is_file() or not Path(SYSTEMCTL).is_file():
                raise RuntimeError("O Ollama está instalado, mas sua API não está ativa e não é possível iniciar o serviço do sistema.")
            self._prepare_ollama_storage()
            self._set_stage("Iniciando Ollama", "O Fedora pode solicitar autenticação para iniciar ollama.service.", .48)
            start = subprocess.run([PKEXEC, SYSTEMCTL, "start", "ollama.service"], capture_output=True, text=True, timeout=120)
            if start.returncode:
                detail = (start.stderr or start.stdout or "systemctl start falhou").strip()
                raise RuntimeError(f"Não consegui iniciar ollama.service: {detail}")
        for _ in range(60):
            if ollama_api_ready():
                return
            time.sleep(1)
        raise RuntimeError("O serviço Ollama não respondeu em 60 segundos. Confira systemctl status ollama.")

    def _prepare_ollama_storage(self):
        try:
            service_user = pwd.getpwnam("ollama")
            service_group = grp.getgrnam("ollama")
            command = ollama_storage_creation_command(
                Path("/usr/share/ollama"),
                service_uid=service_user.pw_uid,
                service_gid=service_group.gr_gid,
            )
        except (KeyError, OSError, ValueError) as exc:
            raise RuntimeError(f"Não consegui validar a pasta de dados do Ollama: {exc}") from exc
        if command is None:
            return
        self._set_stage("Preparando o Ollama", "Criando a pasta de dados com o proprietário do serviço.", .46)
        run_process([PKEXEC, *command], self._stream_line, timeout=60)

    def _finish_install(self):
        if self.aurora_update_mode:
            self.installed_aurora_version = installed_aurora_version(MANAGED_APP)
            self.aurora_update_in_progress = False
            if self.done_detail:
                self.done_detail.set_text(
                    f"Aurora atualizada para {self.installed_aurora_version}. Seu perfil, nome, voz, aparência, "
                    "preferências, memória local e modelos foram preservados. O serviço já foi iniciado novamente."
                )
            if self.reboot_status:
                self.reboot_status.set_text("A atualização foi aplicada e o serviço já reiniciou; não é necessário sair da sessão.")
            for button in getattr(self, "done_action_buttons", ()):
                if button.get_label() != "Abrir status do serviço":
                    button.set_visible(False)
        if self._deployment_workspace:
            shutil.rmtree(self._deployment_workspace, ignore_errors=True)
        self._deployment_backup = None
        self._deployment_workspace = None
        self.progress_bar.set_fraction(1.0); self.progress_bar.set_text("100%")
        self.stack.set_visible_child_name("done")
        return False

    def _request_reboot(self, *_):
        self.reboot_status.set_text("Solicitando a reinicialização do sistema…")
        def worker():
            try:
                result = subprocess.run([SYSTEMCTL, "reboot"], capture_output=True, text=True, timeout=30)
                if result.returncode:
                    detail = (result.stderr or result.stdout or "o sistema recusou a reinicialização").strip()
                    message = f"Não consegui reiniciar automaticamente: {detail} Reinicie pelo menu do sistema."
                else:
                    message = "Reinicialização solicitada. A personalização aparecerá no próximo login." if self.onboarding_scheduled else "Reinicialização solicitada."
            except (OSError, subprocess.SubprocessError) as exc:
                message = f"Não consegui solicitar a reinicialização ({type(exc).__name__}). Reinicie pelo menu do sistema."
            GLib.idle_add(self.reboot_status.set_text, message)
        threading.Thread(target=worker, daemon=True).start()
        return False

    def _request_logout(self, *_):
        self.reboot_status.set_text("Solicitando encerramento da sessão…")
        def worker():
            command = shutil.which("gnome-session-quit")
            if not command:
                message = "Não encontrei o comando de sessão do GNOME. Encerre a sessão pelo menu do sistema."
            else:
                try:
                    result = subprocess.run([command, "--logout", "--no-prompt"], capture_output=True,
                                            text=True, timeout=30)
                    message = ("Sessão encerrada. A personalização aparecerá no próximo login."
                               if result.returncode == 0 else
                               f"Não consegui encerrar a sessão: {(result.stderr or result.stdout or 'o GNOME recusou o pedido').strip()}")
                except (OSError, subprocess.SubprocessError) as exc:
                    message = f"Não consegui encerrar a sessão ({type(exc).__name__}). Use o menu do sistema."
            GLib.idle_add(self.reboot_status.set_text, message)
        threading.Thread(target=worker, daemon=True).start()
        return False

    def _install_failed(self, message: str):
        if self.aurora_update_mode:
            self.aurora_update_in_progress = False
        if self.failed_operation == "uninstall":
            self.progress_title.set_text("A remoção foi interrompida")
            self.progress_subtitle.set_text("Leia o detalhe abaixo. A nova tentativa continuará a remoção dos itens restantes.")
        elif self.failed_operation == "update":
            self.progress_title.set_text("A atualização foi interrompida")
            self.progress_subtitle.set_text("As configurações do usuário não foram apagadas. Leia o detalhe e tente novamente.")
        else:
            self.progress_title.set_text("A instalação foi interrompida")
            self.progress_subtitle.set_text("Leia o último detalhe abaixo. Os arquivos baixados ficam disponíveis para tentar novamente.")
        self._append(message)
        self.failed = True
        self.cancel_button.set_label("Tentar novamente")
        self.cancel_button.set_sensitive(True)
        return False

    def _progress_action(self, *_):
        if self.failed:
            self.failed = False
            self.cancel_button.set_label("Fechar janela")
            self.cancel_button.set_sensitive(False)
            if self.failed_operation == "uninstall":
                self.stack.set_visible_child_name("progress")
                threading.Thread(target=self._uninstall_worker, args=self.last_uninstall_options, daemon=True).start()
            else:
                self._start_install()
        else:
            self.window.close()

    def _show_service_status(self, *_):
        try:
            result = subprocess.run([SYSTEMCTL, "--user", "--no-pager", "--full", "status", "aurora.service"], capture_output=True, text=True, timeout=15)
        except subprocess.TimeoutExpired:
            dialog = Gtk.Dialog(title="Status indisponível", transient_for=self.window, modal=True)
            dialog.add_button("Fechar", Gtk.ResponseType.CLOSE)
            box = dialog.get_content_area()
            box.set_margin_top(18); box.set_margin_bottom(18); box.set_margin_start(18); box.set_margin_end(18)
            box.append(self._label(
                "O serviço não respondeu dentro do tempo limite. Tente consultar o status novamente mais tarde.",
                "status-warn", True,
            ))
            dialog.connect("response", lambda d, _r: d.close())
            dialog.present()
            return
        dialog = Gtk.Dialog(title="Status da Aurora", transient_for=self.window, modal=True)
        dialog.add_button("Fechar", Gtk.ResponseType.CLOSE)
        box = dialog.get_content_area()
        box.set_margin_top(18); box.set_margin_bottom(18); box.set_margin_start(18); box.set_margin_end(18)
        view = Gtk.TextView(editable=False, monospace=True, wrap_mode=Gtk.WrapMode.WORD_CHAR)
        view.get_buffer().set_text(result.stdout or result.stderr or "systemctl não retornou detalhes.")
        view.set_size_request(650, 300)
        box.append(view)
        dialog.connect("response", lambda d, _r: d.close())
        dialog.present()

    def _repair_install(self, *_):
        """Stop the current service and rebuild its user unit without downloading."""
        if self.repair_button:
            self.repair_button.set_sensitive(False)
        self.failed_operation = "repair"
        self.stack.set_visible_child_name("progress")
        self.lines.clear()
        self._append("Parando a Aurora com segurança…")
        self.cancel_button.set_sensitive(False)
        threading.Thread(target=self._repair_worker, daemon=True).start()

    def _repair_worker(self):
        try:
            self._set_stage("1/4 · Parando a Aurora", "Encerrando o serviço atual antes de corrigir a instalação.", .15)
            stop = subprocess.run([SYSTEMCTL, "--user", "stop", "aurora.service"], capture_output=True, text=True, timeout=30)
            if stop.returncode:
                raise RuntimeError((stop.stderr or stop.stdout or "Não consegui parar aurora.service.").strip())
            data_root = Path(os.environ.get("XDG_DATA_HOME", str(Path.home()/".local/share"))) / "aurora"
            whisper_model = data_root / "models/ggml-base-q5_1.bin"
            if not voice_assets_ready(MANAGED_APP, whisper_model):
                self._set_stage("2/4 · Reparando reconhecimento de voz", "Conferindo o Vosk e restaurando o modelo Whisper local ausente.", .40)
                run_process([str(MANAGED_APP / "setup-voice.sh")], self._stream_line, cwd=MANAGED_APP, timeout=1800)
            self._set_stage("3/4 · Reinstalando o serviço", "Recriando o arquivo do serviço a partir da instalação gerenciada.", .65)
            run_process([str(MANAGED_APP / "install-desktop.sh")], self._stream_line, cwd=MANAGED_APP, timeout=180)
            self._set_stage("4/4 · Confirmando", "Aguardando o serviço ficar ativo.", .85)
            active = subprocess.run([SYSTEMCTL, "--user", "is-active", "--quiet", "aurora.service"], timeout=15).returncode == 0
            if not active:
                raise RuntimeError("O serviço foi reparado, mas não ficou ativo; confira o status e o journal.")
            GLib.idle_add(self._repair_done)
        except Exception as exc:
            GLib.idle_add(self._install_failed, str(exc))

    def _repair_done(self):
        self._set_stage("Reparo concluído", "A Aurora foi iniciada novamente.", 1.0)
        self.cancel_button.set_sensitive(True)
        self.cancel_button.set_label("Fechar janela")
        return False

    def _confirm_uninstall(self, *_):
        dialog = Gtk.Dialog(title="Remover Aurora", transient_for=self.window, modal=True)
        dialog.add_button("Cancelar", Gtk.ResponseType.CANCEL)
        dialog.add_button("Remover Aurora", Gtk.ResponseType.ACCEPT)
        content = dialog.get_content_area()
        content.set_spacing(10); content.set_margin_top(18); content.set_margin_bottom(18); content.set_margin_start(18); content.set_margin_end(18)
        content.append(Gtk.Label(label="A ação remove o serviço e os arquivos da Aurora deste usuário. Ela não remove o Ollama do sistema.", xalign=0, wrap=True))
        self.remove_data = Gtk.CheckButton(label="Apagar também configurações, memória e logs em ~/.config/aurora e ~/.local/state/aurora")
        self.remove_models = Gtk.CheckButton(label="Apagar apenas modelos Gemma baixados pelo Launchpad e registrados por ele")
        self.remove_rpm = Gtk.CheckButton(label="Remover também o RPM Aurora Studio (pode pedir autenticação)")
        self.remove_rpm.set_active(is_rpm_install())
        content.append(self.remove_data); content.append(self.remove_models); content.append(self.remove_rpm)
        content.append(Gtk.Label(label="Modelos já existentes antes da instalação nunca serão apagados. Preferências e modelos ficam preservados se as opções acima não forem marcadas.", xalign=0, wrap=True))
        dialog.connect("response", self._uninstall_response)
        dialog.present()

    def _uninstall_response(self, dialog, response):
        remove_data = self.remove_data.get_active()
        remove_models = self.remove_models.get_active()
        remove_rpm = self.remove_rpm.get_active()
        dialog.close()
        if response != Gtk.ResponseType.ACCEPT:
            return
        self.failed_operation = "uninstall"
        self.last_uninstall_options = (remove_data, remove_models, remove_rpm)
        self.stack.set_visible_child_name("progress")
        self._set_stage("Removendo Aurora", "Parando o serviço e limpando os itens escolhidos.", .1)
        threading.Thread(target=self._uninstall_worker, args=(remove_data, remove_models, remove_rpm), daemon=True).start()

    def _uninstall_worker(self, remove_data: bool, remove_models: bool, remove_rpm: bool):
        try:
            self._set_stage("1/4 · Parando o serviço", "Desabilitando o serviço aurora.service da sessão.", .16)
            unit = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home()/".config"))) / "systemd/user/aurora.service"
            stop = subprocess.run([SYSTEMCTL, "--user", "disable", "--now", "aurora.service"], capture_output=True, text=True, timeout=30)
            active = subprocess.run([SYSTEMCTL, "--user", "is-active", "--quiet", "aurora.service"], timeout=15).returncode == 0
            if active or (unit.exists() and stop.returncode != 0):
                detail = (stop.stderr or stop.stdout or "o serviço ainda está ativo").strip()
                raise RuntimeError(f"Não removi os arquivos porque não consegui parar aurora.service: {detail}")
            if unit.is_symlink():
                raise RuntimeError("O arquivo aurora.service é um link simbólico; ele foi preservado por segurança.")
            unit.unlink(missing_ok=True)
            subprocess.run([SYSTEMCTL, "--user", "daemon-reload"], check=True, timeout=15, capture_output=True, text=True)
            (Path.home()/".local/share/applications/aurora.desktop").unlink(missing_ok=True)
            if remove_models:
                self._set_stage("2/4 · Removendo modelos Aurora", "Removendo somente os modelos que o Launchpad registrou como novos.", .38)
                ollama = shutil.which("ollama", path=SYSTEM_PATH)
                if ollama:
                    remove_owned_models(ollama, OWNED_MODELS, lambda cmd: run_process(cmd, self._stream_line, timeout=180))
            memory_file = MANAGED_APP / "aurora-memory.json"
            if not remove_data and memory_file.is_file() and not memory_file.is_symlink():
                PRESERVED_MEMORY.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                PRESERVED_MEMORY.parent.chmod(0o700)
                shutil.copy2(memory_file, PRESERVED_MEMORY)
                PRESERVED_MEMORY.chmod(0o600)
            if MANAGED_APP.is_symlink():
                MANAGED_APP.unlink(missing_ok=True)
            elif MANAGED_APP.exists():
                shutil.rmtree(MANAGED_APP)
            if remove_data:
                self._set_stage("3/4 · Removendo dados", "Apagando as configurações, a memória local e os logs conforme solicitado.", .61)
                for data_path in (Path.home()/".config/aurora", Path.home()/".local/state/aurora"):
                    if data_path.is_symlink():
                        data_path.unlink()
                    elif data_path.is_dir():
                        shutil.rmtree(data_path)
                    elif data_path.exists():
                        data_path.unlink()
                PRESERVED_MEMORY.unlink(missing_ok=True)
            if remove_rpm and is_rpm_install():
                if not Path(PKEXEC).is_file() or not Path(DNF).is_file():
                    raise RuntimeError("Não encontrei pkexec/dnf para remover o pacote RPM; os arquivos do usuário já foram removidos.")
                self._set_stage("4/4 · Removendo pacote RPM", "O Fedora solicitará autenticação administrativa.", .78)
                run_process([PKEXEC, DNF, "remove", "--setopt=clean_requirements_on_remove=False", "-y", "aurora-launchpad"], self._stream_line, timeout=600)
            GLib.idle_add(self._uninstall_done)
        except Exception as exc:
            GLib.idle_add(self._install_failed, str(exc))

    def _uninstall_done(self):
        self.failed = False
        self.failed_operation = "install"
        self.progress_title.set_text("Aurora removida deste usuário")
        self.progress_subtitle.set_text("O sistema pode precisar de alguns segundos para atualizar o menu de aplicativos.")
        self.progress_bar.set_fraction(1); self.progress_bar.set_text("100%")
        self.cancel_button.set_sensitive(True)
        return False


def main():
    app = Launchpad()
    return app.run(None)


if __name__ == "__main__":
    raise SystemExit(main())
