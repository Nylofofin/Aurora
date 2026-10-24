#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-only
"""Animated Fedora Workstation setup wizard for Aurora Desktop."""
from __future__ import annotations

import os
from pathlib import Path
import http.client
import queue
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.request

import gi
import cairo
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
    format_size,
    missing_models,
    ollama_tags_response_ready,
    reject_symlinks_in_tree,
    remove_owned_models,
    validate_ollama_installer,
)


APP_ID = "com.nylofofin.AuroraLaunchpad"
INSTALLER_VERSION = "0.1.0"
PKEXEC = "/usr/bin/pkexec"
SYSTEMCTL = "/usr/bin/systemctl"
DNF = "/usr/bin/dnf"
SYSTEM_PATH = "/usr/local/bin:/usr/bin:/bin"
PAYLOAD_CANDIDATES = (
    Path("/usr/share/aurora-launchpad/payload"),
    Path(__file__).resolve().parents[1] / "payload",
    Path(__file__).resolve().parents[1],
)
MANAGED_APP = Path.home() / ".local/share/aurora"
OWNED_MODELS = Path.home() / ".local/share/aurora-launchpad/owned-models.txt"
PRESERVED_MEMORY = Path.home() / ".local/share/aurora-launchpad/aurora-memory.json"
CSS = """
window.launchpad { background: #0c1020; color: #f4f4ff; }
.hero { background: linear-gradient(145deg, #171a34, #20234a 60%, #161d3b); border: 1px solid alpha(#b5b8ff, .14); border-radius: 28px; padding: 26px; }
.panel { background: alpha(#202641, .90); border: 1px solid alpha(#c3c8ff, .13); border-radius: 20px; padding: 20px; }
.subtle { color: #b4bad5; }
.caption { color: #9ba4c7; font-size: 11px; letter-spacing: .12em; font-weight: 700; }
.title-1 { font-size: 31px; font-weight: 750; letter-spacing: -.035em; }
.title-2 { font-size: 20px; font-weight: 700; }
.status-good { color: #8de8cf; }
.status-bad { color: #ffb3bd; }
.status-warn { color: #f5d995; }
.step { color: #d8ddf6; font-size: 13px; }
.log { font-family: monospace; font-size: 11px; color: #b7c2e2; }
progressbar trough { min-height: 10px; border-radius: 99px; background: #292e4b; }
progressbar progress { min-height: 10px; border-radius: 99px; background: linear-gradient(90deg, #8274ff, #69c9ff); }
button.suggested-action { background: linear-gradient(100deg, #786aff, #6bbdff); color: #10152b; font-weight: 750; }
button.pill { border-radius: 999px; }
checkbutton { color: #e3e8ff; }
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


def payload_root() -> Path:
    for candidate in PAYLOAD_CANDIDATES:
        if (candidate / "aurora.py").is_file():
            return candidate
    raise RuntimeError("Não encontrei os arquivos da Aurora incluídos no pacote.")


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


class Orb(Gtk.DrawingArea):
    """Lightweight Cairo orb with continuous, interpolated internal motion."""

    def __init__(self, size: int = 176):
        super().__init__(width_request=size, height_request=size)
        self.phase = 0.0
        self.set_draw_func(self._draw)
        GLib.timeout_add(16, self._tick)

    def _tick(self) -> bool:
        self.phase = (self.phase + 0.018) % (2 * 3.14159)
        self.queue_draw()
        return True

    def _draw(self, area, cr, width, height):
        import math
        size = min(width, height) * 0.88
        x, y = width / 2, height / 2
        radius = size / 2
        pulse = 1.0 + 0.018 * math.sin(self.phase * 1.35)
        r = radius * pulse
        glow = cairo.RadialGradient(x, y, r * .72, x, y, r * 1.65)
        glow.add_color_stop_rgba(0, .42, .37, 1.0, .12)
        glow.add_color_stop_rgba(1, .42, .37, 1.0, 0)
        cr.set_source(glow); cr.arc(x, y, r * 1.65, 0, 2 * math.pi); cr.fill()
        cr.save(); cr.arc(x, y, r, 0, 2 * math.pi); cr.clip()
        base = cairo.LinearGradient(x - r*.7, y - r, x + r*.6, y + r)
        base.add_color_stop_rgb(0, .96, .98, 1.0)
        base.add_color_stop_rgb(.37, .78, .79, 1.0)
        base.add_color_stop_rgb(.72, .48, .44, .94)
        base.add_color_stop_rgb(1, .21, .49, .92)
        cr.set_source(base); cr.paint()
        # Slow luminous color fields move within the sphere, not around it.
        for index, (dx, dy, color, speed) in enumerate([
            (-.35, .37, (.15, .63, 1.0), 1.0),
            (.39, .29, (.58, .31, 1.0), -.76),
            (.03, -.37, (.94, .92, 1.0), .53),
        ]):
            angle = self.phase * speed + index * 2.1
            bx = x + r * (dx + .13 * math.sin(angle))
            by = y + r * (dy + .12 * math.cos(angle * .83))
            blob = cairo.RadialGradient(bx, by, 1, bx, by, r * .72)
            blob.add_color_stop_rgba(0, *color, .48)
            blob.add_color_stop_rgba(1, *color, 0)
            cr.set_source(blob); cr.arc(bx, by, r*.72, 0, 2*math.pi); cr.fill()
        # Glass reflection and a very soft lower shadow.
        cr.set_source_rgba(1, 1, 1, .35)
        cr.save(); cr.translate(x - r*.24, y - r*.48); cr.scale(1.0, .29)
        cr.arc(0, 0, r*.62, 0, 2*math.pi); cr.fill(); cr.restore()
        cr.set_source_rgba(.08, .19, .62, .13)
        cr.rectangle(x-r, y+r*.35, 2*r, r*.65); cr.fill()
        cr.restore()
        cr.set_source_rgba(.80, .84, 1.0, .34)
        cr.set_line_width(1.2); cr.arc(x, y, r, 0, 2*math.pi); cr.stroke()


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
        self.install_button = None
        self.report = None
        self.ollama = shutil.which("ollama", path=SYSTEM_PATH)
        self.existing_install = (MANAGED_APP / "aurora.py").is_file()
        self.failed = False
        self.failed_operation = "install"
        self.last_uninstall_options = (False, False, False)
        self.lines: list[str] = []

    def on_activate(self, _app):
        if self.window:
            self.window.present()
            return
        Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.FORCE_DARK)
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS.encode())
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.report = assess_environment(read_os_release(), dict(os.environ), memory_total_bytes(), disk_free_bytes(Path.home()))
        self.window = Adw.ApplicationWindow(application=self, title="Aurora Launchpad", default_width=930, default_height=720)
        self.window.add_css_class("launchpad")
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        header = Adw.HeaderBar()
        header.set_title_widget(Gtk.Label(label="Aurora Launchpad"))
        header.add_css_class("flat")
        outer.append(header)
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, transition_duration=240)
        self.stack.add_named(self._welcome_page(), "welcome")
        self.stack.add_named(self._review_page(), "review")
        self.stack.add_named(self._progress_page(), "progress")
        self.stack.add_named(self._done_page(), "done")
        outer.append(self.stack)
        self.window.set_content(outer)
        self.window.present()

    def _page(self, child: Gtk.Widget) -> Gtk.Widget:
        scroll = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_child(child)
        return scroll

    def _column(self, spacing=18) -> Gtk.Box:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=spacing)
        box.set_margin_top(26); box.set_margin_bottom(24); box.set_margin_start(34); box.set_margin_end(34)
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
        hero = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=24)
        hero.add_css_class("hero")
        orb = Orb()
        hero.append(orb)
        text_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=11, valign=Gtk.Align.CENTER, hexpand=True)
        text_col.append(self._label("FEDORA WORKSTATION · GNOME · WAYLAND", "caption"))
        text_col.append(self._label("Um primeiro despertar\npara a Aurora.", "title-1", True))
        text_col.append(self._label("O Launchpad prepara os componentes, configura o serviço da sua sessão e mostra cada etapa. Você acompanha tudo antes de confirmar.", "subtle", True))
        hero.append(text_col); col.append(hero)

        status = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        status.add_css_class("panel")
        status.append(self._label("VERIFICAÇÃO DO AMBIENTE", "caption"))
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
            status.append(self._label("Este alpha instala somente no Fedora Workstation com GNOME em Wayland.", "status-bad", True))
        col.append(status)
        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12, halign=Gtk.Align.END)
        if self.existing_install:
            actions.append(self._button("Remover Aurora…", self._confirm_uninstall))
        actions.append(self._button("Revisar instalação", self._show_review, suggested=True))
        col.append(actions)
        col.append(self._label("A Aurora pode usar vários gigabytes para os modelos Gemma. Nenhum download começa antes de você confirmar o plano.", "subtle", True))
        return self._page(col)

    def _review_page(self) -> Gtk.Widget:
        col = self._column()
        col.append(self._label("Seu plano de instalação", "title-1"))
        col.append(self._label("Confira o que será feito neste usuário e no sistema antes de iniciar.", "subtle", True))
        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        panel.add_css_class("panel")
        items = [
            ("Aurora Desktop", "Copiar a aplicação para ~/.local/share/aurora e manter preferências existentes."),
            ("Dependências Python", "Criar um ambiente virtual privado e instalar os pacotes usados pela Aurora."),
            ("Voz local", "Baixar o modelo português Vosk (aprox. 31 MiB). Google STT e Edge TTS continuam usando internet quando chamados."),
            ("Motor local", "Se faltar, instalar a versão auditada do script oficial. A etapa administrativa pode substituir arquivos do Ollama, criar seu usuário/serviço, ajustar grupos e instalar suporte de GPU; em alguns casos, adiciona repositório e driver NVIDIA."),
            ("Modelos Gemma", "Instalar os modelos de conversa e ferramentas. Download de até cerca de 6 GiB se ainda não estiverem disponíveis."),
            ("Inicialização", "Criar o serviço aurora.service da sua sessão, habilitá-lo e iniciar a Aurora."),
        ]
        for title, description in items:
            row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
            row.append(self._label("✓  " + title, "title-2"))
            row.append(self._label(description, "subtle", True))
            panel.append(row)
        col.append(panel)
        self.model_ack = Gtk.CheckButton(label="Entendi que os modelos podem baixar até cerca de 6 GiB e que instalar o Ollama pode alterar pacotes, serviços, grupos e drivers do sistema após autenticação administrativa.")
        self.model_ack.set_active(False)
        col.append(self.model_ack)
        nav = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12, halign=Gtk.Align.END)
        nav.append(self._button("Voltar", lambda *_: self.stack.set_visible_child_name("welcome")))
        self.install_button = self._button("Instalar Aurora", self._start_install, suggested=True)
        self.install_button.set_sensitive(False)
        self.model_ack.connect("toggled", lambda button: self.install_button.set_sensitive(button.get_active() and self.report.supported and self.report.free_gib >= 10))
        nav.append(self.install_button); col.append(nav)
        col.append(self._label("Se já existir uma instalação, o serviço será apontado para a cópia gerenciada pelo Launchpad. A pasta antiga não será apagada.", "subtle", True))
        return self._page(col)

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
        col.append(self._label("A instalação terminou e o serviço da sua sessão foi iniciado. Não é necessário reiniciar o computador; teste dizendo “Aurora”.", "subtle", True))
        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12, halign=Gtk.Align.END)
        buttons.append(self._button("Abrir status do serviço", self._show_service_status))
        buttons.append(self._button("Concluir", lambda *_: self.window.close(), suggested=True))
        col.append(buttons)
        return self._page(col)

    def _show_review(self, *_):
        if not self.report.supported:
            self.progress_title.set_text("Ambiente ainda não suportado")
            self.stack.set_visible_child_name("progress")
            self._append("Use Fedora Workstation em GNOME/Wayland.")
            return
        if self.report.free_gib < 10:
            self.progress_title.set_text("Falta espaço livre")
            self.stack.set_visible_child_name("progress")
            self._append("Libere pelo menos 10 GiB antes de continuar.")
            return
        if not self.ollama and not Path(PKEXEC).is_file():
            self.progress_title.set_text("Falta autenticação do sistema")
            self.stack.set_visible_child_name("progress")
            self._append("Ollama não está instalado e o utilitário pkexec não está disponível.")
            return
        self.stack.set_visible_child_name("review")

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
        if not self.model_ack.get_active():
            return
        self.failed_operation = "install"
        self.stack.set_visible_child_name("progress")
        self.lines.clear(); self._append("Preparando o ambiente…")
        self.cancel_button.set_sensitive(False)
        threading.Thread(target=self._install_worker, daemon=True).start()

    def _set_stage(self, title: str, detail: str, fraction: float):
        GLib.idle_add(self._status, title, detail, fraction, title)

    def _stream_line(self, line: str):
        if line.strip():
            GLib.idle_add(self._status, None, None, None, line)

    def _install_worker(self):
        try:
            source = payload_root()
            self._set_stage("1/7 · Preparando os arquivos", "Copiando o pacote para a pasta privada deste usuário.", .06)
            self._install_payload(source)
            self._migrate_existing_memory()
            self._set_stage("2/7 · Preparando dependências", "Criando o ambiente Python e instalando os pacotes da Aurora.", .16)
            run_process([str(MANAGED_APP / "run.sh"), "--setup-only"], self._stream_line, cwd=MANAGED_APP, timeout=1800)
            self._set_stage("3/7 · Preparando a voz", "Baixando o reconhecedor português Vosk.", .31)
            run_process([str(MANAGED_APP / "setup-voice.sh")], self._stream_line, cwd=MANAGED_APP, timeout=1800)
            self.ollama = shutil.which("ollama", path=SYSTEM_PATH)
            if not self.ollama:
                self._set_stage("4/7 · Instalando Ollama", "O instalador oficial solicitará autenticação do sistema.", .43)
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
            self._set_stage("7/7 · Ativando a Aurora", "Configurando o serviço da sessão e iniciando a bolha.", .94)
            stop_old = subprocess.run([SYSTEMCTL, "--user", "stop", "aurora.service"], capture_output=True, text=True, timeout=30)
            if stop_old.returncode and subprocess.run([SYSTEMCTL, "--user", "is-active", "--quiet", "aurora.service"], timeout=15).returncode == 0:
                raise RuntimeError("Não consegui parar a instalação anterior da Aurora; não vou substituir seus arquivos enquanto o serviço estiver ativo.")
            run_process([str(MANAGED_APP / "install-desktop.sh")], self._stream_line, cwd=MANAGED_APP, timeout=180)
            active = subprocess.run([SYSTEMCTL, "--user", "is-active", "--quiet", "aurora.service"], timeout=15).returncode == 0
            if not active:
                raise RuntimeError("O serviço foi configurado, mas não ficou ativo. Consulte journalctl --user -u aurora.service.")
            GLib.idle_add(self._finish_install)
        except Exception as exc:
            GLib.idle_add(self._install_failed, str(exc))

    def _install_payload(self, source: Path):
        ignored = {".git", ".venv", "__pycache__", ".pytest_cache", "android-client", "tests", "reports", ".github", "packaging", "launchpad"}
        try:
            reject_symlinks_in_tree(source)
            reject_symlinks_in_tree(MANAGED_APP)
        except ValueError as exc:
            raise RuntimeError(str(exc)) from exc
        MANAGED_APP.mkdir(parents=True, exist_ok=True)
        MANAGED_APP.chmod(0o700)
        for entry in source.iterdir():
            if entry.name in ignored or entry.name.endswith("-preview.png"):
                continue
            dest = MANAGED_APP / entry.name
            if entry.is_symlink():
                raise RuntimeError(f"O pacote contém um link simbólico inesperado: {entry.name}.")
            if dest.exists() and dest.is_symlink():
                raise RuntimeError(f"O destino já contém um link simbólico: {dest.name}. Ele não será sobrescrito.")
            if entry.is_dir():
                shutil.copytree(entry, dest, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".venv", "vosk-model"))
            else:
                shutil.copy2(entry, dest)
        for script in ("run.sh", "start-alpha.sh", "install-desktop.sh", "install-service.sh", "setup-voice.sh", "uninstall-service.sh"):
            path = MANAGED_APP / script
            if path.is_file():
                path.chmod(path.stat().st_mode | 0o111)

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
            raise RuntimeError(f"{exc} Atualize o Launchpad antes de continuar.") from exc
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

    def _finish_install(self):
        self.progress_bar.set_fraction(1.0); self.progress_bar.set_text("100%")
        self.stack.set_visible_child_name("done")
        return False

    def _install_failed(self, message: str):
        if self.failed_operation == "uninstall":
            self.progress_title.set_text("A remoção foi interrompida")
            self.progress_subtitle.set_text("Leia o detalhe abaixo. A nova tentativa continuará a remoção dos itens restantes.")
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
        result = subprocess.run([SYSTEMCTL, "--user", "--no-pager", "--full", "status", "aurora.service"], capture_output=True, text=True, timeout=15)
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

    def _confirm_uninstall(self, *_):
        dialog = Gtk.Dialog(title="Remover Aurora", transient_for=self.window, modal=True)
        dialog.add_button("Cancelar", Gtk.ResponseType.CANCEL)
        dialog.add_button("Remover Aurora", Gtk.ResponseType.ACCEPT)
        content = dialog.get_content_area()
        content.set_spacing(10); content.set_margin_top(18); content.set_margin_bottom(18); content.set_margin_start(18); content.set_margin_end(18)
        content.append(Gtk.Label(label="A ação remove o serviço e os arquivos da Aurora deste usuário. Ela não remove o Ollama do sistema.", xalign=0, wrap=True))
        self.remove_data = Gtk.CheckButton(label="Apagar também configurações, memória e logs em ~/.config/aurora e ~/.local/state/aurora")
        self.remove_models = Gtk.CheckButton(label="Apagar apenas modelos Gemma baixados pelo Launchpad e registrados por ele")
        self.remove_rpm = Gtk.CheckButton(label="Remover também o RPM Aurora Launchpad (pode pedir autenticação)")
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
