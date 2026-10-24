# SPDX-License-Identifier: GPL-3.0-only
"""First-boot personalization wizard for the desktop client."""
from __future__ import annotations

import asyncio
import math
import time
from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QThread, Signal, QTimer, QUrl
from PySide6.QtGui import QColor, QPainter, QPainterPath, QRadialGradient, QLinearGradient, QPen
from PySide6.QtMultimedia import QSoundEffect
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QDialog, QFrame, QGraphicsOpacityEffect, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QRadioButton, QStackedWidget, QVBoxLayout, QWidget,
)

from ..config import VOSK_PATH
from ..voice.wake import wake_name_supported, wake_name_words


SUPPORTED_VOICES = (
    ("pt-BR-ThalitaMultilingualNeural", "Thalita", "Feminina"),
    ("pt-BR-FranciscaNeural", "Francisca", "Feminina"),
    ("pt-BR-AntonioNeural", "Antonio", "Masculina"),
)


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
        self.phase = (self.phase + 0.018) % (math.tau)
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
        self.setMinimumWidth(238)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 15, 16, 15)
        layout.setSpacing(8)
        heading = QLabel(title)
        heading.setObjectName("cardTitle")
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(heading)
        orb = _AnimatedOrb(key)
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
        layout.addWidget(voice_icon, 1)
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
    checked = Signal(str, bool, str)

    def __init__(self, name):
        super().__init__()
        self.name = name

    def run(self):
        words = wake_name_words(self.name)
        if not words:
            self.checked.emit(self.name, False, "Use um nome de até quatro palavras.")
            return
        try:
            import vosk
            model = vosk.Model(str(VOSK_PATH))
            missing = [word for word in words if not wake_name_supported(word, model)]
            if missing:
                self.checked.emit(self.name, False,
                                  "O modelo de voz não reconhece: " + ", ".join(missing) +
                                  ". Escolha outro nome ou marque “Prefiro Aurora”.")
                return
            self.checked.emit(self.name, True, "Nome compatível com o vocabulário do Vosk.")
        except Exception as exc:
            if self.isInterruptionRequested():
                return
            self.checked.emit(self.name, False,
                              f"Não consegui validar esse nome no modelo de voz ({type(exc).__name__}).")


