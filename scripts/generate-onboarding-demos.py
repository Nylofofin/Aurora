#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Generate official skin artwork and motion demos from the real onboarding widgets."""
from __future__ import annotations

import math
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PIL import Image, ImageDraw, ImageFont  # noqa: E402
from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtGui import QColor, QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from aurora_core.ui.onboarding import (  # noqa: E402
    BUBBLE_STYLES,
    FEEDBACK_THEMES,
    PersonalizationWizard,
    _AnimatedOrb,
)
from aurora_core.voice.catalog import VOICES  # noqa: E402

MEDIA = ROOT / "docs" / "media"
FRAME_MS = 60


def capture(widget: PersonalizationWizard, fixed_height: int | None = None) -> Image.Image:
    size = widget.size()
    image = QImage(size.width(), fixed_height or size.height(), QImage.Format.Format_RGBA8888)
    image.fill(QColor("#111117"))
    painter = QPainter(image)
    widget.render(painter, QPoint())
    painter.end()
    ptr = image.bits()
    return Image.frombytes("RGBA", (image.width(), image.height()), bytes(ptr)).convert("RGB")


def animate_for(app: QApplication, widget: PersonalizationWizard, duration_ms: int,
                frames: list[Image.Image], *, hold_ms: int = 0,
                fixed_height: int | None = None) -> None:
    started = time.monotonic()
    while (time.monotonic() - started) * 1000 < duration_ms:
        app.processEvents()
        frames.append(capture(widget, fixed_height))
        time.sleep(FRAME_MS / 1000)
    app.processEvents()
    if hold_ms:
        frame = capture(widget, fixed_height)
        frames.extend([frame.copy()] * max(1, hold_ms // FRAME_MS))


def save_gif(frames: list[Image.Image], path: Path) -> None:
    if not frames:
        raise RuntimeError(f"No frames captured for {path.name}")
    palette_frames = [frame.quantize(colors=160, method=Image.Quantize.FASTOCTREE)
                      for frame in frames]
    palette_frames[0].save(
        path,
        save_all=True,
        append_images=palette_frames[1:],
        duration=FRAME_MS,
        loop=0,
        optimize=True,
        disposal=2,
    )
    print(f"{path.relative_to(ROOT)}: {len(frames)} frames, {path.stat().st_size // 1024} KiB")


def capture_orb(orb: _AnimatedOrb) -> Image.Image:
    size = orb.size()
    image = QImage(size.width(), size.height(), QImage.Format.Format_RGBA8888)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    orb.render(painter, QPoint())
    painter.end()
    return Image.frombytes("RGBA", (image.width(), image.height()), bytes(image.bits()))


def save_animated_webp(frames: list[Image.Image], path: Path, frame_ms: int) -> None:
    if not frames:
        raise RuntimeError(f"No frames captured for {path.name}")
    frames[0].save(path, format="WEBP", save_all=True, append_images=frames[1:],
                    duration=frame_ms, loop=0, quality=90, method=0)
    print(f"{path.relative_to(ROOT)}: {len(frames)} official frames, {path.stat().st_size // 1024} KiB")


def make_skin_assets(app: QApplication) -> None:
    """Export stills and looping motion from the exact onboarding orb painter."""
    skin_dir = MEDIA / "skins"
    skin_dir.mkdir(parents=True, exist_ok=True)
    for index, (key, title, _detail) in enumerate(BUBBLE_STYLES):
        orb = _AnimatedOrb(key)
        orb.setFixedSize(288, 288)
        orb.phase = index * .73
        orb.show()
        app.processEvents()
        image = QImage(288, 288, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        orb.render(painter, QPoint())
        painter.end()
        destination = skin_dir / f"{key}.png"
        image.save(str(destination), "PNG")
        # Each site loop follows the actual detail cycle: drifting veils and
        # surface details complete one cycle; the two orbital skins use their
        # true revolution time so the satellite returns seamlessly.
        cycle_seconds = 2 * math.pi / (.42 * 2 * math.pi / 5) if key == "amethyst" else (
            2 * math.pi / (.62 * 2 * math.pi / 5) if key == "titan" else 2 * math.pi / (.48 * 2 * math.pi / 5)
        )
        frame_ms = 83
        frame_count = round(cycle_seconds * 1000 / frame_ms)
        frames = []
        for frame_index in range(frame_count):
            orb.phase = 2 * math.pi * (frame_index * frame_ms / 1000) / 5
            frames.append(capture_orb(orb))
        save_animated_webp(frames, skin_dir / f"{key}.webp", frame_ms)
        orb.close()
        orb.deleteLater()
        print(f"{destination.relative_to(ROOT)}: official {title} orb")


def make_skin_contact_sheet(app: QApplication) -> None:
    width, height, margin, gap = 980, 864, 24, 14
    cell_w = (width - 2 * margin - 2 * gap) // 3
    cell_h = 246
    image = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QColor("#111117"))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QColor("#f4f0fa"))
    painter.setFont(QFontSafe(25, True))
    painter.drawText(margin, 39, f"{len(BUBBLE_STYLES)} acabamentos · uma bolha, identidades próprias")
    painter.setFont(QFontSafe(12))
    painter.setPen(QColor("#b5afbd"))
    painter.drawText(margin, 62, "Prévias renderizadas pelos mesmos componentes usados no onboarding da Aurora.")

    for index, (key, title, detail) in enumerate(BUBBLE_STYLES):
        row, col = divmod(index, 3)
        row_start = row * 3
        row_count = min(3, len(BUBBLE_STYLES) - row_start)
        row_offset = ((3 - row_count) * (cell_w + gap)) // 2 if row_count < 3 else 0
        x, y = margin + row_offset + col * (cell_w + gap), 82 + row * (cell_h + gap)
        painter.setPen(QColor("#393441"))
        painter.setBrush(QColor("#1b1a22"))
        painter.drawRoundedRect(x, y, cell_w, cell_h, 18, 18)
        orb = _AnimatedOrb(key)
        orb.setFixedSize(166, 166)
        orb.move(-400, -400)
        orb.show()
        app.processEvents()
        orb.phase = index * .47
        orb.render(painter, QPoint(x + (cell_w - 166) // 2, y + 5))
        painter.setPen(QColor("#f4f0fa"))
        painter.setFont(QFontSafe(15, True))
        painter.drawText(x + 14, y + 184, cell_w - 28, 24,
                         int(Qt.AlignmentFlag.AlignHCenter), title)
        painter.setPen(QColor("#b5afbd"))
        painter.setFont(QFontSafe(10))
        painter.drawText(x + 14, y + 204, cell_w - 28, 38,
                         int(Qt.AlignmentFlag.AlignHCenter | Qt.TextFlag.TextWordWrap), detail)
        orb.close()
        orb.deleteLater()
    painter.end()
    image.save(str(MEDIA / "bubble-skins.png"), "PNG")
    print(f"docs/media/bubble-skins.png: {width}x{height}")


def QFontSafe(size: int, bold: bool = False):
    from PySide6.QtGui import QFont
    font = QFont("Noto Sans", size)
    font.setBold(bold)
    return font


def make_wizard() -> tuple[QApplication, PersonalizationWizard]:
    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    wizard = PersonalizationWizard({"bubble_style": "boreal", "assistant_name": "Aurora",
                                    "tts_voice": VOICES[0].key,
                                    "feedback_theme": FEEDBACK_THEMES[0][0]}, None)
    wizard.resize(900, 640)
    wizard._needs_training = True
    wizard.show()
    app.processEvents()
    wizard._fit_current_page()
    app.processEvents()
    return app, wizard


def make_carousel_demo(app: QApplication, wizard: PersonalizationWizard) -> None:
    wizard._set_page(3, animated=False)
    app.processEvents()
    frames: list[Image.Image] = []
    frames.extend([capture(wizard).copy()] * 7)
    for _ in range(len(BUBBLE_STYLES)):
        wizard._step_style(1)
        animate_for(app, wizard, 420, frames, hold_ms=240)
    save_gif(frames, MEDIA / "onboarding-skins.gif")


def make_transition_demo(app: QApplication, wizard: PersonalizationWizard) -> None:
    frames: list[Image.Image] = []
    wizard._set_page(0, animated=False)
    app.processEvents()
    frames.extend([capture(wizard, 648).copy()] * 8)
    for page in (1, 2, 3, 4, 5, 0):
        wizard._set_page(page, animated=True)
        animate_for(app, wizard, 420, frames, hold_ms=300, fixed_height=648)
    save_gif(frames, MEDIA / "onboarding-transitions.gif")


def make_studio_personalization_demo(app: QApplication, wizard: PersonalizationWizard) -> None:
    """Capture a longer, continuous tour of the complete local profile setup."""
    frames: list[Image.Image] = []

    def hold(page: int, milliseconds: int, *, transition: bool = True) -> None:
        wizard._set_page(page, animated=transition)
        animate_for(app, wizard, 420 if transition else 1,
                    frames, hold_ms=milliseconds, fixed_height=648)

    wizard.resize(900, 640)
    wizard._needs_training = True
    wizard.user_name.setText("Nylo")
    wizard.assistant_name.setText("Luna")
    wizard.default_name.setChecked(False)
    wizard.personality_choice.setCurrentIndex(wizard.personality_choice.findData("playful"))
    wizard.detail_choice.setCurrentIndex(wizard.detail_choice.findData("balanced"))
    wizard.tone_slider.setValue(76)
    wizard.custom_instructions.setText("Seja calorosa, direta e use exemplos quando ajudarem.")

    hold(0, 780, transition=False)
    hold(1, 900)
    wizard.wake_training_status.setText("Perfil local criado · 4 de 4 amostras válidas")
    wizard.wake_training_button.setText("Amostras concluídas ✓")
    hold(2, 820)
    hold(3, 450)
    wizard._step_style(1)
    animate_for(app, wizard, 420, frames, hold_ms=240, fixed_height=648)
    wizard._step_style(1)
    animate_for(app, wizard, 420, frames, hold_ms=420, fixed_height=648)
    hold(4, 600)
    wizard._step_voice(1)
    animate_for(app, wizard, 420, frames, hold_ms=380, fixed_height=648)
    hold(5, 500)
    wizard._step_feedback(1)
    animate_for(app, wizard, 420, frames, hold_ms=380, fixed_height=648)
    wizard._loading_pulse.start()
    hold(6, 1450)
    wizard._loading_pulse.stop()
    save_gif(frames, MEDIA / "studio-personalization.gif")


def main() -> int:
    MEDIA.mkdir(parents=True, exist_ok=True)
    app, wizard = make_wizard()
    if "--studio-only" in sys.argv:
        make_studio_personalization_demo(app, wizard)
        wizard.close()
        app.processEvents()
        return 0
    make_skin_assets(app)
    make_skin_contact_sheet(app)
    make_carousel_demo(app, wizard)
    make_transition_demo(app, wizard)
    make_studio_personalization_demo(app, wizard)
    wizard.close()
    app.processEvents()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
