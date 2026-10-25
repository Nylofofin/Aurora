# SPDX-License-Identifier: GPL-3.0-only
"""First-boot personalization wizard for the desktop client."""
from __future__ import annotations

import asyncio
import math
import time
from PySide6.QtCore import (QEasingCurve, QParallelAnimationGroup, QPropertyAnimation,
                            QPoint, Qt, QThread, Signal, QTimer, QUrl)
from PySide6.QtGui import QColor, QPainter, QPainterPath, QRadialGradient, QLinearGradient, QPen
from PySide6.QtMultimedia import QSoundEffect
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QDialog, QFrame, QGraphicsOpacityEffect, QGridLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QRadioButton, QStackedWidget, QVBoxLayout, QWidget,
)

from ..config import VOSK_PATH
from ..voice.wake import wake_name_supported, wake_name_words
from ..voice.profile import enroll as enroll_wake_profile, validate_recording


SUPPORTED_VOICES = (
    ("pt-BR-ThalitaMultilingualNeural", "Thalita", "Feminina"),
    ("pt-BR-FranciscaNeural", "Francisca", "Feminina"),
    ("pt-BR-AntonioNeural", "Antonio", "Masculina"),
)

# Public appearance catalog shared by onboarding and the live orb.  Keep the
# keys stable so a saved preference survives upgrades.
BUBBLE_STYLES = (
    ("boreal", "Névoa Boreal", "Azul e violeta · cristalino"),
    ("emerald", "Pulso Esmeralda", "Verde vivo · energia fresca"),
    ("crimson", "Flare Carmesim", "Vermelho intenso · presença forte"),
    ("amethyst", "Ametista Nebular", "Roxo profundo · brilho cósmico"),
    ("solaris", "Halo Solaris", "Dourado solar · calor suave"),
    ("ocean", "Maré de Cobalto", "Ciano e azul · fluxo líquido"),
)
BUBBLE_STYLE_KEYS = {key for key, _title, _detail in BUBBLE_STYLES}