class PersonalizationWizard(QDialog):
    """Material-inspired, animated first-login setup, returning saved choices."""
    def __init__(self, cfg, speaker, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.speaker = speaker
        self.result_settings = None
        self._voice_map = {}
        self._selected_style = str(cfg.get("bubble_style", "boreal"))
        if self._selected_style not in {"boreal", "emerald", "crimson"}:
            self._selected_style = "boreal"
        self._name_worker = None
        self._sfx = {}
        self.setWindowTitle("Personalizar a Aurora")
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        self.setModal(True)
        self.setMinimumSize(900, 650)
        self.resize(980, 700)
        self.setStyleSheet("""
            QDialog { background:#f3f2f8; color:#1b1b22; }
            QLabel#eyebrow { color:#625b70; font-size:11px; font-weight:700; letter-spacing:2px; }
            QLabel#title { color:#1c1b20; font-size:27px; font-weight:700; }
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
            QPushButton#selectStyle, QPushButton#previewVoice { background:#f0edf6; border:1px solid #e3deec; }
            QPushButton#selectStyle:hover, QPushButton#previewVoice:hover { background:#e8e2f2; }
            QCheckBox, QRadioButton { spacing:9px; color:#494451; }
            QRadioButton::indicator { width:18px; height:18px; }
        """)
        for name in ("select", "step", "success", "error"):
            effect = QSoundEffect(self)
            effect.setSource(QUrl.fromLocalFile(str(__import__("pathlib").Path(__file__).resolve().parents[2] / "assets" / "audio" / f"{name}.wav")))
            effect.setVolume(0.22 if name != "error" else 0.30)
            self._sfx[name] = effect

        root = QVBoxLayout(self)
        root.setContentsMargins(38, 30, 38, 28)
        root.setSpacing(18)
        self.eyebrow = QLabel("AURORA · PRIMEIRA CONFIGURAÇÃO")
        self.eyebrow.setObjectName("eyebrow")
        root.addWidget(self.eyebrow)
        self.stack = QStackedWidget()
        self.stack.setGraphicsEffect(QGraphicsOpacityEffect(self.stack))
        self._build_welcome()
        self._build_profile()
        self._build_bubble()
        self._build_voice()
        self._build_loading()
        root.addWidget(self.stack, 1)
        footer = QHBoxLayout()
        self.step_label = QLabel("Boas-vindas  ·  1 de 4")
        self.step_label.setStyleSheet("color:#746d7d;font-size:12px")
        footer.addWidget(self.step_label)
        footer.addStretch(1)
        self.back_button = QPushButton("Voltar")
        self.back_button.clicked.connect(self.back)
        footer.addWidget(self.back_button)
        self.next_button = QPushButton("Começar")
        self.next_button.setObjectName("primary")
        self.next_button.clicked.connect(self.next)
        footer.addWidget(self.next_button)
        root.addLayout(footer)

        self._voice_worker = _VoiceCatalog(self)
        self._voice_worker.loaded.connect(self._populate_voices)
        self._voice_worker.start()
        self._current_page = 0
        self._set_page(0, animated=False)
        self._center()

    def _panel(self, title, subtitle=""):
        frame = QFrame()
        frame.setObjectName("panel")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(12)
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
        self.user_name = QLineEdit(str(self.cfg.get("user_name", "")))
        self.user_name.setPlaceholderText("Ex.: Alex")
        self.user_name.setClearButtonEnabled(True)
        self.user_name.setMinimumHeight(48)
        layout.addWidget(QLabel("Como devo te chamar?")); layout.addWidget(self.user_name)
        self.user_name_note = QLabel("Digite como você quer ser chamada na saudação.")
        self.user_name_note.setStyleSheet("color:#746d7d;font-size:12px")
        layout.addWidget(self.user_name_note)
        layout.addSpacing(6)
        layout.addWidget(QLabel("Nome de ativação da assistente"))
        self.assistant_name = QLineEdit(str(self.cfg.get("assistant_name", "Aurora")))
        self.assistant_name.setPlaceholderText("Ex.: Aurora")
        self.assistant_name.setClearButtonEnabled(True)
        self.assistant_name.setMinimumHeight(48)
        layout.addWidget(self.assistant_name)
        self.default_name = QCheckBox("Nah, prefiro Aurora")
        self.default_name.setChecked(str(self.cfg.get("assistant_name", "Aurora")).casefold() == "aurora")
        self.default_name.toggled.connect(self.assistant_name.setHidden)
        self.assistant_name.setHidden(self.default_name.isChecked())
        layout.addWidget(self.default_name)
        self.name_note = QLabel("O nome será adicionado à gramática dinâmica do Vosk. Para funcionar bem, cada palavra precisa existir no vocabulário do modelo instalado.")
        self.name_note.setWordWrap(True)
        self.name_note.setStyleSheet("color:#746d7d;font-size:12px")
        layout.addWidget(self.name_note)
        self.stack.addWidget(frame)

    def _build_bubble(self):
        frame, layout = self._panel("Vamos personalizar sua bolha", "Veja cada acabamento em movimento e selecione o que combina com você.")
        cards = QHBoxLayout()
        cards.setSpacing(14)
        self.style_cards = {}
        choices = (("boreal", "Névoa Boreal", "O acabamento atual · azul e violeta"),
                   ("emerald", "Pulso Esmeralda", "Verde vivo · energia fresca"),
                   ("crimson", "Flare Carmesim", "Vermelho intenso · presença forte"))
        for key, title, detail in choices:
            card = _StyleCard(key, title, detail)
            card.select_button.clicked.connect(lambda _=False, value=key: self._select_style(value))
            self.style_cards[key] = card
            cards.addWidget(card, 1)
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

    def _preview_voice(self, voice):
        name = "Aurora" if self.default_name.isChecked() else (self.assistant_name.text().strip() or "Aurora")
        self.voice_status.setText(f"Reproduzindo prévia de {next((n for s, n, _ in SUPPORTED_VOICES if s == voice), voice)}…")
        self.speaker.say_with_voice(f"Olá, eu sou {name}. Estou pronta para ajudar.", voice)
        self._play_sfx("select")

    def _center(self):
        screen = self.screen() or __import__("PySide6.QtWidgets", fromlist=["QApplication"]).QApplication.primaryScreen()
        if screen:
            self.move(screen.availableGeometry().center() - self.rect().center())

    def showEvent(self, event):
        super().showEvent(event)

    def done(self, result):
        for worker in (getattr(self, "_voice_worker", None), getattr(self, "_name_worker", None)):
            if worker is not None and worker.isRunning():
                worker.requestInterruption()
                worker.wait(2500)
        super().done(result)

    def _set_page(self, page, animated=True):
        self._current_page = page
        self.stack.setCurrentIndex(page)
        self.back_button.setVisible(page > 0 and page < 4)
        labels = ("Boas-vindas · 1 de 4", "Seu perfil · 2 de 4", "Sua Bolha · 3 de 4", "Sua voz · 4 de 4", "")
        self.step_label.setText(labels[page])
        self.next_button.setVisible(page < 4)
        self.next_button.setText(("Começar", "Próximo", "Próximo", "Finalizar", "")[page])
        if animated:
            effect = self.stack.graphicsEffect()
            effect.setOpacity(0.12)
            animation = QPropertyAnimation(effect, b"opacity", self)
            animation.setDuration(320)
            animation.setStartValue(0.12)
            animation.setEndValue(1.0)
            animation.setEasingCurve(QEasingCurve.Type.OutCubic)
            self._page_animation = animation
            animation.start()
            self._play_sfx("step")

    def _set_name_checked(self, name, ok, message):
        self.next_button.setEnabled(True)
        self.name_note.setText(message)
        if ok and name == self.assistant_name.text().strip():
            self._set_page(2)

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
        if self._current_page < 3:
            self._set_page(self._current_page + 1)
        elif self._current_page == 3:
            self._apply()

    def back(self):
        if self._current_page > 0:
            self._set_page(self._current_page - 1)

    def _apply(self):
        voice = getattr(self, "_selected_voice", str(self.cfg.get("tts_voice", SUPPORTED_VOICES[0][0])))
        self.result_settings = {
            "user_name": " ".join(self.user_name.text().split())[:80],
            "profile_configured": True,
            "assistant_name": "Aurora" if self.default_name.isChecked() else " ".join(self.assistant_name.text().split())[:80],
            "bubble_style": self._selected_style,
            "tts_voice": voice or self.cfg.get("tts_voice", "pt-BR-ThalitaMultilingualNeural"),
            "onboarding_pending": False,
            "onboarding_boot_id": "",
        }
        self._set_page(4)
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

