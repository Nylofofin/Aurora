# SPDX-License-Identifier: GPL-3.0-only
"""First-boot personalization wizard for the desktop client."""
from __future__ import annotations

import asyncio
import time
from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QThread, Signal, QTimer
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QDialog, QFrame, QGraphicsOpacityEffect, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QStackedWidget, QVBoxLayout, QWidget,
)

from ..config import VOSK_PATH
from ..voice.wake import wake_name_supported, wake_name_words


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
        self._name_worker = None
        self.setWindowTitle("Personalizar a Aurora")
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        self.setModal(True)
        self.setMinimumSize(600, 510)
        self.setStyleSheet("""
            QDialog { background:#f6f5fb; color:#201d28; }
            QLabel#eyebrow { color:#655a78; font-size:11px; font-weight:700; letter-spacing:2px; }
            QLabel#title { color:#201d28; font-size:27px; font-weight:700; }
            QLabel#subtitle { color:#625d6c; font-size:14px; }
            QFrame#hero, QFrame#panel { background:#ffffff; border:1px solid #e8e4ef; border-radius:22px; }
            QLineEdit, QComboBox { background:#fff; border:1px solid #d8d2e2; border-radius:12px; padding:12px; color:#25212c; }
            QLineEdit:focus, QComboBox:focus { border:2px solid #7554ad; }
            QPushButton { background:#ede9f4; color:#332c3d; border:0; border-radius:14px; padding:12px 18px; font-weight:600; }
            QPushButton:hover { background:#e3dced; }
            QPushButton#primary { background:#6750a4; color:#fff; }
            QPushButton#primary:hover { background:#7962b4; }
            QPushButton#style { text-align:left; min-height:94px; border:1px solid #e1dce9; background:#fff; }
            QPushButton#style:checked { border:2px solid #6750a4; background:#f0ecf7; }
            QCheckBox { spacing:9px; color:#494451; }
            QComboBox QAbstractItemView { background:#fff; selection-background-color:#e8e0f2; }
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(30, 26, 30, 24)
        root.setSpacing(16)
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
        self.step_label = QLabel("Boas-vindas · 1 de 4")
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
        self.adjustSize()
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
        glow = QLabel("✦")
        glow.setAlignment(Qt.AlignmentFlag.AlignCenter)
        glow.setStyleSheet("font-size:72px;color:#8f79c7;background:qradialgradient(cx:.5,cy:.5,radius:.5,stop:0 #ebe5f8,stop:1 #ffffff);border-radius:80px")
        glow.setFixedSize(150, 150)
        glow.setGraphicsEffect(QGraphicsOpacityEffect(glow))
        layout.addWidget(glow, 0, Qt.AlignmentFlag.AlignHCenter)
        self._welcome_pulse = QPropertyAnimation(glow.graphicsEffect(), b"opacity", self)
        self._welcome_pulse.setDuration(1900)
        self._welcome_pulse.setStartValue(0.62)
        self._welcome_pulse.setEndValue(1.0)
        self._welcome_pulse.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._welcome_pulse.setLoopCount(-1)
        note = QLabel("Uma bolha, uma voz e um nome que combinam com você.")
        note.setObjectName("subtitle")
        note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(note)
        self.stack.addWidget(frame)

    def _build_profile(self):
        frame, layout = self._panel("Quem está por aqui?", "A Aurora usará esse nome nas saudações, em vez do nome da conta do desktop.")
        self.user_name = QLineEdit(str(self.cfg.get("user_name", "")))
        self.user_name.setPlaceholderText("Como devo te chamar?")
        layout.addWidget(QLabel("Seu nome")); layout.addWidget(self.user_name)
        self.user_name_note = QLabel("Digite como você quer ser chamada na saudação.")
        self.user_name_note.setStyleSheet("color:#746d7d;font-size:12px")
        layout.addWidget(self.user_name_note)
        layout.addSpacing(6)
        layout.addWidget(QLabel("Nome da assistente"))
        self.assistant_name = QLineEdit(str(self.cfg.get("assistant_name", "Aurora")))
        self.assistant_name.setPlaceholderText("Escolha um nome pronunciável")
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
        frame, layout = self._panel("Vamos personalizar sua Bolha!", "Três acabamentos para a mesma bolha animada. Mais estilos poderão chegar depois.")
        cards = QHBoxLayout()
        self.style_group = QButtonGroup(self)
        self.style_buttons = {}
        choices = (("boreal", "✦\nNévoa Boreal\nAzul e violeta", "#8bc8e8"),
                   ("prisma", "✧\nPrisma\nLuz perolada", "#cbeef7"),
                   ("violeta", "◉\nÓrbita Violeta\nVioleta profundo", "#a98adf"))
        for key, label, color in choices:
            button = QPushButton(label)
            button.setObjectName("style")
            button.setCheckable(True)
            button.setMinimumHeight(112)
            button.setStyleSheet(f"QPushButton#style {{ color:{color}; font-size:15px; }}")
            button.clicked.connect(lambda _checked=False, value=key: setattr(self, "_selected_style", value))
            self.style_group.addButton(button)
            self.style_buttons[key] = button
            cards.addWidget(button)
        self.style_buttons.get(self._selected_style, self.style_buttons["boreal"]).setChecked(True)
        layout.addLayout(cards)
        self.stack.addWidget(frame)

    def _build_voice(self):
        frame, layout = self._panel("Escolha a voz que mais gostar", "As vozes são carregadas da lista atual do Edge TTS. A síntese usa a internet, conforme explicado no README.")
        self.voice_combo = QComboBox()
        self.voice_combo.setEditable(True)
        self.voice_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.voice_combo.setPlaceholderText("Carregando vozes disponíveis…")
        layout.addWidget(self.voice_combo)
        row = QHBoxLayout()
        self.preview_button = QPushButton("▶  Ouvir prévia")
        self.preview_button.clicked.connect(self.preview_voice)
        row.addWidget(self.preview_button)
        soon = QLabel("Em breve, mais vozes")
        soon.setStyleSheet("color:#746d7d")
        row.addWidget(soon, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addStretch(1)
        layout.addLayout(row)
        self.voice_status = QLabel("Buscando vozes…")
        self.voice_status.setStyleSheet("color:#746d7d;font-size:12px")
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
        current = str(self.cfg.get("tts_voice", "pt-BR-ThalitaMultilingualNeural"))
        values = []
        for voice in voices:
            short = str(voice.get("ShortName", ""))
            if not short:
                continue
            locale = str(voice.get("Locale", ""))
            friendly = str(voice.get("FriendlyName", short))
            gender = str(voice.get("Gender", ""))
            label = f"{locale} · {friendly} · {gender}".strip(" ·")
            values.append((label, short))
        values.sort(key=lambda item: (not item[1].lower().startswith("pt-br-"), item[0].casefold()))
        self.voice_combo.clear()
        for label, short in values:
            self.voice_combo.addItem(label, short)
            self._voice_map[short] = label
        index = self.voice_combo.findData(current)
        if index < 0 and self.voice_combo.count():
            index = 0
        if index >= 0:
            self.voice_combo.setCurrentIndex(index)
        self.voice_status.setText(f"{len(values)} vozes disponíveis." if values else "Não foi possível carregar a lista agora; sua voz atual será mantida.")

    def _center(self):
        screen = self.screen() or __import__("PySide6.QtWidgets", fromlist=["QApplication"]).QApplication.primaryScreen()
        if screen:
            self.move(screen.availableGeometry().center() - self.rect().center())

    def showEvent(self, event):
        super().showEvent(event)
        if self._current_page == 0:
            self._welcome_pulse.start()

    def done(self, result):
        for worker in (getattr(self, "_voice_worker", None), getattr(self, "_name_worker", None)):
            if worker is not None and worker.isRunning():
                worker.requestInterruption()
                worker.wait(2500)
        super().done(result)

    def _set_page(self, page, animated=True):
        self._current_page = page
        if page == 0 and self.isVisible():
            self._welcome_pulse.start()
        else:
            self._welcome_pulse.stop()
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

    def preview_voice(self):
        voice = self.voice_combo.currentData()
        if not voice:
            self.voice_status.setText("A lista de vozes ainda não está disponível.")
            return
        name = "Aurora" if self.default_name.isChecked() else (self.assistant_name.text().strip() or "Aurora")
        self.speaker.say_with_voice(f"Olá, eu sou {name}. Estou pronta para ajudar.", voice)

    def _apply(self):
        voice = self.voice_combo.currentData()
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
        self._loading_pulse.start()
        self.back_button.setVisible(False)
        self.next_button.setVisible(False)
        QTimer.singleShot(1250, self.accept)