class _AnimatedOrb(QWidget):
    """Small, continuously animated preview of the selected orb finish."""
    def __init__(self, style="boreal", parent=None):
        super().__init__(parent)
        self.style = style
        self.phase = 0.0
        self.setFixedSize(126, 126)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def _tick(self):
        # 60/30 Hz friendly motion: two incommensurate waves keep the light
        # field moving continuously without making the orb wobble or jump.
        self.phase = (self.phase + 0.026) % (math.tau)
        self.update()

    def paintEvent(self, _event):
        size = min(self.width(), self.height()) - 10
        rect_x = (self.width() - size) / 2
        rect_y = (self.height() - size) / 2
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.translate(rect_x, rect_y)
        base = QColor("#eafaff")
        lower = QColor("#177ff2")
        violet = QColor("#7950d8")
        if self.style == "emerald":
            base, lower, violet = QColor("#f5fff8"), QColor("#32d583"), QColor("#0b8f66")
        elif self.style == "crimson":
            base, lower, violet = QColor("#fff8f8"), QColor("#ff5c6c"), QColor("#b51e52")
        elif self.style == "amethyst":
            base, lower, violet = QColor("#fbf5ff"), QColor("#a66cff"), QColor("#5427b8")
        elif self.style == "solaris":
            base, lower, violet = QColor("#fffbed"), QColor("#ffbd4a"), QColor("#e66b24")
        elif self.style == "ocean":
            base, lower, violet = QColor("#effcff"), QColor("#22c7d9"), QColor("#1558ba")
        circle = QPainterPath()
        circle.addEllipse(2, 2, size-4, size-4)
        painter.setClipPath(circle)
        gradient = QLinearGradient(0, 0, size * .12, size)
        gradient.setColorAt(0, base)
        gradient.setColorAt(.50, QColor("#d9f3ff"))
        gradient.setColorAt(.73, lower)
        gradient.setColorAt(1, violet)
        painter.fillPath(circle, gradient)
        # Slow, overlapping color fields create motion inside the sphere itself.
        drift_x = math.sin(self.phase) * size * .12
        drift_y = math.cos(self.phase * .8) * size * .08
        field = QRadialGradient(size*.48 + drift_x, size*.70 + drift_y, size*.65)
        field.setColorAt(0, QColor(violet.red(), violet.green(), violet.blue(), 110))
        field.setColorAt(.58, QColor(lower.red(), lower.green(), lower.blue(), 92))
        field.setColorAt(1, QColor(lower.red(), lower.green(), lower.blue(), 0))
        painter.fillPath(circle, field)
        # Match the live orb's refractive surface so the onboarding preview
        # represents the selected finish instead of a static approximation.
        refraction = math.sin(self.phase * 0.63) * size * 0.16
        fold = QLinearGradient(-size * .18 + refraction, size * .28,
                               size * .92 + refraction, size * .72)
        fold.setColorAt(0.00, QColor(255, 255, 255, 0))
        fold.setColorAt(0.44, QColor(255, 255, 255, 24))
        fold.setColorAt(0.52, QColor(255, 255, 255, 92))
        fold.setColorAt(0.60, QColor(255, 255, 255, 18))
        fold.setColorAt(1.00, QColor(255, 255, 255, 0))
        refraction_path = QPainterPath()
        refraction_path.addEllipse(-size * .08 + refraction, size * .27,
                                   size * 1.16, size * .42)
        painter.fillPath(refraction_path, fold)
        shine = QRadialGradient(size*.31, size*.22, size*.48)
        shine.setColorAt(0, QColor(255, 255, 255, 235))
        shine.setColorAt(.35, QColor(255, 255, 255, 120))
        shine.setColorAt(1, QColor(255, 255, 255, 0))
        painter.fillPath(circle, shine)
        painter.setClipping(False)
        painter.setPen(QPen(QColor(255,255,255,210), 1.2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(2, 2, size-4, size-4)
        painter.end()


class _StyleCard(QFrame):
    def __init__(self, key, title, detail, parent=None):
        super().__init__(parent)
        self.key = key
        self.setObjectName("choiceCard")
        self.setProperty("selected", False)
        self.setMinimumWidth(200)
        self.setMinimumHeight(238)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 15, 16, 15)
        layout.setSpacing(8)
        heading = QLabel(title)
        heading.setObjectName("cardTitle")
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(heading)
        orb = _AnimatedOrb(key)
        orb.setFixedSize(100, 100)
        layout.addWidget(orb, 0, Qt.AlignmentFlag.AlignHCenter)
        caption = QLabel(detail)
        caption.setObjectName("cardDetail")
        caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(caption)
        self.select_button = QPushButton("Selecionar")
        self.select_button.setObjectName("selectStyle")
        layout.addWidget(self.select_button)

    def set_selected(self, selected):
        self.setProperty("selected", bool(selected))
        self.select_button.setText("Selecionado ✓" if selected else "Selecionar")
        self.style().unpolish(self)
        self.style().polish(self)


class _VoiceCard(QFrame):
    def __init__(self, short_name, name, gender, parent=None):
        super().__init__(parent)
        self.short_name = short_name
        self.setObjectName("choiceCard")
        self.setMinimumWidth(218)
        self.setMinimumHeight(250)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 18, 16, 16)
        layout.setSpacing(10)
        heading = QLabel(name)
        heading.setObjectName("cardTitle")
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(heading)
        voice_icon = QLabel("◖  ◗")
        voice_icon.setObjectName("voiceGlyph")
        voice_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        voice_icon.setFixedHeight(82)
        layout.addWidget(voice_icon, 0, Qt.AlignmentFlag.AlignHCenter)
        self.preview_button = QPushButton("▶  Ouvir prévia")
        self.preview_button.setObjectName("previewVoice")
        layout.addWidget(self.preview_button)
        detail = QLabel(f"{gender} · Português (Brasil)")
        detail.setObjectName("cardDetail")
        detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(detail)
        self.radio = QRadioButton("Usar esta voz")
        self.radio.setObjectName("voiceRadio")
        self.radio.setStyleSheet("QRadioButton { spacing: 8px; }")
        layout.addWidget(self.radio, 0, Qt.AlignmentFlag.AlignHCenter)


class _VoiceCatalog(QThread):
    loaded = Signal(object)

    def run(self):
        try:
            import edge_tts
            async def load():
                task=asyncio.create_task(edge_tts.list_voices())
                deadline=time.monotonic()+8
                while not task.done():
                    if self.isInterruptionRequested() or time.monotonic()>=deadline:
                        task.cancel()
                        await asyncio.gather(task,return_exceptions=True)
                        return []
                    await asyncio.sleep(.1)
                return task.result()
            voices = asyncio.run(load())
            self.loaded.emit(voices)
        except Exception:
            self.loaded.emit([])


class _NameCheck(QThread):
    checked = Signal(str, bool, str, bool)

    def __init__(self, name):
        super().__init__()
        self.name = name

    def run(self):
        words = wake_name_words(self.name)
        if not words:
            self.checked.emit(self.name, False, "Use um nome de até quatro palavras.", False)
            return
        try:
            import vosk
            model = vosk.Model(str(VOSK_PATH))
            missing = [word for word in words if not wake_name_supported(word, model)]
            if missing:
                self.checked.emit(self.name, False,
                                  "O modelo de voz não reconhece: " + ", ".join(missing) +
                                  ". Vamos criar um perfil local com sua voz.", True)
                return
            self.checked.emit(self.name, True, "Nome compatível com o vocabulário do Vosk.", False)
        except Exception as exc:
            if self.isInterruptionRequested():
                return
            self.checked.emit(self.name, False,
                              f"Não consegui validar o modelo ({type(exc).__name__}). Vamos criar um perfil local.", True)


class _WakeCapture(QThread):
    captured = Signal(object)
    failed = Signal(str)

    def run(self):
        try:
            import sounddevice as sd
            audio = sd.rec(int(16_000 * 1.6), samplerate=16_000, channels=1, dtype="int16")
            sd.wait()
            self.captured.emit(audio.tobytes())
        except Exception as exc:
            self.failed.emit(f"Não consegui acessar o microfone ({type(exc).__name__}).")


class PersonalizationWizard(QDialog):
    """Material-inspired, animated first-login setup, returning saved choices."""
    def __init__(self, cfg, speaker, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.speaker = speaker
        self.result_settings = None
        self._voice_map = {}
        self._selected_style = str(cfg.get("bubble_style", "boreal"))
        if self._selected_style not in BUBBLE_STYLE_KEYS:
            self._selected_style = "boreal"
        self._name_worker = None
        self._wake_worker = None
        self._wake_recordings = []
        self._wake_profile = None
        self._needs_training = False
        self._sfx = {}
        self._feedback_sfx = {}
        self._selected_feedback = str(cfg.get("feedback_theme", "boreal"))
        if self._selected_feedback not in {"boreal", "pulse", "void"}:
            self._selected_feedback = "boreal"
        self.setWindowTitle("Personalizar a Aurora")
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        self.setModal(True)
        # Give cards and form fields a real horizontal rhythm.  The previous
        # compact width forced labels and buttons to collide on Fedora fonts.
        self.setMinimumSize(900, 420)
        self.resize(980, 470)
        self._dark_theme = True
        self.setStyleSheet(self._stylesheet(True))

        # Keep the wizard compact on small screens and let the platform palette
        # decide whether text and surfaces should be light or dark.
        self._transition_group = None
        self._selected_voice = str(cfg.get("tts_voice", SUPPORTED_VOICES[0][0]))

        for name in ("select", "step", "success", "error"):
            effect = QSoundEffect(self)
            effect.setSource(QUrl.fromLocalFile(str(__import__("pathlib").Path(__file__).resolve().parents[2] / "assets" / "audio" / f"{name}.wav")))
            effect.setVolume(0.16 if name in {"select", "step"} else (0.22 if name != "error" else 0.30))
            self._sfx[name] = effect
        for theme in ("boreal", "pulse", "void"):
            for direction in ("entrada", "saida"):
                effect = QSoundEffect(self)
                effect.setSource(QUrl.fromLocalFile(str(__import__("pathlib").Path(__file__).resolve().parents[2] / "assets" / "audio" / f"{direction}-{theme}.wav")))
                effect.setVolume(0.28)
                self._feedback_sfx[f"{theme}:{direction}"] = effect

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 18, 22, 16)
        root.setSpacing(10)
        self.eyebrow = QLabel("AURORA · PRIMEIRA CONFIGURAÇÃO")
        self.eyebrow.setObjectName("eyebrow")
        root.addWidget(self.eyebrow)
        self.stack = QStackedWidget()
        self.stack.setGraphicsEffect(QGraphicsOpacityEffect(self.stack))
        self._build_welcome()
        self._build_profile()
        self._build_wake_training()
        self._build_bubble()
        self._build_voice()
        self._build_feedback()
        self._build_loading()
        root.addWidget(self.stack, 1)
        footer = QHBoxLayout()
        self.step_label = QLabel("Boas-vindas  ·  1 de 4")
        footer.addWidget(self.step_label)
        footer.addStretch(1)
        self.back_button = QPushButton("Voltar")
        self.back_button.clicked.connect(self.back)
        footer.addWidget(self.back_button)
        self.next_button = QPushButton("Começar")
        self.next_button.setObjectName("primary")
        self.next_button.setMinimumHeight(44)
        self.next_button.clicked.connect(self.next)
        footer.addWidget(self.next_button)
        root.addLayout(footer)

        self._voice_worker = _VoiceCatalog(self)
        self._voice_worker.loaded.connect(self._populate_voices)
        self._voice_worker.start()
        self._current_page = 0
        self._set_page(0, animated=False)
        self._center()

    def _fit_current_page(self):
        """Keep short pages compact instead of inheriting the tallest page."""
        if not self.stack or not self.stack.currentWidget():
            return
        page_height = self.stack.currentWidget().sizeHint().height()
        page_height = max(270, min(620, page_height))
        self.stack.setFixedHeight(page_height)
        # Header, eyebrow and footer need roughly 118 px around the page.
        target_height = max(420, min(760, page_height + 118))
        if abs(self.height() - target_height) > 4:
            self.resize(self.width(), target_height)
            self._center()

    def _system_prefers_dark(self):
        from PySide6.QtWidgets import QApplication
        palette = QApplication.instance().palette()
        return palette.color(palette.ColorRole.Window).lightness() < 128

    @staticmethod
    def _stylesheet(dark):
        if dark:
            return """
            QDialog { background:#111117; color:#f5f2fa; }
            QLabel { color:#eeeaf5; }
            QLabel#eyebrow { color:#b6acc8; font-size:11px; font-weight:700; letter-spacing:2px; }
            QLabel#title { color:#faf8ff; font-size:25px; font-weight:700; }
            QLabel#subtitle { color:#c5bfce; font-size:14px; }
            QLabel#cardTitle { color:#f4f0fa; font-size:16px; font-weight:700; }
            QLabel#cardDetail { color:#b5afbd; font-size:12px; }
            QLabel#voiceGlyph { color:#c6a8f2; font-size:38px; font-weight:600; }
            QFrame#panel { background:#1b1a22; border:1px solid #35313f; border-radius:22px; }
            QFrame#choiceCard { background:#211f29; border:1px solid #3a3546; border-radius:18px; }
            QFrame#choiceCard[selected="true"] { background:#292238; border:2px solid #b89be9; }
            QLineEdit { background:#24212d; border:1px solid #514961; border-radius:12px; padding:12px 14px; min-height:24px; color:#faf8ff; selection-background-color:#5d477e; }
            QLineEdit:focus { background:#2a2634; border:2px solid #b89be9; padding:11px 13px; }
            QPushButton { background:#302d38; color:#f2eff7; border:0; border-radius:12px; padding:11px 17px; font-weight:600; }
            QPushButton:hover { background:#3d3848; }
            QPushButton#primary { background:#8b6bc2; color:#fff; padding-left:22px; padding-right:22px; }
            QPushButton#primary:hover { background:#a080d8; }
            QPushButton#primary:pressed { background:#7655ae; }
            QPushButton#selectStyle, QPushButton#previewVoice { background:#2d2937; border:1px solid #4a4258; }
            QPushButton#selectStyle:hover, QPushButton#previewVoice:hover { background:#3b3449; }
            QCheckBox, QRadioButton { spacing:9px; color:#d1cbd9; }
            QRadioButton::indicator { width:18px; height:18px; }
            """
        return """
            QDialog { background:#f3f2f8; color:#1b1b22; }
            QLabel { color:#27242d; }
            QLabel#eyebrow { color:#625b70; font-size:11px; font-weight:700; letter-spacing:2px; }
            QLabel#title { color:#1c1b20; font-size:25px; font-weight:700; }
            QLabel#subtitle { color:#5e5b66; font-size:14px; }
            QLabel#cardTitle { color:#25232b; font-size:16px; font-weight:700; }
            QLabel#cardDetail { color:#696673; font-size:12px; }
            QLabel#voiceGlyph { color:#7960ad; font-size:38px; font-weight:600; }
            QFrame#panel { background:#fff; border:1px solid #e5e2ec; border-radius:24px; }
            QFrame#choiceCard { background:#fff; border:1px solid #e2dfe9; border-radius:20px; }
            QFrame#choiceCard[selected="true"] { background:#faf8ff; border:2px solid #7052a8; }
            QLineEdit { background:#fbfaff; border:1px solid #d7d3df; border-radius:13px; padding:13px 15px; min-height:24px; color:#25232b; selection-background-color:#ddd3f1; }
            QLineEdit:focus { background:#fff; border:2px solid #7052a8; padding:12px 14px; }
            QPushButton { background:#eeecf3; color:#302e37; border:0; border-radius:13px; padding:12px 18px; font-weight:600; }
            QPushButton:hover { background:#e5e1ed; }
            QPushButton#primary { background:#6750a4; color:#fff; padding-left:23px; padding-right:23px; }
            QPushButton#primary:hover { background:#7962b4; }
            QPushButton#primary:pressed { background:#57418e; }
            QPushButton#selectStyle, QPushButton#previewVoice { background:#f0edf6; border:1px solid #e3deec; }
            QPushButton#selectStyle:hover, QPushButton#previewVoice:hover { background:#e8e2f2; }
            QCheckBox, QRadioButton { spacing:9px; color:#494451; }
            QRadioButton::indicator { width:18px; height:18px; }
            """

    def _apply_system_theme(self):
        # The onboarding surface intentionally stays dark so its cards and
        # orb previews keep the same identity on every desktop theme.
        if not self._dark_theme:
            self._dark_theme = True
            self.setStyleSheet(self._stylesheet(True))

    def _panel(self, title, subtitle=""):
        frame = QFrame()
        frame.setObjectName("panel")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(9)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        heading = QLabel(title)
        heading.setObjectName("title")
        heading.setWordWrap(True)
        layout.addWidget(heading)
        if subtitle:
            desc = QLabel(subtitle)
            desc.setObjectName("subtitle")
            desc.setWordWrap(True)
            layout.addWidget(desc)
        return frame, layout

    def _build_welcome(self):
        frame, layout = self._panel("Vamos personalizar sua experiência",
                                    "Seu perfil fica salvo apenas neste computador. Você poderá mudar essas escolhas depois.")
        glow = _AnimatedOrb("boreal")
        glow.setFixedSize(180, 180)
        layout.addWidget(glow, 0, Qt.AlignmentFlag.AlignHCenter)
        note = QLabel("Uma bolha, uma voz e um nome que combinam com você.")
        note.setObjectName("subtitle")
        note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(note)
        self.stack.addWidget(frame)

    def _build_profile(self):
        frame, layout = self._panel("Quem está por aqui?", "A Aurora usará esse nome nas saudações, em vez do nome da conta do desktop.")
        columns = QHBoxLayout()
        columns.setSpacing(22)
        user_column = QVBoxLayout(); user_column.setSpacing(8)
        assistant_column = QVBoxLayout(); assistant_column.setSpacing(8)
        self.user_name = QLineEdit(str(self.cfg.get("user_name", "")))
        self.user_name.setPlaceholderText("Ex.: Alex")
        self.user_name.setClearButtonEnabled(True)
        self.user_name.setMinimumHeight(48)
        user_column.addWidget(QLabel("Como devo te chamar?")); user_column.addWidget(self.user_name)
        self.user_name_note = QLabel("Digite como você quer ser chamada na saudação.")
        self.user_name_note.setObjectName("cardDetail")
        user_column.addWidget(self.user_name_note)
        assistant_column.addWidget(QLabel("Nome de ativação da assistente"))
        self.assistant_name = QLineEdit(str(self.cfg.get("assistant_name", "Aurora")))
        self.assistant_name.setPlaceholderText("Ex.: Aurora")
        self.assistant_name.setClearButtonEnabled(True)
        self.assistant_name.setMinimumHeight(48)
        assistant_column.addWidget(self.assistant_name)
        self.default_name = QCheckBox("Nah, prefiro Aurora")
        self.default_name.setChecked(str(self.cfg.get("assistant_name", "Aurora")).casefold() == "aurora")
        self.default_name.toggled.connect(self.assistant_name.setHidden)
        self.default_name.toggled.connect(self._update_preview_phrase)
        self.assistant_name.textChanged.connect(self._update_preview_phrase)
        self.assistant_name.setHidden(self.default_name.isChecked())
        assistant_column.addWidget(self.default_name)
        self.name_note = QLabel("O nome será validado no Vosk. Se alguma palavra não existir, a Aurora oferecerá um treinamento local curto.")
        self.name_note.setWordWrap(True)
        self.name_note.setObjectName("cardDetail")
        assistant_column.addWidget(self.name_note)
        columns.addLayout(user_column, 1)
        columns.addLayout(assistant_column, 1)
        layout.addLayout(columns)
        self.stack.addWidget(frame)

    def _build_wake_training(self):
        frame, layout = self._panel(
            "Vamos reconhecer seu nome",
            "O vocabulário atual não contém esse nome. Grave quatro amostras curtas para criar um perfil local privado.",
        )
        self.wake_training_hint = QLabel(
            "Clique em gravar e diga apenas o nome da assistente. Repita quatro vezes em um tom natural."
        )
        self.wake_training_hint.setObjectName("subtitle")
        self.wake_training_hint.setWordWrap(True)
        layout.addWidget(self.wake_training_hint)
        self.wake_training_status = QLabel("Nenhuma amostra gravada · 0 de 4")
        self.wake_training_status.setObjectName("cardDetail")
        layout.addWidget(self.wake_training_status)
        self.wake_training_button = QPushButton("Gravar amostra 1 de 4")
        self.wake_training_button.setObjectName("primary")
        self.wake_training_button.clicked.connect(self._capture_wake_sample)
        layout.addWidget(self.wake_training_button, 0, Qt.AlignmentFlag.AlignHCenter)
        self.wake_training_note = QLabel(
            "O áudio não é salvo: apenas características acústicas são mantidas nas configurações locais."
        )
        self.wake_training_note.setObjectName("cardDetail")
        self.wake_training_note.setWordWrap(True)
        layout.addWidget(self.wake_training_note)
        self.stack.addWidget(frame)

    def _build_bubble(self):
        frame, layout = self._panel("Vamos personalizar sua bolha", "Veja cada acabamento em movimento e selecione o que combina com você.")
        cards = QGridLayout()
        cards.setHorizontalSpacing(12)
        cards.setVerticalSpacing(12)
        self.style_cards = {}
        choices = BUBBLE_STYLES
        for index, (key, title, detail) in enumerate(choices):
            card = _StyleCard(key, title, detail)
            card.select_button.clicked.connect(lambda _=False, value=key: self._select_style(value))
            self.style_cards[key] = card
            cards.addWidget(card, index // 3, index % 3)
        self._select_style(self._selected_style if self._selected_style in self.style_cards else "boreal")
        layout.addLayout(cards)
        self.stack.addWidget(frame)

    def _build_voice(self):
        frame, layout = self._panel("Escolha a voz da Aurora", "Três vozes em português do Brasil. Ouça uma prévia e marque sua escolha.")
        cards = QHBoxLayout(); cards.setSpacing(14)
        self.voice_group = QButtonGroup(self); self.voice_group.setExclusive(True)
        self.voice_cards = {}
        current = str(self.cfg.get("tts_voice", SUPPORTED_VOICES[0][0]))
        for short, name, gender in SUPPORTED_VOICES:
            card = _VoiceCard(short, name, gender)
            card.radio.setChecked(short == current)
            card.preview_button.clicked.connect(lambda _=False, voice=short: self._preview_voice(voice))
            card.radio.toggled.connect(lambda checked, voice=short: self._select_voice(voice, checked))
            self.voice_group.addButton(card.radio)
            self.voice_cards[short] = card
            cards.addWidget(card, 1)
        if not any(card.radio.isChecked() for card in self.voice_cards.values()):
            self.voice_cards[SUPPORTED_VOICES[0][0]].radio.setChecked(True)
        layout.addLayout(cards)
        soon = QLabel("Mais vozes poderão ser adicionadas em versões futuras.")
        soon.setObjectName("cardDetail"); soon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(soon)
        self.voice_status = QLabel("A prévia usa Edge TTS e precisa de internet.")
        self.voice_status.setObjectName("cardDetail")
        layout.addWidget(self.voice_status)
        self.preview_phrase = QLabel()
        self.preview_phrase.setObjectName("cardDetail")
        self.preview_phrase.setWordWrap(True)
        self.preview_phrase.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.preview_phrase)
        self._update_preview_phrase()
        self.stack.addWidget(frame)

    def _build_feedback(self):
        frame, layout = self._panel(
            "Escolha seus sons",
            "Cada assinatura tem uma entrada e uma saída próprias. Ouça o par antes de salvar.",
        )
        cards = QHBoxLayout(); cards.setSpacing(12)
        self.feedback_group = QButtonGroup(self); self.feedback_group.setExclusive(True)
        self.feedback_cards = {}
        choices = (("boreal", "Boreal", "Cristalino · suave"),
                   ("pulse", "Pulse", "Rítmico · energético"),
                   ("void", "Void", "Profundo · futurista"))
        for key, title, detail in choices:
            card = QFrame(); card.setObjectName("choiceCard")
            card.setMinimumHeight(190)
            card.setProperty("selected", key == self._selected_feedback)
            box = QVBoxLayout(card); box.setContentsMargins(12, 12, 12, 12); box.setSpacing(7)
            heading = QLabel(title); heading.setObjectName("cardTitle"); heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
            box.addWidget(heading)
            caption = QLabel(detail); caption.setObjectName("cardDetail"); caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
            box.addWidget(caption)
            preview_row = QHBoxLayout(); preview_row.setSpacing(6)
            entry_preview = QPushButton("↗  Entrada")
            entry_preview.setObjectName("previewVoice")
            entry_preview.clicked.connect(lambda _=False, value=key: self._preview_feedback(value, "entrada"))
            exit_preview = QPushButton("↘  Saída")
            exit_preview.setObjectName("previewVoice")
            exit_preview.clicked.connect(lambda _=False, value=key: self._preview_feedback(value, "saida"))
            preview_row.addWidget(entry_preview); preview_row.addWidget(exit_preview)
            box.addLayout(preview_row)
            radio = QRadioButton("Usar estes sons")
            radio.setChecked(key == self._selected_feedback)
            radio.toggled.connect(lambda checked, value=key: self._select_feedback(value, checked))
            self.feedback_group.addButton(radio); box.addWidget(radio, 0, Qt.AlignmentFlag.AlignHCenter)
            self.feedback_cards[key] = card
            cards.addWidget(card, 1)
        layout.addLayout(cards)
        self.feedback_status = QLabel("Prévia: entrada … saída …")
        self.feedback_status.setObjectName("cardDetail"); self.feedback_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.feedback_status)
        self.stack.addWidget(frame)

    def _build_loading(self):
        frame, layout = self._panel("Vamos configurar tudo para você…", "Aguarde enquanto aplicamos suas escolhas à Aurora.")
        self.loading_mark = QLabel("◌")
        self.loading_mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.loading_mark.setStyleSheet("font-size:66px;color:#7655ae")
        layout.addWidget(self.loading_mark)
        self._loading_effect = QGraphicsOpacityEffect(self.loading_mark)
        self.loading_mark.setGraphicsEffect(self._loading_effect)
        self._loading_pulse = QPropertyAnimation(self._loading_effect, b"opacity", self)
        self._loading_pulse.setDuration(800)
        self._loading_pulse.setStartValue(0.35)
        self._loading_pulse.setEndValue(1.0)
        self._loading_pulse.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._loading_pulse.setLoopCount(-1)
        self.stack.addWidget(frame)

    def _populate_voices(self, voices):
        # The catalog request is only a reachability check. Keep the UI limited
        # to the three supported Brazilian voices instead of exposing every
        # language returned by Edge TTS.
        available = {str(v.get("ShortName")) for v in voices if isinstance(v, dict)}
        missing = [name for name, _label, _gender in SUPPORTED_VOICES if name not in available]
        self.voice_status.setText(
            "A prévia usa Edge TTS e precisa de internet."
            if not missing else "Catálogo indisponível; as três vozes brasileiras continuam selecionáveis."
        )

    def _select_style(self, key):
        self._selected_style = key
        for name, card in self.style_cards.items():
            card.set_selected(name == key)
        self._play_sfx("select")

    def _select_voice(self, voice, checked):
        if checked:
            self._selected_voice = voice

    def _select_feedback(self, theme, checked):
        if not checked: return
        self._selected_feedback = theme
        for key, card in self.feedback_cards.items():
            card.setProperty("selected", key == theme)
            card.style().unpolish(card); card.style().polish(card)
        self._play_sfx("select")

    def _preview_feedback(self, theme, direction=None):
        entry = self._feedback_sfx.get(f"{theme}:entrada")
        exit_ = self._feedback_sfx.get(f"{theme}:saida")
        if not entry or not exit_ or not entry.source().isValid() or not exit_.source().isValid():
            self.feedback_status.setText("Prévia indisponível")
            return
        for effect in self._feedback_sfx.values(): effect.stop()
        if direction == "entrada":
            self.feedback_status.setText(f"Prévia {theme}: entrada")
            entry.play()
            return
        if direction == "saida":
            self.feedback_status.setText(f"Prévia {theme}: saída")
            exit_.play()
            return
        self.feedback_status.setText("Prévia: entrada …")
        entry.play()
        def play_exit():
            self.feedback_status.setText("Prévia: saída …")
            exit_.play()
        QTimer.singleShot(760, play_exit)

    def _preview_name(self):
        return "Aurora" if self.default_name.isChecked() else (self.assistant_name.text().strip() or "Aurora")

    def _update_preview_phrase(self, *_args):
        phrase = f'“Olá, eu sou {self._preview_name()}. Estou pronta para ajudar.”'
        label = getattr(self, "preview_phrase", None)
        if label is not None:
            label.setText(f"Texto da prévia: {phrase}")

    def _preview_voice(self, voice):
        name = self._preview_name()
        label = next((n for s, n, _ in SUPPORTED_VOICES if s == voice), voice)
        # A preview must replace a previous preview immediately. Otherwise a
        # queued Edge request can make a click appear to do nothing for many
        # seconds while an older sample is still being generated.
        interrupt = getattr(self.speaker, "interrupt", None)
        if callable(interrupt):
            interrupt()
        self.voice_status.setText(f"Reproduzindo prévia de {label}…")
        self.speaker.say_with_voice(f"Olá, eu sou {name}. Estou pronta para ajudar.", voice)
        self._play_sfx("select")

    def _center(self):
        screen = self.screen() or __import__("PySide6.QtWidgets", fromlist=["QApplication"]).QApplication.primaryScreen()
        if screen:
            self.move(screen.availableGeometry().center() - self.rect().center())

    def showEvent(self, event):
        super().showEvent(event)
        self._apply_system_theme()

    def done(self, result):
        for worker in (getattr(self, "_voice_worker", None), getattr(self, "_name_worker", None), getattr(self, "_wake_worker", None)):
            if worker is not None and worker.isRunning():
                worker.requestInterruption()
                worker.wait(2500)
        super().done(result)

    def _set_page(self, page, animated=True):
        previous = self._current_page
        self._current_page = page
        self.stack.setCurrentIndex(page)
        QTimer.singleShot(0, self._fit_current_page)
        self.back_button.setVisible(page > 0 and page < 6)
        labels = (("Boas-vindas · 1 de 6", "Seu perfil · 2 de 6", "Ativação · 3 de 6", "Sua Bolha · 4 de 6", "Sua voz · 5 de 6", "Seus sons · 6 de 6", "")
                  if self._needs_training else
                  ("Boas-vindas · 1 de 5", "Seu perfil · 2 de 5", "", "Sua Bolha · 3 de 5", "Sua voz · 4 de 5", "Seus sons · 5 de 5", ""))
        self.step_label.setText(labels[page])
        self.next_button.setVisible(page < 6)
        self.next_button.setText(("Começar", "Próximo", "Próximo", "Próximo", "Próximo", "Finalizar", "")[page])
        if animated:
            effect = self.stack.graphicsEffect()
            effect.setOpacity(0.0)
            fade = QPropertyAnimation(effect, b"opacity", self)
            fade.setDuration(480)
            fade.setStartValue(0.0)
            fade.setEndValue(1.0)
            fade.setEasingCurve(QEasingCurve.Type.OutCubic)
            # A small directional glide makes the page change feel connected
            # instead of replacing the entire panel in one frame.
            origin = self.stack.pos()
            direction = 1 if page >= previous else -1
            slide = QPropertyAnimation(self.stack, b"pos", self)
            slide.setDuration(480)
            slide.setStartValue(origin + QPoint(18 * direction, 0))
            slide.setEndValue(origin)
            slide.setEasingCurve(QEasingCurve.Type.OutBack)
            group = QParallelAnimationGroup(self)
            group.addAnimation(fade)
            group.addAnimation(slide)
            self._transition_group = group
            group.start()
            self._play_sfx("step")

    def _set_name_checked(self, name, ok, message, needs_training=False):
        self.next_button.setEnabled(True)
        self.name_note.setText(message)
        if ok and name == self.assistant_name.text().strip():
            self._needs_training = False
            self._set_page(3)
        elif needs_training and name == self.assistant_name.text().strip():
            self._needs_training = True
            self._set_page(2)

    def _capture_wake_sample(self):
        if self._wake_worker is not None and self._wake_worker.isRunning():
            return
        if len(self._wake_recordings) >= 4:
            return
        self.wake_training_button.setEnabled(False)
        self.wake_training_status.setText(f'Diga “{self._preview_name()}” agora…')
        self._play_sfx("select")
        self._wake_worker = _WakeCapture(self)
        self._wake_worker.captured.connect(self._wake_sample_captured)
        self._wake_worker.failed.connect(self._wake_capture_failed)
        self._wake_worker.start()

    def _wake_sample_captured(self, pcm):
        valid, reason = validate_recording(pcm)
        if not valid:
            count = len(self._wake_recordings)
            self.wake_training_status.setText(reason)
            self.wake_training_button.setText(f"Gravar amostra {count + 1} de 4")
            self.wake_training_button.setEnabled(True)
            return
        self._wake_recordings.append(bytes(pcm))
        count = len(self._wake_recordings)
        if count >= 4:
            try:
                self._wake_profile = enroll_wake_profile(self._preview_name(), self._wake_recordings)
                self.wake_training_status.setText("Perfil local criado · 4 de 4 amostras válidas")
                self.wake_training_button.setText("Amostras concluídas ✓")
                self.next_button.setEnabled(True)
            except ValueError as exc:
                self.wake_training_status.setText(str(exc))
                self.wake_training_button.setEnabled(True)
        else:
            self.wake_training_status.setText(f"Amostra {count} de 4 concluída")
            self.wake_training_button.setText(f"Gravar amostra {count + 1} de 4")
            self.wake_training_button.setEnabled(True)

    def _wake_capture_failed(self, message):
        self.wake_training_status.setText(message)
        self.wake_training_button.setEnabled(True)

    def next(self):
        if self._current_page == 1 and not self.user_name.text().strip():
            self.user_name_note.setText("Preencha seu nome para a Aurora não depender do nome da conta do desktop.")
            return
        if self._current_page == 1 and not self.default_name.isChecked():
            name = self.assistant_name.text().strip()
            if not name:
                self.name_note.setText("Digite um nome ou marque “Nah, prefiro Aurora”.")
                return
            self.next_button.setEnabled(False)
            self.name_note.setText("Conferindo o nome no vocabulário de voz instalado…")
            self._name_worker = _NameCheck(name)
            self._name_worker.checked.connect(self._set_name_checked)
            self._name_worker.start()
            return
        if self._current_page == 1 and self.default_name.isChecked():
            self._needs_training = False
            self._set_page(3)
        elif self._current_page == 2:
            if not self._wake_profile:
                self.wake_training_status.setText("Grave as quatro amostras antes de continuar.")
                return
            self._set_page(3)
        elif self._current_page < 5:
            if self._current_page == 3 and not self._selected_style:
                return
            self._set_page(self._current_page + 1)
        elif self._current_page == 5:
            if not getattr(self, "_selected_voice", None):
                self.voice_status.setText("Escolha uma voz para continuar.")
                return
            self._apply()

    def back(self):
        if self._current_page > 0:
            previous = self._current_page - 1
            if previous == 2 and not self._needs_training:
                previous = 1
            self._set_page(previous)

    def _apply(self):
        voice = getattr(self, "_selected_voice", str(self.cfg.get("tts_voice", SUPPORTED_VOICES[0][0])))
        self.result_settings = {
            "user_name": " ".join(self.user_name.text().split())[:80],
            "profile_configured": True,
            "assistant_name": "Aurora" if self.default_name.isChecked() else " ".join(self.assistant_name.text().split())[:80],
            "wake_profile": self._wake_profile if self._needs_training else None,
            "bubble_style": self._selected_style,
            "tts_voice": voice or self.cfg.get("tts_voice", "pt-BR-ThalitaMultilingualNeural"),
            "feedback_theme": self._selected_feedback,
            "onboarding_pending": False,
            "onboarding_boot_id": "",
        }
        self._set_page(5)
        self._play_sfx("success")
        self._loading_pulse.start()
        self.back_button.setVisible(False)
        self.next_button.setVisible(False)
        QTimer.singleShot(1250, self.accept)

    def _play_sfx(self, name):
        effect = self._sfx.get(name)
        if effect is not None and effect.source().isValid():
            effect.stop()
            effect.play()

