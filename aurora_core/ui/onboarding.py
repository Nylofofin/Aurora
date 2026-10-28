# SPDX-License-Identifier: GPL-3.0-only
"""First-boot personalization wizard for the desktop client."""
from __future__ import annotations

import math
from PySide6.QtCore import (QAbstractAnimation, QElapsedTimer, QEasingCurve, QParallelAnimationGroup, QPropertyAnimation,
                            QVariantAnimation,
                            QPoint, QPointF, QRectF, Property, Qt, QThread, Signal, QTimer, QUrl)
from PySide6.QtGui import QColor, QPainter, QPainterPath, QRadialGradient, QLinearGradient, QPen
from PySide6.QtMultimedia import QSoundEffect
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFrame, QGraphicsOpacityEffect, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QSlider, QStackedWidget, QVBoxLayout, QWidget, QProgressBar,
)

from ..config import VOSK_PATH
from ..voice.wake import wake_name_supported, wake_name_words
from ..voice.profile import enroll as enroll_wake_profile, validate_recording
from ..voice.catalog import VOICES, voice_available, voice_runtime_available, ensure_voice


# Public appearance catalog shared by onboarding and the live orb.  Keep the
# keys stable so a saved preference survives upgrades.
BUBBLE_STYLES = (
    ("boreal", "Cortina Boreal", "Véus turquesa · filamentos violetas · pontos de luz"),
    ("emerald", "Gelo Fraturado", "Placas esmeralda · veios ramificados · brilho móvel"),
    ("crimson", "Tempestade Âmbar", "Bandas jovianas · filamentos de nuvem · olho ciclônico"),
    ("amethyst", "Órbita Índigo", "Anel duplo inclinado · satélite em percurso contínuo"),
    ("solaris", "Eclipse Rosé", "Corona luminosa · sombra móvel · arco de refração"),
    ("ocean", "Falha Prismática", "Placas ciano · fratura ramificada · faces de gelo"),
    ("titan", "Névoa Violeta", "Véus lilás · profundidade escura · luz difusa"),
    ("triton", "Calota Glacial", "Gelo azul profundo · pluma polar · estrias gravadas"),
    ("quasar", "Pulso de Quasar", "Núcleo elétrico · jatos opostos · halo violeta"),
    ("lunar", "Mar de Prata", "Relevo craterado · terminador móvel · poeira luminosa"),
)
BUBBLE_STYLE_KEYS = {key for key, _title, _detail in BUBBLE_STYLES}

# Shared catalog for the onboarding carousel and playback validation. Keep
# stable keys so the user's selected sound signature survives updates.
FEEDBACK_THEMES = (
    ("boreal", "Boreal", "Cristal aéreo", "∿   ✧   ∿"),
    ("pulse", "Pulse", "Batida eletrônica", "▂   ▅   ▇"),
    ("void", "Void", "Grave espacial", "◌   ·   ◌"),
    ("prisma", "Prisma", "Sinos de vidro", "✧   ◇   ✧"),
    ("marea", "Maré", "Gotas líquidas", "◦   〜   ◦"),
    ("lumen", "Lúmen", "Farol harmônico", "◖   ●   ◗"),
    ("aether", "Éter", "Sopro etéreo", "≈   ✦   ≈"),
    ("quasar", "Quasar", "Pulso estelar", "✦   ⇧   ✦"),
    ("ember", "Brasa", "Metal incandescente", "◈   ·   ◈"),
)
FEEDBACK_THEME_KEYS = {item[0] for item in FEEDBACK_THEMES}


class _OrbCarouselStage(QWidget):
    resized = Signal()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.resized.emit()


class _AnimatedOrb(QWidget):
    """Small, continuously animated preview of the selected orb finish."""
    def __init__(self, style="boreal", parent=None, opacity=1.0):
        super().__init__(parent)
        self.style = style
        self._display_opacity = float(opacity)
        self._display_scale = 1.0
        self._motion_blur = 0.0
        self._motion_direction = 0
        self.phase = 0.0
        self._elapsed = QElapsedTimer()
        self._elapsed.start()
        self._style_progress = 1.0
        self._from_colors = self._colors_for(style)
        self._to_colors = self._from_colors
        self._current_colors = self._from_colors
        self._style_transition = QVariantAnimation(self)
        self._style_transition.setDuration(420)
        self._style_transition.setStartValue(0.0)
        self._style_transition.setEndValue(1.0)
        self._style_transition.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._style_transition.valueChanged.connect(self._set_style_progress)
        self.setFixedSize(126, 126)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._timer = QTimer(self)
        # 33ms (30 FPS) for side preview orbs cuts idle rendering load in half,
        # while keeping full 60 FPS (16ms) for the prominent center orb.
        self._timer.setInterval(16 if opacity >= 0.9 else 33)
        self._timer.timeout.connect(self._tick)

    def _get_display_scale(self):
        return self._display_scale

    def _set_display_scale(self, value):
        self._display_scale = max(0.0, float(value))
        self.update()

    displayScale = Property(float, _get_display_scale, _set_display_scale)

    def _get_display_opacity(self):
        return self._display_opacity

    def _set_display_opacity(self, value):
        self._display_opacity = max(0.0, min(1.0, float(value)))
        self.update()

    displayOpacity = Property(float, _get_display_opacity, _set_display_opacity)

    def _get_motion_blur(self):
        return self._motion_blur

    def _set_motion_blur(self, value):
        self._motion_blur = max(0.0, min(1.0, float(value)))
        self.update()

    motionBlur = Property(float, _get_motion_blur, _set_motion_blur)

    def _tick(self):
        # The reference preview breathes on a five-second CSS animation. Keep
        # the same period and drive the whole orb as one rigid surface: moving
        # reflections inside the orb were an extra effect absent from the CSS.
        self.phase = self._elapsed.nsecsElapsed() * (2.0 * math.pi / 5.0e9)
        self.update()

    def showEvent(self, event):
        super().showEvent(event)
        self._timer.start()

    def hideEvent(self, event):
        self._timer.stop()
        super().hideEvent(event)

    def set_style(self, style):
        if style == self.style:
            return
        if self._style_transition.state() == QAbstractAnimation.State.Running:
            self._current_colors = self._blend_colors(
                self._from_colors, self._to_colors, self._style_progress)
            self._style_transition.stop()
        else:
            self._current_colors = self._colors_for(self.style)
        self._from_colors = self._current_colors
        self._to_colors = self._colors_for(style)
        self._style_progress = 0.0
        self.style = style
        self._style_transition.start()
        self.update()

    @staticmethod
    def _colors_for(style):
        # Each finish gets a deliberately separated palette so adjacent
        # carousel choices remain easy to distinguish at a glance.
        palette = {
            "boreal": ("#effaff", "#6ca9ec", "#6961c7"),
            "emerald": ("#edfff7", "#70d2ae", "#247d70"),
            "crimson": ("#fff4df", "#dfa45f", "#92513f"),
            "amethyst": ("#f4f2ff", "#9caee7", "#47598f"),
            "solaris": ("#fff0f0", "#d77f98", "#552f62"),
            "ocean": ("#eaffff", "#58cfc6", "#1d678e"),
            "titan": ("#f4efff", "#76658f", "#30233f"),
            "triton": ("#eaf0ff", "#3c65b0", "#101d4b"),
            "quasar": ("#f8f3ff", "#a27bea", "#321451"),
            "lunar": ("#f8f7f2", "#9a9ca8", "#333846"),
        }
        return tuple(QColor(color) for color in palette.get(style, palette["boreal"]))

    @staticmethod
    def _blend_colors(start, end, amount):
        return tuple(QColor(
            round(a.red() + (b.red() - a.red()) * amount),
            round(a.green() + (b.green() - a.green()) * amount),
            round(a.blue() + (b.blue() - a.blue()) * amount),
            round(a.alpha() + (b.alpha() - a.alpha()) * amount),
        ) for a, b in zip(start, end))

    def _set_style_progress(self, value):
        self._style_progress = float(value)
        self._current_colors = self._blend_colors(
            self._from_colors, self._to_colors, self._style_progress)
        self.update()

    def paintEvent(self, _event):
        # Leave room for Gelo Fraturado's fixed 8° tilt and the subtle scale-up.
        size = min(self.width(), self.height()) - 26
        rect_x = (self.width() - size) / 2
        rect_y = (self.height() - size) / 2
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setOpacity(self._display_opacity)
        base, lower, violet = self._current_colors
        accent = math.sin(math.pi * self._style_progress) * .014
        breath = (1.0 - math.cos(self.phase)) * .5
        lift = -3.0 * breath
        scale = 1.0 + .012 * breath + accent
        painter.translate(self.width() / 2, self.height() / 2)
        if self.style == "emerald":
            # Gelo Fraturado keeps its fixed eight-degree tilt. Other finishes
            # do not inherit a generic wobble or synthetic distortion.
            painter.rotate(-8.0)
        painter.scale(self._display_scale * scale, self._display_scale * scale)
        painter.translate(-self.width() / 2, -self.height() / 2)
        painter.translate(rect_x, rect_y + lift)
        circle = self._silhouette(0, 0, size)
        # A pair of faint afterimages gives the slide a soft, visible motion
        # blur without a GPU effect or blurring the orb while it is at rest.
        if self._motion_blur > .01:
            for index, alpha in ((1, 28), (2, 13)):
                painter.save()
                painter.setOpacity(self._display_opacity * self._motion_blur * alpha / 255)
                painter.translate(-self._motion_direction * index * 3.0, 0)
                ghost = self._silhouette(0, 0, size)
                painter.fillPath(ghost, lower)
                painter.restore()
        halo = QRadialGradient(size*.50, size*.53, size*.72)
        halo.setColorAt(0.0, QColor(lower.red(), lower.green(), lower.blue(), 8))
        halo.setColorAt(.72, QColor(lower.red(), lower.green(), lower.blue(), 2))
        halo.setColorAt(1.0, QColor(lower.red(), lower.green(), lower.blue(), 0))
        painter.setPen(Qt.PenStyle.NoPen); painter.setBrush(halo)
        painter.drawEllipse(QRectF(-size*.08, -size*.06, size*1.16, size*1.16))
        painter.setClipPath(circle)
        # CSS positive diagonal gradients run from upper-left to lower-right.
        gradient = QLinearGradient(0, 0, size*.72, size)
        if self.style == "emerald":
            gradient.setColorAt(0.0, QColor("#edfff7"))
            gradient.setColorAt(.55, QColor("#70d2ae"))
            gradient.setColorAt(1.0, QColor("#247d70"))
        elif self.style == "crimson":
            # Júpiter uses the same layered cloud bands as the approved CSS.
            gradient = QLinearGradient(0, 0, size*.05, size)
            for stop, color in ((0.0, "#fff4df"), (.18, "#fff4df"),
                                (.19, "#edc887"), (.28, "#edc887"),
                                (.29, "#f2d398"), (.42, "#f2d398"),
                                (.43, "#d78f57"), (.53, "#d78f57"),
                                (.54, "#edc47e"), (.67, "#edc47e"),
                                (.68, "#b9654b"), (.76, "#b9654b"),
                                (.77, "#dfa45f"), (1.0, "#dfa45f")):
                gradient.setColorAt(stop, QColor(color))
        elif self.style == "amethyst":
            gradient = QLinearGradient(0, 0, size*.28, size)
            for stop, color in ((0.0, "#f4f2ff"), (.28, "#f4f2ff"),
                                (.29, "#d0d5f4"), (.39, "#d0d5f4"),
                                (.40, "#9caee7"), (.51, "#9caee7"),
                                (.52, "#8799d5"), (.60, "#8799d5"),
                                (.61, "#47598f"), (1.0, "#47598f")):
                gradient.setColorAt(stop, QColor(color))
        elif self.style == "solaris":
            gradient = QLinearGradient(0, 0, size*.58, size)
            for stop, color in ((0.0, "#fff0f0"), (.41, "#edb0bd"),
                                (.72, "#bd7697"), (1.0, "#552f62")):
                gradient.setColorAt(stop, QColor(color))
        elif self.style == "ocean":
            gradient = QLinearGradient(0, 0, size*.58, size)
            for stop, color in ((0.0, "#eaffff"), (.35, "#b3f0e4"),
                                (.60, "#58cfc6"), (1.0, "#1d678e")):
                gradient.setColorAt(stop, QColor(color))
        elif self.style == "titan":
            gradient = QLinearGradient(size*.16, 0, size*.78, size)
            for stop, color in ((0.0, "#f4efff"), (.22, "#c7b9e4"),
                                (.48, "#76658f"), (.74, "#504062"), (1.0, "#30233f")):
                gradient.setColorAt(stop, QColor(color))
        elif self.style == "triton":
            gradient = QLinearGradient(0, size*.08, size, size*.96)
            for stop, color in ((0.0, "#eaf0ff"), (.25, "#a6b9ee"),
                                (.50, "#3c65b0"), (.76, "#243e82"), (1.0, "#101d4b")):
                gradient.setColorAt(stop, QColor(color))
        elif self.style == "quasar":
            gradient = QLinearGradient(size*.12, 0, size*.83, size)
            for stop, color in ((0.0, "#f8f3ff"), (.26, "#d6c0ff"), (.48, "#a27bea"), (.74, "#59318a"), (1.0, "#321451")):
                gradient.setColorAt(stop, QColor(color))
        elif self.style == "lunar":
            gradient = QLinearGradient(size*.12, size*.08, size*.84, size*.95)
            for stop, color in ((0.0, "#f8f7f2"), (.28, "#d2d2d0"), (.53, "#9a9ca8"), (.78, "#555b6b"), (1.0, "#333846")):
                gradient.setColorAt(stop, QColor(color))
        else:
            gradient.setColorAt(0, QColor("#effaff"))
            gradient.setColorAt(.58, QColor("#6ca9ec"))
            gradient.setColorAt(1, QColor("#6961c7"))
        painter.fillPath(circle, gradient)

        # These static overlays follow the prototype's CSS radial gradients.
        radial_fields = {
            "boreal": ((.35, .72), "#91eeeb", 132, .84),
            "emerald": ((.72, .72), "#d6fff0", 90, .72),
            "amethyst": ((.27, .24), "#ffffff", 88, .66),
            "solaris": ((.76, .68), "#3e264f", 110, .74),
            "ocean": ((.70, .76), "#154d80", 138, .74),
            "crimson": ((.32, .20), "#ffffff", 78, .62),
            "titan": ((.72, .72), "#c7a6f5", 104, .82),
            "triton": ((.30, .74), "#d8ffff", 118, .82),
            "quasar": ((.50, .48), "#e4c7ff", 128, .60),
            "lunar": ((.28, .28), "#ffffff", 105, .70),
        }
        if self.style in radial_fields:
            (cx, cy), color, alpha, radius = radial_fields[self.style]
            tint = QColor(color); tint.setAlpha(alpha)
            field = QRadialGradient(size*cx, size*cy, size*radius)
            field.setColorAt(0, tint)
            field.setColorAt(1, QColor(tint.red(), tint.green(), tint.blue(), 0))
            painter.fillPath(circle, field)

        self._paint_style_detail(painter, size, lower, violet)

        # CSS's fixed radial highlight and blurred top sheen. Two faint soft
        # ellipses approximate the 6px CSS blur without adding a new motion.
        # A very slow, narrow refraction pass adds movement to every finish
        # without making the glass look like a looping sticker.
        shine_x = size*(.32 + math.sin(self.phase*.28)*.035)
        shine_y = size*(.19 + math.cos(self.phase*.23)*.018)
        shine = QRadialGradient(shine_x, shine_y, size*.42)
        shine.setColorAt(0, QColor(255, 255, 255, 250))
        shine.setColorAt(.15, QColor(255, 255, 255, 168))
        shine.setColorAt(1, QColor(255, 255, 255, 0))
        painter.fillPath(circle, shine)
        sheen = QLinearGradient(size*(.46 + math.sin(self.phase*.22)*.02), size*.09,
                                size*(.54 + math.sin(self.phase*.22)*.02), size*.42)
        sheen.setColorAt(0, QColor(255, 255, 255, 52))
        sheen.setColorAt(.65, QColor(255, 255, 255, 12))
        sheen.setColorAt(1, QColor(255, 255, 255, 0))
        painter.fillPath(circle, sheen)
        painter.setClipping(False)
        painter.setPen(QPen(QColor(255, 255, 255, 90), max(1.0, size/148)))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(circle)
        painter.end()

    def _silhouette(self, x, y, size):
        path = QPainterPath()
        rect = QRectF(x + 2, y + 2, size - 4, size - 4)
        path.addEllipse(rect)
        return path

    def _paint_style_detail(self, painter, size, lower, violet):
        """Draw a distinct, animated surface signature for each glass finish."""
        painter.save()
        orbit = self.phase * .42
        detail_phase = orbit if self.style == "amethyst" else self.phase * .48
        flow = (math.sin(detail_phase) + 1.0) * .5
        pulse = (math.sin(detail_phase + .8) + 1.0) * .5

        def stroke(path, color, width):
            painter.setPen(QPen(color, max(1.0, size * width), Qt.PenStyle.SolidLine,
                                Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)

        def glint(x, y, radius, alpha=190, color=(255, 255, 255)):
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(*color, int(alpha)))
            painter.drawEllipse(QRectF(x-radius, y-radius, radius*2, radius*2))
            painter.setPen(QPen(QColor(*color, int(alpha*.65)), max(1.0, size*.004)))
            painter.drawLine(QPointF(x-radius*1.8, y), QPointF(x+radius*1.8, y))
            painter.drawLine(QPointF(x, y-radius*1.8), QPointF(x, y+radius*1.8))

        if self.style == "boreal":
            # Layered aurora curtains: broad color bands, fine streamers and
            # tiny stars make this read as atmospheric light rather than waves.
            for index, (color, offset, width) in enumerate((
                (QColor(76, 245, 229, 105), flow, .046),
                (QColor(135, 235, 226, 154), 1.0-flow, .021),
                (QColor(201, 177, 255, 119), flow, .012),
            )):
                veil = QPainterPath()
                y = size*(.38 + index*.115)
                sway = (offset-.5)*size*.12
                veil.moveTo(size*.03, y + size*.10)
                veil.cubicTo(size*(.22)+sway, y-size*.18,
                             size*(.57)-sway*.5, y+size*.20,
                             size*.98, y-size*.04)
                stroke(veil, color, width)
            for x, y, radius in ((.20,.30,.012),(.78,.37,.010),(.69,.70,.008),(.30,.77,.007)):
                glint(size*x, size*y, size*radius, int(100+pulse*90), (228,250,255))
        elif self.style == "emerald":
            # Irregular ice plates, nested hairline cracks and a traveling
            # glint; the offset network avoids a generic starburst.
            seams = QPainterPath()
            d = (flow-.5)*size*.035
            seams.moveTo(size*.16, size*.28); seams.cubicTo(size*.31, size*.31, size*.37, size*.42, size*.49+d, size*.47)
            seams.moveTo(size*.49+d, size*.47); seams.cubicTo(size*.59, size*.42, size*.72, size*.34, size*.84, size*.37)
            seams.moveTo(size*.49+d, size*.47); seams.cubicTo(size*.56, size*.58, size*.60, size*.68, size*.80, size*.76)
            seams.moveTo(size*.49+d, size*.47); seams.cubicTo(size*.40, size*.55, size*.33, size*.65, size*.22, size*.70)
            seams.moveTo(size*.35, size*.39); seams.cubicTo(size*.31, size*.47, size*.27, size*.51, size*.19, size*.54)
            seams.moveTo(size*.65, size*.41); seams.cubicTo(size*.70, size*.48, size*.76, size*.52, size*.84, size*.53)
            stroke(seams, QColor(225, 255, 244, 177), .012)
            hairline = QPainterPath(); hairline.moveTo(size*.17, size*.30); hairline.lineTo(size*.49+d, size*.47); hairline.lineTo(size*.81, size*.75)
            stroke(hairline, QColor(255,255,255,93), .0045)
            glint(size*(.49+d/size), size*.47, size*.018, int(90+pulse*100), (235,255,246))
        elif self.style == "crimson":
            # Broken cloud filaments and a slowly rotating storm with a clear
            # warm eye. The broad bands live in the base gradient.
            x = size*(.47 + (flow-.5)*.10)
            y = size*(.35 + (pulse-.5)*.045)
            for offset, alpha, width in ((.06,105,.008),(.11,75,.005),(.72,86,.007),(.77,62,.004)):
                band = QPainterPath(); yy = size*(offset + (flow-.5)*.025)
                band.moveTo(size*.04, yy); band.cubicTo(size*.31, yy-size*.035, size*.66, yy+size*.04, size*.96, yy-size*.015)
                stroke(band, QColor(255, 240, 206, alpha), width)
            painter.setPen(Qt.PenStyle.NoPen)
            storm = QRadialGradient(x, y, size*.16)
            storm.setColorAt(0, QColor(255, 224, 166, 245))
            storm.setColorAt(.22, QColor(202, 95, 65, 235))
            storm.setColorAt(.62, QColor(133, 57, 54, 195))
            storm.setColorAt(1, QColor(127, 56, 53, 0))
            painter.setBrush(storm)
            painter.drawEllipse(QRectF(x-size*.16, y-size*.095, size*.32, size*.19))
            spiral = QPainterPath(); spiral.moveTo(x-size*.06,y+size*.01)
            spiral.cubicTo(x-size*.02,y-size*.08,x+size*.12,y-size*.04,x+size*.08,y+size*.015)
            spiral.cubicTo(x+size*.04,y+size*.06,x-size*.025,y+size*.025,x-size*.02,y-size*.005)
            stroke(spiral, QColor(255, 221, 169, 198), .009)
        elif self.style == "amethyst":
            # Two tilted tracks share one orbital plane; the bright satellite
            # moves independently of the surface's slow breathing.
            painter.save()
            painter.translate(size*.5, size*.5)
            painter.rotate(-24)
            painter.translate(-size*.5, -size*.5)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(213, 223, 255, 98), max(1.0, size*.008)))
            painter.drawEllipse(QRectF(size*.02, size*.32, size*.96, size*.36))
            painter.setPen(QPen(QColor(246, 247, 255, 219), max(1.0, size*.018)))
            painter.drawEllipse(QRectF(size*.035, size*.36, size*.93, size*.28))
            painter.setPen(QPen(QColor(168, 196, 255, 154), max(1.0, size*.006)))
            painter.drawEllipse(QRectF(size*.12, size*.405, size*.76, size*.19))
            theta = math.radians(orbit)
            mx = size*.5 + math.cos(theta)*size*.46
            my = size*.5 + math.sin(theta)*size*.14
            painter.setPen(Qt.PenStyle.NoPen)
            moon_glow = QRadialGradient(QPointF(mx,my), size*.075)
            moon_glow.setColorAt(0, QColor(255,255,255,238)); moon_glow.setColorAt(1,QColor(207,225,255,0))
            painter.setBrush(moon_glow); painter.drawEllipse(QRectF(mx-size*.075,my-size*.075,size*.15,size*.15))
            painter.setBrush(QColor(249,252,255,248)); painter.drawEllipse(QRectF(mx-size*.024,my-size*.024,size*.048,size*.048))
            painter.restore()
            painter.save(); painter.translate(size*.5,size*.5); painter.rotate(-24); painter.translate(-size*.5,-size*.5)
            painter.setBrush(Qt.BrushStyle.NoBrush); painter.setPen(QPen(QColor(239,245,255,185), max(1.0,size*.016)))
            painter.drawArc(QRectF(size*.035,size*.36,size*.93,size*.28), 205*16, 132*16)
            painter.restore()
        elif self.style == "solaris":
            # An offset shadow crosses a large rosy disc; a bright limb and
            # separated corona preserve a crisp eclipse silhouette.
            center = QPointF(size*.5, size*.51)
            radius = size*.285
            corona = QRadialGradient(center, radius*1.50)
            corona.setColorAt(.66, QColor(255, 226, 207, 0))
            corona.setColorAt(.78, QColor(255, 204, 190, int(188 + pulse*50)))
            corona.setColorAt(.91, QColor(255, 157, 177, 74))
            corona.setColorAt(1.0, QColor(226, 131, 157, 0))
            painter.setPen(Qt.PenStyle.NoPen); painter.setBrush(corona)
            painter.drawEllipse(QRectF(center.x()-radius*1.35, center.y()-radius*1.35,
                                       radius*2.7, radius*2.7))
            painter.setBrush(QColor(255, 220, 213, 235))
            painter.drawEllipse(QRectF(center.x()-radius, center.y()-radius,
                                       radius*2, radius*2))
            shadow = QRectF(center.x()-radius*.34 + (flow-.5)*size*.15,
                            center.y()-radius*.93, radius*1.86, radius*1.86)
            shade = QRadialGradient(shadow.center(), radius*1.9)
            shade.setColorAt(0,QColor(64,34,81,255)); shade.setColorAt(.72,QColor(92,47,96,250)); shade.setColorAt(1,QColor(136,69,112,235))
            painter.setBrush(shade)
            painter.drawEllipse(shadow)
            painter.setPen(QPen(QColor(255, 211, 207, 188), max(1.0, size*.009)))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawArc(QRectF(center.x()-radius*1.15, center.y()-radius*1.15,
                                   radius*2.3, radius*2.3), 25*16, 142*16)
            glint(size*.29,size*.32,size*.012,int(110+pulse*70),(255,241,229))
        elif self.style == "ocean":
            # A major tectonic split branches into smaller cracks. Two angular
            # facets catch light so the surface reads as layered ice.
            fault = QPainterPath()
            shift = (flow-.5)*size*.045
            fault.moveTo(size*.29, size*.18); fault.lineTo(size*.41, size*.35); fault.lineTo(size*.37+shift, size*.48)
            fault.lineTo(size*.57, size*.57); fault.lineTo(size*.52, size*.68); fault.lineTo(size*.73, size*.81)
            fault.moveTo(size*.39,size*.41); fault.lineTo(size*.25,size*.48); fault.lineTo(size*.18,size*.61)
            fault.moveTo(size*.57,size*.57); fault.lineTo(size*.70,size*.48); fault.lineTo(size*.83,size*.46)
            fault.moveTo(size*.54,size*.65); fault.lineTo(size*.66,size*.70); fault.lineTo(size*.78,size*.68)
            stroke(fault,QColor(220,255,255,211),.018)
            facet = QPainterPath(); facet.moveTo(size*.18,size*.27); facet.lineTo(size*.34,size*.20); facet.lineTo(size*.41,size*.35); facet.closeSubpath()
            painter.setPen(QPen(QColor(229,255,255,110),max(1.0,size*.006))); painter.setBrush(QColor(205,255,246,23)); painter.drawPath(facet)
            facet2 = QPainterPath(); facet2.moveTo(size*.63,size*.73); facet2.lineTo(size*.80,size*.60); facet2.lineTo(size*.82,size*.78); facet2.closeSubpath()
            painter.setPen(QPen(QColor(213,251,255,100),max(1.0,size*.005))); painter.setBrush(QColor(190,244,255,24)); painter.drawPath(facet2)
            hairline=QPainterPath(); hairline.moveTo(size*.27,size*.20); hairline.lineTo(size*.40,size*.36); hairline.lineTo(size*.37+shift,size*.48)
            stroke(hairline,QColor(255,255,255,105),.005)
            glint(size*.41,size*.36,size*.014,int(100+pulse*85),(242,255,255))
        elif self.style == "titan":
            # Titan is a deep violet haze, not a second ringed planet: several
            # soft, offset cloud decks drift at different speeds.
            painter.setBrush(Qt.BrushStyle.NoBrush)
            for index,(yy,alpha,width,drift) in enumerate(((.28,130,.045,1),(.40,116,.030,-1),(.58,92,.023,1),(.70,74,.015,-1))):
                deck=QPainterPath(); offset=(flow-.5)*size*.07*drift; y=size*yy
                deck.moveTo(size*.05,y+size*.03); deck.cubicTo(size*.28+offset,y-size*.10,size*.66-offset,y+size*.11,size*.96,y-size*.035)
                stroke(deck,QColor(224-index*7,209-index*8,255,alpha),width)
            haze=QRadialGradient(size*(.72-(flow-.5)*.08),size*.30,size*.30)
            haze.setColorAt(0,QColor(239,226,255,int(115+pulse*60))); haze.setColorAt(1,QColor(190,160,238,0))
            painter.setPen(Qt.PenStyle.NoPen); painter.setBrush(haze); painter.drawEllipse(QRectF(size*.50,size*.08,size*.45,size*.45))
            glint(size*.77,size*.29,size*.009,int(65+pulse*65),(245,235,255))
        elif self.style == "triton":
            # A blue polar cap, etched glacial seams and one rising cryogenic
            # plume distinguish this from Boreal's soft ribbon-like curtains.
            cap=QPainterPath(); cap.moveTo(size*.12,size*.37); cap.cubicTo(size*.18,size*.08,size*.73,size*.07,size*.88,size*.35)
            cap.cubicTo(size*.70,size*.27,size*.57,size*.39,size*.43,size*.32); cap.cubicTo(size*.31,size*.27,size*.22,size*.38,size*.12,size*.37); cap.closeSubpath()
            painter.setPen(QPen(QColor(231,248,255,105),max(1.0,size*.008))); painter.setBrush(QColor(213,243,255,73)); painter.drawPath(cap)
            for index,(yy,alpha,width) in enumerate(((.45,194,.017),(.55,133,.010),(.67,93,.007))):
                seam=QPainterPath(); offset=(flow-.5)*size*.04*(1 if index%2==0 else -1); y=size*yy
                seam.moveTo(size*.12,y); seam.cubicTo(size*.30+offset,y+size*.12,size*.64-offset,y-size*.13,size*.88,y+size*.015)
                stroke(seam,QColor(211,244,255,alpha),width)
            plume_x=size*(.63+(flow-.5)*.025); plume_y=size*(.34-(pulse*.065))
            plume=QPainterPath(); plume.moveTo(size*.61,size*.39); plume.cubicTo(size*.57,size*.28,plume_x-size*.015,plume_y+size*.04,plume_x,plume_y)
            stroke(plume,QColor(226,249,255,int(155+pulse*55)),.010)
            for index in range(4):
                dot_y=plume_y-size*(.035+index*.025)
                glint(plume_x+size*math.sin(self.phase*.4+index)*.025,dot_y,size*.005,int(80+pulse*75),(232,249,255))
        elif self.style == "quasar":
            # A compact hot core feeds two opposing, tapered light jets.
            # Their breathing is subtle and axial, unlike the orbital skin.
            axis = (flow-.5)*size*.025
            for direction, alpha in ((-1, 110), (1, 155)):
                jet = QPainterPath()
                jet.moveTo(size*(.5+axis/size), size*.48)
                jet.cubicTo(size*.43, size*(.40 if direction < 0 else .58), size*.24, size*(.30 if direction < 0 else .68), size*.08, size*(.22 if direction < 0 else .78))
                jet.cubicTo(size*.28, size*(.35 if direction < 0 else .65), size*.39, size*(.44 if direction < 0 else .56), size*.5, size*.52)
                stroke(jet, QColor(239, 211, 255, alpha), .024 if direction < 0 else .018)
            core = QRadialGradient(size*(.5+axis/size), size*.50, size*.105)
            core.setColorAt(0, QColor(255,255,255,250)); core.setColorAt(.26, QColor(247,219,255,235)); core.setColorAt(1, QColor(204,126,255,0))
            painter.setPen(Qt.PenStyle.NoPen); painter.setBrush(core)
            painter.drawEllipse(QRectF(size*.38+axis,size*.38,size*.24,size*.24))
            glint(size*(.5+axis/size),size*.5,size*.025,int(170+pulse*70),(255,255,255))
        elif self.style == "lunar":
            # Three shaded basins and a moving terminator give the metal-gray
            # finish an unmistakable lunar relief rather than another cloud.
            offset=(flow-.5)*size*.08
            for x,y,r in ((.32,.38,.095),(.65,.31,.062),(.62,.65,.105),(.30,.68,.045)):
                basin=QRadialGradient(size*(x-.02),size*(y-.02),size*r*1.7)
                basin.setColorAt(0,QColor(44,49,62,118)); basin.setColorAt(.62,QColor(73,79,94,52)); basin.setColorAt(1,QColor(246,246,242,0))
                painter.setPen(QPen(QColor(250,250,245,68),max(1.0,size*.004))); painter.setBrush(basin)
                painter.drawEllipse(QRectF(size*(x-r),size*(y-r),size*r*2,size*r*2))
            terminator=QPainterPath(); terminator.moveTo(size*(.46+offset/size),size*.08)
            terminator.cubicTo(size*(.23+offset/size),size*.34,size*(.75+offset/size),size*.59,size*(.50+offset/size),size*.92)
            stroke(terminator,QColor(255,255,244,int(85+pulse*55)),.009)
            glint(size*.73,size*.48,size*.012,int(70+pulse*85),(255,255,246))
        painter.restore()


class _VoiceDownload(QThread):
    finished_voice = Signal(str, str)
    progress = Signal(str, int, int)

    def __init__(self, voice_id):
        super().__init__()
        self.voice_id = voice_id

    def run(self):
        try:
            ensure_voice(self.voice_id, lambda name, done, total: self.progress.emit(name, done, total))
            self.finished_voice.emit(self.voice_id, "")
        except Exception as exc:
            self.finished_voice.emit(self.voice_id, str(exc))


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
                              f"Não consegui carregar o Vosk ({type(exc).__name__}). Confira o modelo instalado e tente novamente.", False)


class _WakeCapture(QThread):
    captured = Signal(object)
    failed = Signal(str)

    def run(self):
        try:
            import sounddevice as sd
            audio = sd.rec(int(16_000 * 2.4), samplerate=16_000, channels=1, dtype="int16")
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
        if self._selected_feedback not in FEEDBACK_THEME_KEYS:
            self._selected_feedback = "boreal"
        self.setWindowTitle("Aurora Studio")
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        self.setModal(True)
        # A deliberate two-column studio layout: navigation and live preview
        # stay anchored while each focused setup step uses the remaining space.
        self.setMinimumSize(820, 580)
        self.resize(980, 650)
        self._dark_theme = True
        self.setStyleSheet(self._studio_stylesheet(True))

        # Page changes use short easing transitions without moving the form
        # controls, so fields and carousel hit targets remain stable.
        self._transition_group = None
        self._transition_old_page = None
        self._transition_new_page = None
        self._selected_voice = str(cfg.get("tts_voice", "pt_BR-faber-medium"))
        if self._selected_voice not in {voice.key for voice in VOICES}:
            self._selected_voice = "pt_BR-faber-medium"
        configured_voice = next((voice for voice in VOICES if voice.key == self._selected_voice), VOICES[0])
        self._selected_tts_engine = configured_voice.engine

        for name in ("select", "step", "success", "error"):
            effect = QSoundEffect(self)
            effect.setSource(QUrl.fromLocalFile(str(__import__("pathlib").Path(__file__).resolve().parents[2] / "assets" / "audio" / f"{name}.wav")))
            effect.setVolume(0.16 if name in {"select", "step"} else (0.22 if name != "error" else 0.30))
            self._sfx[name] = effect
        for theme, *_ in FEEDBACK_THEMES:
            for direction in ("entrada", "saida"):
                effect = QSoundEffect(self)
                effect.setSource(QUrl.fromLocalFile(str(__import__("pathlib").Path(__file__).resolve().parents[2] / "assets" / "audio" / f"{direction}-{theme}.wav")))
                effect.setVolume(0.28)
                self._feedback_sfx[f"{theme}:{direction}"] = effect

        self._route_pages = [0, 1, 2, 3, 4, 5, 6]
        self._step_rows = {}
        self._progress_animation = None
        self.stack = QStackedWidget()
        self._build_welcome()
        self._build_profile()
        self._build_conversation_preferences()
        self._build_wake_training()
        self._build_bubble()
        self._build_voice()
        self._build_feedback()
        self._build_loading()

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_navigation_rail())

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(28, 22, 28, 20)
        content_layout.setSpacing(14)
        header = QHBoxLayout()
        self.eyebrow = QLabel("AURORA STUDIO  /  PERSONALIZAÇÃO")
        self.eyebrow.setObjectName("eyebrow")
        header.addWidget(self.eyebrow)
        header.addStretch(1)
        self.progress_counter = QLabel("01 / 07")
        self.progress_counter.setObjectName("stepCounter")
        header.addWidget(self.progress_counter)
        content_layout.addLayout(header)
        self.page_progress = QProgressBar()
        self.page_progress.setObjectName("stepProgress")
        self.page_progress.setTextVisible(False)
        self.page_progress.setFixedHeight(5)
        self.page_progress.setRange(0, 6)
        content_layout.addWidget(self.page_progress)
        self.stack.setObjectName("pageStack")
        self.stack.setMinimumSize(0, 0)
        content_layout.addWidget(self.stack, 1)
        footer = QHBoxLayout()
        self.step_label = QLabel("SEU PERFIL FICA NESTE COMPUTADOR")
        self.step_label.setObjectName("footerNote")
        footer.addWidget(self.step_label)
        footer.addStretch(1)
        self.back_button = QPushButton("Voltar")
        self.back_button.setObjectName("secondary")
        self.back_button.clicked.connect(self.back)
        footer.addWidget(self.back_button)
        self.next_button = QPushButton("Começar")
        self.next_button.setObjectName("primary")
        self.next_button.setMinimumHeight(44)
        self.next_button.clicked.connect(self.next)
        footer.addWidget(self.next_button)
        content_layout.addLayout(footer)
        root.addWidget(content, 1)

        self._voice_download_worker = None
        self._current_page = 0
        self._set_page(0, animated=False)
        self._center()

    def _build_navigation_rail(self):
        rail = QFrame()
        rail.setObjectName("navigationRail")
        rail.setFixedWidth(238)
        layout = QVBoxLayout(rail)
        layout.setContentsMargins(16, 16, 14, 14)
        layout.setSpacing(6)

        brand = QHBoxLayout()
        brand.setSpacing(10)
        mark = QLabel("✦")
        mark.setObjectName("brandMark")
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark.setFixedSize(34, 34)
        brand.addWidget(mark)
        brand_copy = QVBoxLayout()
        brand_copy.setSpacing(0)
        name = QLabel("AURORA")
        name.setObjectName("brandName")
        studio = QLabel("STUDIO  ·  SETUP")
        studio.setObjectName("brandCaption")
        brand_copy.addWidget(name)
        brand_copy.addWidget(studio)
        brand.addLayout(brand_copy)
        brand.addStretch(1)
        layout.addLayout(brand)

        layout.addSpacing(2)
        intro = QLabel("Sua assistente,\ndo seu jeito.")
        intro.setObjectName("railHeading")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        intro_note = QLabel("Configuração pessoal, salva neste computador.")
        intro_note.setObjectName("railDescription")
        intro_note.setWordWrap(True)
        layout.addWidget(intro_note)

        preview = QFrame()
        preview.setObjectName("railPreview")
        preview_layout = QVBoxLayout(preview)
        preview.setFixedHeight(142)
        preview_layout.setContentsMargins(8, 3, 8, 3)
        preview_layout.setSpacing(0)
        self.rail_orb = _AnimatedOrb(self._selected_style, preview, opacity=1.0)
        self.rail_orb.setFixedSize(76, 76)
        preview_layout.addWidget(self.rail_orb, 0, Qt.AlignmentFlag.AlignHCenter)
        self.rail_preview_name = QLabel("Aurora")
        self.rail_preview_name.setObjectName("railPreviewTitle")
        self.rail_preview_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_layout.addWidget(self.rail_preview_name)
        self.rail_preview_detail = QLabel("Perfil em construção")
        self.rail_preview_detail.setObjectName("railPreviewDetail")
        self.rail_preview_detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.rail_preview_detail.setWordWrap(True)
        preview_layout.addWidget(self.rail_preview_detail)
        layout.addWidget(preview)

        divider = QFrame()
        divider.setObjectName("railDivider")
        divider.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(divider)
        section_label = QLabel("SEU PERCURSO")
        section_label.setObjectName("railSection")
        layout.addWidget(section_label)
        self._step_rows = {}
        for page, title in ((0, "Boas-vindas"), (1, "Identidade"), (2, "Conversa"),
                            (3, "Nome de ativação"), (4, "Aparência"),
                            (5, "Voz local"), (6, "Sons")):
            row = QFrame()
            row.setObjectName("stepRow")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(7, 3, 7, 3)
            row_layout.setSpacing(8)
            number = QLabel("✦" if page == 0 else f"{page:02d}")
            number.setObjectName("stepDot")
            number.setAlignment(Qt.AlignmentFlag.AlignCenter)
            number.setFixedSize(22, 22)
            caption = QLabel(title)
            caption.setObjectName("stepName")
            row.setFixedHeight(30)
            row_layout.addWidget(number)
            row_layout.addWidget(caption, 1)
            layout.addWidget(row)
            self._step_rows[page] = (row, number, caption)
        layout.addStretch(1)
        privacy = QLabel("◈  PRIVADO POR PADRÃO\nSuas escolhas ficam neste computador.")
        privacy.setObjectName("railPrivacy")
        privacy.setWordWrap(True)
        layout.addWidget(privacy)
        return rail

    def _add_page(self, card):
        """Keep each step card content-sized; let the canvas breathe around it."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addStretch(1)
        layout.addWidget(card, 0, Qt.AlignmentFlag.AlignTop)
        layout.addStretch(1)
        self.stack.addWidget(page)

    def _refresh_rail_preview(self):
        if not hasattr(self, "rail_preview_name"):
            return
        assistant = "Aurora"
        if hasattr(self, "assistant_name") and not self.default_name.isChecked():
            assistant = self.assistant_name.text().strip() or "Sua assistente"
        user = self.user_name.text().strip() if hasattr(self, "user_name") else ""
        style = next((title for key, title, _detail in BUBBLE_STYLES if key == self._selected_style), "Aurora")
        voice = next((item.name for item in VOICES if item.key == self._selected_voice), VOICES[0].name)
        self.rail_preview_name.setText(assistant)
        personal = f"Para {user}" if user else "Seu perfil em construção"
        self.rail_preview_detail.setText(f"{personal}\n{style} · {voice}")
        if hasattr(self, "rail_orb"):
            self.rail_orb.set_style(self._selected_style)

    def _system_prefers_dark(self):
        from PySide6.QtWidgets import QApplication
        palette = QApplication.instance().palette()
        return palette.color(palette.ColorRole.Window).lightness() < 128

    @staticmethod
    def _studio_stylesheet(dark):
        """A calmer Studio visual system with a persistent preview rail."""
        if dark:
            return """
            QDialog { background:#0b0c12; color:#f4f2f8; }
            QWidget#navigationRail { background:#101018; border-right:1px solid #292735; }
            QFrame#railPreview { background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #211c2e,stop:1 #151720); border:1px solid #393348; border-radius:18px; }
            QFrame#railDivider { color:#302c3a; background:#302c3a; max-height:1px; }
            QLabel { color:#efedf5; }
            QLabel#brandMark { color:#f1dfff; background:#322747; border:1px solid #5a4778; border-radius:11px; font-size:19px; font-weight:700; }
            QLabel#brandName { color:#f7f2ff; font-size:14px; font-weight:800; letter-spacing:1.5px; }
            QLabel#brandCaption, QLabel#railSection { color:#a69bb9; font-size:9px; font-weight:800; letter-spacing:1.5px; }
            QLabel#railHeading { color:#f5f0fb; font-size:21px; font-weight:750; }
            QLabel#railDescription { color:#aaa4b5; font-size:11px; }
            QLabel#railPreviewTitle { color:#f4edff; font-size:13px; font-weight:700; }
            QLabel#railPreviewDetail { color:#a9a2b5; font-size:10px; }
            QFrame#stepRow { background:transparent; border:1px solid transparent; border-radius:11px; }
            QFrame#stepRow[current="true"] { background:#292337; border-color:#594773; }
            QFrame#stepRow[complete="true"] { background:#171923; }
            QLabel#stepDot { color:#aaa2b5; background:#211f2a; border:1px solid #3b3746; border-radius:12px; font-size:9px; font-weight:800; }
            QLabel#stepDot[current="true"] { color:#160f20; background:#d3b4ff; border-color:#d3b4ff; }
            QLabel#stepDot[complete="true"] { color:#9ce6cc; background:#172c29; border-color:#315349; }
            QLabel#stepName { color:#aaa4b2; font-size:11px; font-weight:600; }
            QFrame#stepRow[current="true"] QLabel#stepName { color:#f5ecff; font-weight:700; }
            QLabel#railPrivacy { color:#958da0; background:#15151d; border:1px solid #2c2935; border-radius:11px; padding:10px; font-size:10px; }
            QLabel#eyebrow { color:#a89bbd; font-size:10px; font-weight:800; letter-spacing:1.7px; }
            QLabel#stepCounter { color:#d3b4ff; font-size:11px; font-weight:800; letter-spacing:1px; }
            QLabel#footerNote { color:#928b9e; font-size:10px; font-weight:700; letter-spacing:.7px; }
            QProgressBar#stepProgress { background:#24222d; border:0; border-radius:3px; }
            QProgressBar#stepProgress::chunk { background:#c5a1f0; border-radius:3px; }
            QStackedWidget#pageStack { background:transparent; border:0; }
            QFrame#panel { background:#15151e; border:1px solid #302d3a; border-radius:20px; }
            QLabel#title { color:#f6f3fa; font-size:24px; font-weight:750; }
            QLabel#subtitle { color:#b8b3c0; font-size:13px; }
            QLabel#cardTitle { color:#f2eef8; font-size:16px; font-weight:700; }
            QLabel#cardDetail { color:#aaa4b3; font-size:11px; }
            QLabel#onboardingBadge { color:#ddcef2; background:#211e2a; border:1px solid #393447; border-radius:10px; padding:6px 9px; font-size:10px; font-weight:700; }
            QLabel#soundSignature { color:#d0b0fa; font-size:24px; font-weight:700; letter-spacing:3px; }
            QLabel#soundSequence, QLabel#carouselPosition { color:#a79db3; font-size:10px; font-weight:700; }
            QLabel#voiceGlyph { color:#d0b0fa; font-size:38px; }
            QLabel#voiceCarouselName { color:#f5effb; font-size:14px; font-weight:700; }
            QFrame#choiceCard { background:#1c1b25; border:1px solid #383444; border-radius:17px; }
            QFrame#choiceCard[side="true"] { background:#171720; border-color:#2d2a36; }
            QFrame#choiceCard[side="true"] QLabel { color:#817b8b; }
            QFrame#choiceCard[selected="true"] { background:#292238; border:2px solid #c9a7f4; }
            QLineEdit { background:#1e1d27; border:1px solid #464153; border-radius:11px; padding:11px 13px; min-height:23px; color:#f7f3fc; selection-background-color:#6d5493; }
            QLineEdit:focus { border:2px solid #c19bef; padding:10px 12px; }
            QComboBox { background:#1e1d27; border:1px solid #464153; border-radius:10px; padding:8px 10px; min-height:22px; color:#f7f3fc; }
            QComboBox QAbstractItemView { background:#1b1a23; color:#f7f3fc; selection-background-color:#49395f; border:1px solid #464153; }
            QSlider::groove:horizontal { height:4px; background:#393541; border-radius:2px; }
            QSlider::sub-page:horizontal { background:#c09aef; border-radius:2px; }
            QSlider::handle:horizontal { width:14px; margin:-5px 0; border-radius:7px; background:#e2c9ff; }
            QPushButton { background:#272530; color:#eeeaf4; border:1px solid #3a3745; border-radius:11px; padding:10px 15px; font-weight:650; }
            QPushButton:hover { background:#34313f; border-color:#625672; }
            QPushButton#primary { background:#ad83df; color:#17101f; border:0; padding-left:21px; padding-right:21px; font-weight:800; }
            QPushButton#primary:hover { background:#c09aef; }
            QPushButton#secondary { background:transparent; border-color:#403c49; }
            QPushButton#selectStyle, QPushButton#previewVoice { background:#24212e; border:1px solid #464052; }
            QPushButton#carouselArrow { background:#211f29; color:#f0eafd; border:1px solid #494354; border-radius:21px; padding:0; font-size:26px; }
            QPushButton#carouselArrow:hover { background:#342b42; border-color:#c19bef; }
            QProgressBar { background:#24222d; color:#f4effa; border:0; border-radius:7px; text-align:center; font-size:10px; }
            QProgressBar::chunk { background:#ad83df; border-radius:7px; }
            QCheckBox, QRadioButton { spacing:9px; color:#d8d2df; }
            QRadioButton::indicator { width:18px; height:18px; }
            """
        return """
            QDialog { background:#f1f0f5; color:#25222d; }
            QWidget#navigationRail { background:#e9e6ef; border-right:1px solid #d8d3e1; }
            QFrame#railPreview { background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #f4edff,stop:1 #e8edf7); border:1px solid #d5cbe3; border-radius:18px; }
            QFrame#railDivider { color:#d6d1de; background:#d6d1de; max-height:1px; }
            QLabel { color:#292631; }
            QLabel#brandMark { color:#503879; background:#ded1f2; border:1px solid #c8b3e5; border-radius:11px; font-size:19px; font-weight:700; }
            QLabel#brandName { color:#27232e; font-size:14px; font-weight:800; letter-spacing:1.5px; }
            QLabel#brandCaption, QLabel#railSection { color:#71677f; font-size:9px; font-weight:800; letter-spacing:1.5px; }
            QLabel#railHeading { color:#28232f; font-size:21px; font-weight:750; }
            QLabel#railDescription { color:#625c6b; font-size:11px; }
            QLabel#railPreviewTitle { color:#30283b; font-size:13px; font-weight:700; }
            QLabel#railPreviewDetail { color:#716a79; font-size:10px; }
            QFrame#stepRow { background:transparent; border:1px solid transparent; border-radius:11px; }
            QFrame#stepRow[current="true"] { background:#ded5eb; border-color:#c5b3dc; }
            QFrame#stepRow[complete="true"] { background:#e4e1e9; }
            QLabel#stepDot { color:#6d6675; background:#f3f1f6; border:1px solid #d7d1de; border-radius:12px; font-size:9px; font-weight:800; }
            QLabel#stepDot[current="true"] { color:#fff; background:#71559c; border-color:#71559c; }
            QLabel#stepDot[complete="true"] { color:#346a57; background:#d6eadf; border-color:#afd0bd; }
            QLabel#stepName { color:#625c6b; font-size:11px; font-weight:600; }
            QFrame#stepRow[current="true"] QLabel#stepName { color:#332541; font-weight:700; }
            QLabel#railPrivacy { color:#615a6b; background:#f4f2f7; border:1px solid #d9d4df; border-radius:11px; padding:10px; font-size:10px; }
            QLabel#eyebrow { color:#6f657b; font-size:10px; font-weight:800; letter-spacing:1.7px; }
            QLabel#stepCounter { color:#684b92; font-size:11px; font-weight:800; letter-spacing:1px; }
            QLabel#footerNote { color:#706979; font-size:10px; font-weight:700; letter-spacing:.7px; }
            QProgressBar#stepProgress { background:#ddd9e4; border:0; border-radius:3px; }
            QProgressBar#stepProgress::chunk { background:#8062b7; border-radius:3px; }
            QStackedWidget#pageStack { background:transparent; border:0; }
            QFrame#panel { background:#fff; border:1px solid #e0dce6; border-radius:20px; }
            QLabel#title { color:#27242d; font-size:24px; font-weight:750; }
            QLabel#subtitle { color:#615d68; font-size:13px; }
            QLabel#cardTitle { color:#292631; font-size:16px; font-weight:700; }
            QLabel#cardDetail { color:#6d6874; font-size:11px; }
            QLabel#onboardingBadge { color:#57476d; background:#f0edf5; border:1px solid #dfd9e8; border-radius:10px; padding:6px 9px; font-size:10px; font-weight:700; }
            QLabel#soundSignature { color:#7657a5; font-size:24px; font-weight:700; letter-spacing:3px; }
            QLabel#soundSequence, QLabel#carouselPosition { color:#71677d; font-size:10px; font-weight:700; }
            QFrame#choiceCard { background:#faf9fc; border:1px solid #e0dce6; border-radius:17px; }
            QFrame#choiceCard[side="true"] { background:#f0eef4; border-color:#e2deea; }
            QFrame#choiceCard[side="true"] QLabel { color:#9892a0; }
            QFrame#choiceCard[selected="true"] { background:#f2edf9; border:2px solid #8062b7; }
            QLineEdit, QComboBox { background:#fbfaff; border:1px solid #d7d3df; border-radius:11px; padding:11px 13px; min-height:23px; color:#292631; }
            QLineEdit:focus { border:2px solid #8062b7; padding:10px 12px; }
            QComboBox QAbstractItemView { background:#fff; color:#292631; selection-background-color:#e8dff4; }
            QSlider::groove:horizontal { height:4px; background:#ddd9e4; border-radius:2px; }
            QSlider::sub-page:horizontal { background:#8062b7; border-radius:2px; }
            QSlider::handle:horizontal { width:14px; margin:-5px 0; border-radius:7px; background:#71559c; }
            QPushButton { background:#eeecf3; color:#302e37; border:1px solid #dfdbe6; border-radius:11px; padding:10px 15px; font-weight:650; }
            QPushButton:hover { background:#e4dfeb; }
            QPushButton#primary { background:#71559c; color:#fff; border:0; padding-left:21px; padding-right:21px; font-weight:800; }
            QPushButton#primary:hover { background:#8062b7; }
            QPushButton#secondary { background:transparent; border-color:#d5d0dc; }
            QPushButton#selectStyle, QPushButton#previewVoice { background:#f0edf6; border:1px solid #ded8e8; }
            QPushButton#carouselArrow { background:#f0edf6; color:#302e37; border:1px solid #d9d2e4; border-radius:21px; padding:0; font-size:26px; }
            QPushButton#carouselArrow:hover { background:#e8e2f2; border-color:#8062b7; }
            QProgressBar { background:#e8e4ee; color:#302e37; border:0; border-radius:7px; text-align:center; font-size:10px; }
            QProgressBar::chunk { background:#8062b7; border-radius:7px; }
            QCheckBox, QRadioButton { spacing:9px; color:#494451; }
            QRadioButton::indicator { width:18px; height:18px; }
            """

    def _apply_system_theme(self):
        # Aurora Studio intentionally stays dark: onboarding is a focused,
        # branded surface and must not inherit a bright desktop theme.
        self._dark_theme = True
        self.setStyleSheet(self._studio_stylesheet(True))

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
        overview = QHBoxLayout()
        overview.setSpacing(20)
        copy = QVBoxLayout()
        copy.setSpacing(10)
        label = QLabel("FEITO PARA VOCÊ")
        label.setObjectName("eyebrow")
        copy.addWidget(label)
        note = QLabel("Escolha como a Aurora aparece, fala e responde ao seu nome. Tudo fica neste computador.")
        note.setObjectName("subtitle")
        note.setWordWrap(True)
        copy.addWidget(note)
        facts = QHBoxLayout()
        facts.setSpacing(8)
        voice_count = f"{len(VOICES)} voz local" if len(VOICES) == 1 else f"{len(VOICES)} vozes locais"
        for text in (f"{len(BUBBLE_STYLES)} acabamentos", voice_count,
                     f"{len(FEEDBACK_THEMES)} assinaturas sonoras"):
            badge = QLabel(text)
            badge.setObjectName("onboardingBadge")
            facts.addWidget(badge)
        facts.addStretch(1)
        copy.addLayout(facts)
        overview.addLayout(copy, 1)
        hero = QVBoxLayout()
        hero.setSpacing(4)
        glow = _AnimatedOrb(self._selected_style)
        glow.setFixedSize(158, 158)
        self.welcome_orb = glow
        hero.addWidget(glow, 0, Qt.AlignmentFlag.AlignCenter)
        initial_style_name = next(item[1] for item in BUBBLE_STYLES if item[0] == self._selected_style)
        self.welcome_style_title = QLabel(initial_style_name)
        self.welcome_style_title.setObjectName("cardTitle")
        self.welcome_style_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hero.addWidget(self.welcome_style_title)
        hero_note = QLabel("aparência selecionada")
        hero_note.setObjectName("cardDetail")
        hero_note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hero.addWidget(hero_note)
        overview.addLayout(hero, 0)
        layout.addLayout(overview, 1)
        self._add_page(frame)

    def _build_profile(self):
        frame, layout = self._panel("Vamos nos conhecer", "Defina como a Aurora chama você e escolha o nome que vai despertá-la.")
        identity_note = QLabel("Essas escolhas ficam neste computador e podem ser alteradas depois no Aurora Studio.")
        identity_note.setWordWrap(True)
        identity_note.setObjectName("cardDetail")
        layout.addWidget(identity_note)
        columns = QHBoxLayout()
        columns.setSpacing(22)
        user_column = QVBoxLayout(); user_column.setSpacing(8)
        assistant_column = QVBoxLayout(); assistant_column.setSpacing(8)
        self.user_name = QLineEdit(str(self.cfg.get("user_name", "")))
        self.user_name.setPlaceholderText("Ex.: Alex")
        self.user_name.setClearButtonEnabled(True)
        self.user_name.setMinimumHeight(48)
        user_column.addWidget(QLabel("SEU NOME")); user_column.addWidget(self.user_name)
        self.user_name_note = QLabel("Usado nas saudações. Pode ser apelido ou nome curto.")
        self.user_name_note.setObjectName("cardDetail")
        user_column.addWidget(self.user_name_note)
        assistant_column.addWidget(QLabel("NOME DE ATIVAÇÃO"))
        self.assistant_name = QLineEdit(str(self.cfg.get("assistant_name", "Aurora")))
        self.assistant_name.setPlaceholderText("Ex.: Aurora")
        self.assistant_name.setMaxLength(80)
        self.assistant_name.setClearButtonEnabled(True)
        self.assistant_name.setMinimumHeight(48)
        assistant_column.addWidget(self.assistant_name)
        self.default_name = QCheckBox("Manter o nome Aurora")
        self.default_name.setChecked(str(self.cfg.get("assistant_name", "Aurora")).casefold() == "aurora")
        self.default_name.toggled.connect(self.assistant_name.setHidden)
        self.default_name.toggled.connect(self._assistant_name_changed)
        self.assistant_name.textChanged.connect(self._assistant_name_changed)
        self.assistant_name.setHidden(self.default_name.isChecked())
        assistant_column.addWidget(self.default_name)
        self.name_note = QLabel("O nome será conferido no vocabulário local. Se não for reconhecido, você poderá gravar algumas amostras.")
        self.name_note.setWordWrap(True)
        self.name_note.setObjectName("cardDetail")
        assistant_column.addWidget(self.name_note)
        columns.addLayout(user_column, 1)
        columns.addLayout(assistant_column, 1)
        layout.addLayout(columns)

        self._add_page(frame)

    def _build_conversation_preferences(self):
        frame, layout = self._panel(
            "Como você prefere conversar?",
            "Escolha um ponto de partida. A Aurora ainda adapta as respostas ao que você pedir.",
        )
        style_heading = QLabel("PERSONALIDADE E RITMO")
        style_heading.setObjectName("eyebrow")
        layout.addWidget(style_heading)
        style_row = QHBoxLayout()
        style_row.setSpacing(14)

        personality_column = QVBoxLayout()
        personality_column.setSpacing(5)
        personality_column.addWidget(QLabel("Personalidade"))
        self.personality_choice = QComboBox()
        for label, value in (("Companheira · próxima e natural", "companion"),
                             ("Objetiva · direta e organizada", "direct"),
                             ("Brincalhona · leve quando couber", "playful"),
                             ("Formal · polida e profissional", "formal")):
            self.personality_choice.addItem(label, value)
        personality_index = self.personality_choice.findData(self.cfg.get("assistant_personality", "companion"))
        self.personality_choice.setCurrentIndex(max(0, personality_index))
        personality_column.addWidget(self.personality_choice)
        style_row.addLayout(personality_column, 1)

        detail_column = QVBoxLayout()
        detail_column.setSpacing(5)
        detail_column.addWidget(QLabel("Nível de detalhe"))
        self.detail_choice = QComboBox()
        for label, value in (("Conciso", "concise"), ("Equilibrado", "balanced"), ("Explicativo", "detailed")):
            self.detail_choice.addItem(label, value)
        detail_index = self.detail_choice.findData(self.cfg.get("response_detail", "balanced"))
        self.detail_choice.setCurrentIndex(max(0, detail_index))
        detail_column.addWidget(self.detail_choice)
        style_row.addLayout(detail_column, 1)

        tone_column = QVBoxLayout()
        tone_column.setSpacing(4)
        tone_label_row = QHBoxLayout()
        tone_label_row.addWidget(QLabel("Tom da conversa"))
        tone_label_row.addStretch(1)
        self.tone_value = QLabel()
        self.tone_value.setObjectName("cardDetail")
        tone_label_row.addWidget(self.tone_value)
        tone_column.addLayout(tone_label_row)
        self.tone_slider = QSlider(Qt.Orientation.Horizontal)
        self.tone_slider.setRange(0, 100)
        self.tone_slider.setValue(max(0, min(100, int(self.cfg.get("conversation_tone", 55)))))
        self.tone_slider.valueChanged.connect(self._update_tone_label)
        tone_column.addWidget(self.tone_slider)
        tone_bounds = QHBoxLayout()
        tone_bounds.addWidget(QLabel("Neutro"))
        tone_bounds.addStretch(1)
        tone_bounds.addWidget(QLabel("Caloroso"))
        tone_column.addLayout(tone_bounds)
        style_row.addLayout(tone_column, 1)
        layout.addLayout(style_row)

        custom_label = QLabel("INSTRUÇÃO PESSOAL · OPCIONAL")
        layout.addWidget(custom_label)
        self.custom_instructions = QLineEdit(str(self.cfg.get("custom_instructions", "")))
        self.custom_instructions.setMaxLength(240)
        self.custom_instructions.setPlaceholderText("Ex.: use exemplos práticos e evite introduções longas")
        self.custom_instructions.setClearButtonEnabled(True)
        layout.addWidget(self.custom_instructions)
        self._add_page(frame)
        self._update_tone_label(self.tone_slider.value())

    def _update_tone_label(self, value):
        if hasattr(self, "tone_value"):
            self.tone_value.setText("Neutro" if value < 30 else "Equilibrado" if value < 70 else "Caloroso")

    def _build_wake_training(self):
        frame, layout = self._panel(
            "Ensine o nome de ativação",
            "O Vosk local não reconhece esse nome ainda. Grave quatro vezes para criar uma referência acústica privada neste computador.",
        )
        self.wake_training_hint = QLabel(
            "Clique para gravar e diga o nome uma vez em voz natural. Cada gravação dura até 2,4 segundos; faça uma pausa curta antes da próxima."
        )
        self.wake_training_hint.setObjectName("subtitle")
        self.wake_training_hint.setWordWrap(True)
        layout.addWidget(self.wake_training_hint)
        self.wake_training_status = QLabel("Pronto para começar · 0 de 4 amostras")
        self.wake_training_status.setObjectName("cardDetail")
        layout.addWidget(self.wake_training_status)
        self.wake_training_progress = QProgressBar()
        self.wake_training_progress.setRange(0, 4)
        self.wake_training_progress.setValue(0)
        self.wake_training_progress.setTextVisible(False)
        self.wake_training_progress.setFixedHeight(8)
        layout.addWidget(self.wake_training_progress)
        self.wake_training_button = QPushButton("Gravar amostra 1 de 4")
        self.wake_training_button.setObjectName("primary")
        self.wake_training_button.clicked.connect(self._capture_wake_sample)
        layout.addWidget(self.wake_training_button, 0, Qt.AlignmentFlag.AlignHCenter)
        self.wake_training_note = QLabel("O áudio é descartado após a análise. Só características acústicas ficam nas configurações locais; o reconhecimento continua no dispositivo.")
        self.wake_training_note.setObjectName("cardDetail")
        self.wake_training_note.setWordWrap(True)
        layout.addWidget(self.wake_training_note)
        self._add_page(frame)

    def _build_bubble(self):
        frame, layout = self._panel("Escolha a aparência da bolha", "Use as setas para percorrer os acabamentos. A prévia continua animada enquanto você escolhe.")
        self._style_index = next((i for i, item in enumerate(BUBBLE_STYLES) if item[0] == self._selected_style), 0)
        self._style_step_pending = False
        self._style_transition_group = None
        self.style_stage = _OrbCarouselStage()
        self.style_stage.setFixedHeight(190)
        self.style_side_left = _AnimatedOrb(BUBBLE_STYLES[(self._style_index - 1) % len(BUBBLE_STYLES)][0], self.style_stage, opacity=.48)
        self.style_orb = _AnimatedOrb(self._selected_style, self.style_stage)
        self.style_side_right = _AnimatedOrb(BUBBLE_STYLES[(self._style_index + 1) % len(BUBBLE_STYLES)][0], self.style_stage, opacity=.48)
        for orb in (self.style_side_left, self.style_orb, self.style_side_right):
            orb.setFixedSize(166, 166)
        self.style_side_left.displayScale = .50
        self.style_side_right.displayScale = .50
        self.style_stage.resized.connect(self._position_style_orbs)
        layout.addWidget(self.style_stage)
        self.style_title = QLabel(); self.style_title.setObjectName("cardTitle"); self.style_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.style_detail = QLabel(); self.style_detail.setObjectName("cardDetail"); self.style_detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.style_position = QLabel(); self.style_position.setObjectName("carouselPosition"); self.style_position.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.style_title); layout.addWidget(self.style_detail)
        style_nav = QHBoxLayout(); style_nav.addStretch(1)
        self.style_prev = QPushButton("‹"); self.style_prev.setObjectName("carouselArrow"); self.style_prev.setFixedSize(40, 40)
        self.style_prev.clicked.connect(lambda: self._step_style(-1))
        self.style_position.setMinimumWidth(88)
        style_nav.addWidget(self.style_prev); style_nav.addWidget(self.style_position, 0, Qt.AlignmentFlag.AlignCenter)
        self.style_next = QPushButton("›"); self.style_next.setObjectName("carouselArrow"); self.style_next.setFixedSize(40, 40)
        self.style_next.clicked.connect(lambda: self._step_style(1))
        style_nav.addWidget(self.style_next); style_nav.addStretch(1); layout.addLayout(style_nav)
        self._refresh_style_carousel()
        self._add_page(frame)

    def _build_voice(self):
        frame, layout = self._panel(
            "Escolha a voz local",
            "Faber · síntese no próprio computador. Ajuste a altura tonal e o ritmo sem trocar o modelo.",
        )
        self._voice_index = next((i for i, voice in enumerate(VOICES)
                                  if voice.key == self._selected_voice), 0)
        self._voice_step_pending = False
        self._voice_transition_group = None
        self.voice_stage = _OrbCarouselStage()
        self.voice_stage.setFixedHeight(180)
        self.voice_side_left = _AnimatedOrb(self._selected_style, self.voice_stage, opacity=0.0)
        self.voice_orb = _AnimatedOrb(self._selected_style, self.voice_stage)
        self.voice_side_right = _AnimatedOrb(self._selected_style, self.voice_stage, opacity=0.0)
        self.voice_side_left.hide(); self.voice_side_right.hide()
        self.voice_orb.setFixedSize(150, 150)
        self.voice_name_left = QLabel("", self.voice_stage); self.voice_name_left.hide()
        self.voice_title = QLabel(VOICES[0].name, self.voice_stage)
        self.voice_title.setObjectName("voiceCarouselName")
        self.voice_name_right = QLabel("", self.voice_stage); self.voice_name_right.hide()
        self.voice_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.voice_title.setFixedSize(138, 24)
        self.voice_stage.resized.connect(self._position_voice_orbs)
        layout.addWidget(self.voice_stage)
        self.voice_detail = QLabel(); self.voice_detail.setObjectName("cardDetail"); self.voice_detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.voice_position = QLabel(); self.voice_position.setObjectName("carouselPosition"); self.voice_position.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.voice_position.hide()
        layout.addWidget(self.voice_detail)
        voice_nav = QHBoxLayout()
        self.voice_prev = QPushButton("‹"); self.voice_prev.hide()
        self.voice_next = QPushButton("›"); self.voice_next.hide()
        # Pitch & Speed controls
        tuning_layout = QHBoxLayout()
        tuning_layout.setSpacing(16)
        
        # Pitch control
        pitch_box = QVBoxLayout()
        pitch_box.setSpacing(4)
        pitch_header = QHBoxLayout()
        pitch_title = QLabel("Altura tonal · grave ↔ aguda")
        pitch_title.setObjectName("cardDetail")
        self.pitch_val_label = QLabel(f"{int(float(self.cfg.get('tts_pitch', 1.25))*100)}%")
        self.pitch_val_label.setObjectName("cardDetail")
        pitch_header.addWidget(pitch_title)
        pitch_header.addStretch(1)
        pitch_header.addWidget(self.pitch_val_label)
        
        self.pitch_slider = QSlider(Qt.Orientation.Horizontal)
        self.pitch_slider.setRange(75, 160)
        self.pitch_slider.setValue(int(float(self.cfg.get('tts_pitch', 1.25)) * 100))
        self.pitch_slider.valueChanged.connect(self._on_pitch_changed)
        pitch_box.addLayout(pitch_header)
        pitch_box.addWidget(self.pitch_slider)
        tuning_layout.addLayout(pitch_box)
        
        # Speed control
        speed_box = QVBoxLayout()
        speed_box.setSpacing(4)
        speed_header = QHBoxLayout()
        speed_title = QLabel("Velocidade")
        speed_title.setObjectName("cardDetail")
        self.speed_val_label = QLabel(f"{int(float(self.cfg.get('tts_speed', 1.0))*100)}%")
        self.speed_val_label.setObjectName("cardDetail")
        speed_header.addWidget(speed_title)
        speed_header.addStretch(1)
        speed_header.addWidget(self.speed_val_label)
        
        self.speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.speed_slider.setRange(70, 140)
        self.speed_slider.setValue(int(float(self.cfg.get('tts_speed', 1.0)) * 100))
        self.speed_slider.valueChanged.connect(self._on_speed_changed)
        speed_box.addLayout(speed_header)
        speed_box.addWidget(self.speed_slider)
        tuning_layout.addLayout(speed_box)
        
        layout.addLayout(tuning_layout)

        self.voice_preview_button = QPushButton("▶  Baixar e ouvir prévia"); self.voice_preview_button.setObjectName("previewVoice")
        self.voice_preview_button.clicked.connect(lambda: self._preview_voice(self._selected_voice))
        preview_error_signal = getattr(self.speaker, "preview_error", None)
        if preview_error_signal is not None:
            preview_error_signal.connect(self._voice_preview_error, Qt.ConnectionType.QueuedConnection)
        layout.addWidget(self.voice_preview_button, 0, Qt.AlignmentFlag.AlignHCenter)
        self.voice_download_progress = QProgressBar(); self.voice_download_progress.setTextVisible(True); self.voice_download_progress.setFormat("Baixando modelo · %p%"); self.voice_download_progress.setFixedHeight(16); self.voice_download_progress.hide()
        layout.addWidget(self.voice_download_progress)
        self.voice_status = QLabel("Escolha um perfil e ouça a prévia local. O download só acontece quando você pede para ouvir.")
        self.voice_status.setObjectName("cardDetail")
        self.voice_status.setWordWrap(True)
        layout.addWidget(self.voice_status)
        self.voice_license = QLabel("")
        self.voice_license.setObjectName("cardDetail")
        self.voice_license.setWordWrap(True)
        layout.addWidget(self.voice_license)
        self.preview_phrase = QLabel()
        self.preview_phrase.setObjectName("cardDetail")
        self.preview_phrase.setWordWrap(True)
        self.preview_phrase.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.preview_phrase)
        self._update_preview_phrase()
        self._refresh_voice_carousel()
        self._position_voice_orbs()
        self._refresh_tts_choices()
        self._add_page(frame)

    def _feedback_card(self, index):
        key, title, detail, signature_text = FEEDBACK_THEMES[index % len(FEEDBACK_THEMES)]
        card = QFrame(self.feedback_stage)
        card.setObjectName("choiceCard")
        card.setProperty("selected", False)
        box = QVBoxLayout(card)
        box.setContentsMargins(14, 10, 14, 10)
        box.setSpacing(3)
        signature = QLabel(signature_text)
        signature.setObjectName("soundSignature")
        signature.setAlignment(Qt.AlignmentFlag.AlignCenter)
        box.addWidget(signature)
        heading = QLabel(title)
        heading.setObjectName("cardTitle")
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        box.addWidget(heading)
        caption = QLabel(detail)
        caption.setObjectName("cardDetail")
        caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        box.addWidget(caption)
        sequence = QLabel("ENTRADA   →   SAÍDA")
        sequence.setObjectName("soundSequence")
        sequence.setAlignment(Qt.AlignmentFlag.AlignCenter)
        box.addWidget(sequence)
        card._feedback_key = key
        return card

    def _build_feedback(self):
        frame, layout = self._panel(
            "Assinatura sonora",
            "Cada par tem uma entrada e uma saída diferentes. Percorra, ouça a sequência e escolha a que combina com a sua Aurora.",
        )
        self._feedback_choices = tuple(item[:3] for item in FEEDBACK_THEMES)
        self._feedback_index = next((i for i, item in enumerate(self._feedback_choices)
                                     if item[0] == self._selected_feedback), 0)
        self._feedback_step_pending = False
        self._feedback_transition_group = None
        self.feedback_stage = _OrbCarouselStage()
        self.feedback_stage.setFixedHeight(166)
        count = len(self._feedback_choices)
        indexes = ((self._feedback_index - 1) % count,
                   self._feedback_index,
                   (self._feedback_index + 1) % count)
        self.feedback_side_left, self.feedback_center, self.feedback_side_right = (
            self._feedback_card(index) for index in indexes)
        self.feedback_cards = {card._feedback_key: card for card in
                               (self.feedback_side_left, self.feedback_center, self.feedback_side_right)}
        self.feedback_stage.resized.connect(self._position_feedback_cards)
        layout.addWidget(self.feedback_stage)

        controls = QHBoxLayout()
        controls.addStretch(1)
        self.feedback_prev = QPushButton("‹")
        self.feedback_prev.setObjectName("carouselArrow")
        self.feedback_prev.setFixedSize(42, 42)
        self.feedback_prev.clicked.connect(lambda: self._step_feedback(-1))
        controls.addWidget(self.feedback_prev)
        self.feedback_position = QLabel()
        self.feedback_position.setObjectName("carouselPosition")
        self.feedback_position.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.feedback_position.setMinimumWidth(72)
        controls.addWidget(self.feedback_position)
        self.feedback_next = QPushButton("›")
        self.feedback_next.setObjectName("carouselArrow")
        self.feedback_next.setFixedSize(42, 42)
        self.feedback_next.clicked.connect(lambda: self._step_feedback(1))
        controls.addWidget(self.feedback_next)
        controls.addStretch(1)
        layout.addLayout(controls)

        self.feedback_preview_button = QPushButton("▶   Ouvir entrada  ·  saída")
        self.feedback_preview_button.setObjectName("previewVoice")
        self.feedback_preview_button.clicked.connect(lambda: self._preview_feedback(self._selected_feedback))
        layout.addWidget(self.feedback_preview_button, 0, Qt.AlignmentFlag.AlignHCenter)
        self.feedback_status = QLabel("Par selecionado · pronto para prévia")
        self.feedback_status.setObjectName("cardDetail")
        self.feedback_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.feedback_status)
        self._refresh_feedback_carousel()
        self._position_feedback_cards()
        self._add_page(frame)

    def _feedback_geometries(self):
        width, height = self.feedback_stage.width(), self.feedback_stage.height()
        center_w, center_h = min(244, max(218, width // 3)), 144
        side_w, side_h = min(184, max(158, width // 4)), 116
        center_x = (width - center_w) // 2
        gap = max(16, (width - center_w - side_w * 2) // 2)
        side_y = (height - side_h) // 2
        center_y = (height - center_h) // 2
        return (QRectF(center_x - gap - side_w, side_y, side_w, side_h).toRect(),
                QRectF(center_x, center_y, center_w, center_h).toRect(),
                QRectF(center_x + center_w + gap, side_y, side_w, side_h).toRect())

    def _position_feedback_cards(self):
        if self._feedback_step_pending or not hasattr(self, "feedback_center"):
            return
        left, center, right = self._feedback_geometries()
        for card, rect, opacity in ((self.feedback_side_left, left, .64),
                                    (self.feedback_center, center, 1.0),
                                    (self.feedback_side_right, right, .64)):
            card.setGeometry(rect)
            self._set_feedback_card_role(card, side=opacity < .9, selected=opacity >= .9)
            card.show()

    @staticmethod
    def _set_feedback_card_role(card, *, side, selected=False):
        card.setProperty("side", bool(side))
        card.setProperty("selected", bool(selected))
        card.style().unpolish(card)
        card.style().polish(card)

    def _step_feedback(self, direction):
        if self._feedback_step_pending or direction not in (-1, 1):
            return
        count = len(self._feedback_choices)
        index = (self._feedback_index + direction) % count
        self._feedback_step_pending = True
        self.feedback_prev.setEnabled(False)
        self.feedback_next.setEnabled(False)
        self.feedback_preview_button.setEnabled(False)
        old_left, old_center, old_right = self.feedback_side_left, self.feedback_center, self.feedback_side_right
        left_rect, center_rect, right_rect = self._feedback_geometries()
        if direction > 0:
            incoming_index = (index + 1) % count
            shifts = ((old_left, left_rect.translated(-100, 0)),
                      (old_center, left_rect), (old_right, center_rect))
            incoming_rect, incoming_end, outgoing = right_rect.translated(100, 0), right_rect, old_left
        else:
            incoming_index = (index - 1) % count
            shifts = ((old_right, right_rect.translated(100, 0)),
                      (old_center, right_rect), (old_left, center_rect))
            incoming_rect, incoming_end, outgoing = left_rect.translated(-100, 0), left_rect, old_right
        entering = self._feedback_card(incoming_index)
        entering.setGeometry(incoming_rect)
        self._set_feedback_card_role(entering, side=True)
        entering.show()
        group = QParallelAnimationGroup(self)
        for card, destination in (*shifts, (entering, incoming_end)):
            move = QPropertyAnimation(card, b"geometry", group)
            move.setDuration(390); move.setStartValue(card.geometry()); move.setEndValue(destination)
            move.setEasingCurve(QEasingCurve.Type.OutCubic); group.addAnimation(move)
        self._feedback_transition_group = group
        group.finished.connect(lambda: self._complete_feedback_step(index, direction, old_left,
                                                                     old_center, old_right, entering, outgoing))
        group.start()
        self._play_sfx("select")

    def _complete_feedback_step(self, index, direction, old_left, old_center, old_right, entering, outgoing):
        if direction > 0:
            self.feedback_side_left, self.feedback_center, self.feedback_side_right = old_center, old_right, entering
        else:
            self.feedback_side_left, self.feedback_center, self.feedback_side_right = entering, old_left, old_center
        outgoing.deleteLater()
        self._feedback_index = index
        self._selected_feedback = self._feedback_choices[index][0]
        self.feedback_cards = {card._feedback_key: card for card in
                               (self.feedback_side_left, self.feedback_center, self.feedback_side_right)}
        self._feedback_step_pending = False
        self.feedback_prev.setEnabled(True); self.feedback_next.setEnabled(True)
        self.feedback_preview_button.setEnabled(True)
        self._refresh_feedback_carousel()
        group, self._feedback_transition_group = self._feedback_transition_group, None
        if group is not None: group.deleteLater()

    def _refresh_feedback_carousel(self):
        if not hasattr(self, "feedback_position"):
            return
        count = len(self._feedback_choices)
        self._selected_feedback = self._feedback_choices[self._feedback_index][0]
        self.feedback_position.setText(f"{self._feedback_index + 1:02d}  /  {count:02d}")
        for card in (self.feedback_side_left, self.feedback_center, self.feedback_side_right):
            selected = card is self.feedback_center
            self._set_feedback_card_role(card, side=not selected, selected=selected)
        self.feedback_status.setText(f"{self._feedback_choices[self._feedback_index][1]} · par selecionado")

    def _build_loading(self):
        frame, layout = self._panel("Preparando sua assistente…", "Montando seu perfil local e iniciando a Aurora com as escolhas que você fez.")
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
        self._add_page(frame)

    def _select_style(self, key):
        self._selected_style = key
        self._style_index = next((i for i, item in enumerate(BUBBLE_STYLES) if item[0] == key), 0)
        if hasattr(self, "style_orb"):
            self._refresh_style_carousel()
        if hasattr(self, "welcome_orb"):
            self.welcome_orb.set_style(key)
            self.welcome_style_title.setText(next(item[1] for item in BUBBLE_STYLES if item[0] == key))
        if hasattr(self, "voice_orb"):
            for voice_orb in (self.voice_side_left, self.voice_orb, self.voice_side_right):
                voice_orb.set_style(key)
        self._play_sfx("select")

    def _step_style(self, direction):
        if self._style_step_pending or direction not in (-1, 1):
            return
        count = len(BUBBLE_STYLES)
        next_index = (self._style_index + direction) % count
        if next_index == self._style_index:
            return

        self._style_step_pending = True
        self.style_prev.setEnabled(False)
        self.style_next.setEnabled(False)
        old_left, old_center, old_right = (
            self.style_side_left, self.style_orb, self.style_side_right)
        anchors = self._style_orb_positions()
        if direction > 0:
            incoming_index = (next_index + 1) % count
            incoming_slot = 2
            moving = (
                (old_left, QPoint(anchors[0].x() - 105, anchors[0].y()), .28, 0.0),
                (old_center, anchors[0], .50, .48),
                (old_right, anchors[1], 1.0, 1.0),
            )
        else:
            incoming_index = (next_index - 1) % count
            incoming_slot = 0
            moving = (
                (old_right, QPoint(anchors[2].x() + 105, anchors[2].y()), .28, 0.0),
                (old_center, anchors[2], .50, .48),
                (old_left, anchors[1], 1.0, 1.0),
            )

        entering = _AnimatedOrb(BUBBLE_STYLES[incoming_index][0], self.style_stage, opacity=0.0)
        entering.setFixedSize(166, 166)
        entering.displayScale = .38
        incoming_start = anchors[incoming_slot]
        incoming_offset = -76 if direction > 0 else 76
        entering.move(incoming_start.x() + incoming_offset, incoming_start.y())
        entering.show()
        moving = (*moving, (entering, incoming_start, .50, .48))

        group = QParallelAnimationGroup(self)
        for orb, target_pos, target_scale, target_opacity in moving:
            orb._motion_direction = -direction
            for prop, start_value, end_value in (
                (b"pos", orb.pos(), target_pos),
                (b"displayScale", orb.displayScale, target_scale),
                (b"displayOpacity", orb.displayOpacity, target_opacity),
            ):
                animation = QPropertyAnimation(orb, prop, group)
                animation.setDuration(360)
                animation.setStartValue(start_value)
                animation.setEndValue(end_value)
                animation.setEasingCurve(QEasingCurve.Type.OutCubic)
                group.addAnimation(animation)
            blur = QPropertyAnimation(orb, b"motionBlur", group)
            blur.setDuration(360)
            blur.setStartValue(0.0); blur.setEndValue(0.0); blur.setKeyValueAt(.42, .72)
            blur.setEasingCurve(QEasingCurve.Type.OutCubic)
            group.addAnimation(blur)
        self._style_transition_group = group
        group.finished.connect(lambda: self._complete_style_step(
            next_index, direction, old_left, old_center, old_right, entering, anchors))
        group.start()
        self._play_sfx("select")

    def _style_orb_positions(self):
        if not hasattr(self, "style_stage"):
            return (QPoint(), QPoint(), QPoint())
        return self._carousel_positions(self.style_stage)

    @staticmethod
    def _carousel_positions(stage):
        width, height = stage.width(), stage.height()
        center_x = (width - 166) // 2
        spacing = min(178, max(138, (width - 166) // 3))
        y = (height - 166) // 2
        return (QPoint(center_x - spacing, y), QPoint(center_x, y),
                QPoint(center_x + spacing, y))

    def _position_style_orbs(self):
        if self._style_step_pending or not hasattr(self, "style_orb"):
            return
        for orb, position in zip(
            (self.style_side_left, self.style_orb, self.style_side_right),
            self._style_orb_positions(),
        ):
            orb.move(position)

    def _complete_style_step(self, index, direction, old_left, old_center, old_right, entering, anchors):
        if direction > 0:
            old_left.deleteLater()
            self.style_side_left, self.style_orb, self.style_side_right = old_center, old_right, entering
        else:
            old_right.deleteLater()
            self.style_side_left, self.style_orb, self.style_side_right = entering, old_left, old_center

        self._style_index = index
        self._selected_style = BUBBLE_STYLES[index][0]
        for orb, position, scale, opacity in zip(
            (self.style_side_left, self.style_orb, self.style_side_right),
            anchors, (.50, 1.0, .50), (.48, 1.0, .48),
        ):
            orb.move(position)
            orb.displayScale = scale
            orb.displayOpacity = opacity
            orb.motionBlur = 0.0
        _, title, detail = BUBBLE_STYLES[index]
        self.style_title.setText(title)
        self.style_detail.setText(detail)
        self.style_position.setText(f"{index + 1:02d}  /  {len(BUBBLE_STYLES):02d}")
        if hasattr(self, "voice_orb"):
            for voice_orb in (self.voice_side_left, self.voice_orb, self.voice_side_right):
                voice_orb.set_style(self._selected_style)
        if hasattr(self, "welcome_orb"):
            self.welcome_orb.set_style(self._selected_style)
            self.welcome_style_title.setText(title)

        self._style_step_pending = False
        self.style_prev.setEnabled(True)
        self.style_next.setEnabled(True)
        group, self._style_transition_group = self._style_transition_group, None
        if group is not None:
            group.deleteLater()

    def _refresh_style_carousel(self):
        count = len(BUBBLE_STYLES); index = self._style_index % count
        key, title, detail = BUBBLE_STYLES[index]
        self._selected_style = key
        self.style_orb.set_style(key); self.style_title.setText(title); self.style_detail.setText(detail)
        self.style_position.setText(f"{index + 1:02d}  /  {count:02d}")
        self.style_side_left.set_style(BUBBLE_STYLES[(index - 1) % count][0])
        self.style_side_right.set_style(BUBBLE_STYLES[(index + 1) % count][0])
        self._position_style_orbs()

    def _step_voice(self, direction):
        if len(VOICES) < 2 or self._voice_step_pending or direction not in (-1, 1):
            return
        count = len(VOICES)
        index = (self._voice_index + direction) % count
        self._voice_step_pending = True
        self.voice_prev.setEnabled(False)
        self.voice_next.setEnabled(False)
        self.voice_preview_button.setEnabled(False)
        old_left, old_center, old_right = self.voice_side_left, self.voice_orb, self.voice_side_right
        old_left_name, old_center_name, old_right_name = self.voice_name_left, self.voice_title, self.voice_name_right
        anchors = self._carousel_positions(self.voice_stage)
        label_anchors = tuple(QPoint(point.x()+14, self.voice_stage.height()-27) for point in anchors)
        if direction > 0:
            incoming_index, incoming_slot = (index+1) % count, 2
            moving = ((old_left, QPoint(anchors[0].x()-105, anchors[0].y()), .28, 0.0),
                      (old_center, anchors[0], .50, .45), (old_right, anchors[1], 1.0, 1.0))
            name_moving = ((old_left_name, QPoint(label_anchors[0].x()-105, label_anchors[0].y())),
                           (old_center_name, label_anchors[0]), (old_right_name, label_anchors[1]))
        else:
            incoming_index, incoming_slot = (index-1) % count, 0
            moving = ((old_right, QPoint(anchors[2].x()+105, anchors[2].y()), .28, 0.0),
                      (old_center, anchors[2], .50, .45), (old_left, anchors[1], 1.0, 1.0))
            name_moving = ((old_right_name, QPoint(label_anchors[2].x()+105, label_anchors[2].y())),
                           (old_center_name, label_anchors[2]), (old_left_name, label_anchors[1]))

        entering = _AnimatedOrb(self._selected_style, self.voice_stage, opacity=0.0)
        entering.setFixedSize(166, 166); entering.displayScale = .38
        incoming_start = anchors[incoming_slot]
        entering.move(incoming_start.x()+(-76 if direction > 0 else 76), incoming_start.y())
        entering.show()
        moving = (*moving, (entering, incoming_start, .50, .45))
        incoming_name = QLabel(VOICES[incoming_index].name, self.voice_stage)
        incoming_name.setObjectName("voiceCarouselSideName")
        incoming_name.setAlignment(Qt.AlignmentFlag.AlignCenter); incoming_name.setFixedSize(138, 24)
        incoming_name.move(label_anchors[incoming_slot].x()+(-76 if direction > 0 else 76), label_anchors[incoming_slot].y())
        incoming_name.show()

        group = QParallelAnimationGroup(self)
        for orb, target_pos, target_scale, target_opacity in moving:
            orb._motion_direction = -direction
            for prop, start_value, end_value in ((b"pos", orb.pos(), target_pos),
                                                  (b"displayScale", orb.displayScale, target_scale),
                                                  (b"displayOpacity", orb.displayOpacity, target_opacity)):
                animation = QPropertyAnimation(orb, prop, group)
                animation.setDuration(360); animation.setStartValue(start_value); animation.setEndValue(end_value)
                animation.setEasingCurve(QEasingCurve.Type.OutCubic); group.addAnimation(animation)
            blur = QPropertyAnimation(orb, b"motionBlur", group)
            blur.setDuration(360); blur.setStartValue(0.0); blur.setEndValue(0.0); blur.setKeyValueAt(.42, .72)
            blur.setEasingCurve(QEasingCurve.Type.OutCubic); group.addAnimation(blur)
        for label, target_pos in (*name_moving, (incoming_name, label_anchors[incoming_slot])):
            animation = QPropertyAnimation(label, b"pos", group)
            animation.setDuration(360); animation.setStartValue(label.pos()); animation.setEndValue(target_pos)
            animation.setEasingCurve(QEasingCurve.Type.OutCubic); group.addAnimation(animation)
        self._voice_transition_group = group
        group.finished.connect(lambda: self._complete_voice_carousel_step(
            index, direction, old_left, old_center, old_right, entering,
            old_left_name, old_center_name, old_right_name, incoming_name, anchors, label_anchors))
        group.start()
        self._play_sfx("select")

    def _complete_voice_carousel_step(self, index, direction, old_left, old_center, old_right,
                                      entering, old_left_name, old_center_name, old_right_name,
                                      incoming_name, anchors, label_anchors):
        if direction > 0:
            old_left.deleteLater(); old_left_name.deleteLater()
            self.voice_side_left, self.voice_orb, self.voice_side_right = old_center, old_right, entering
            self.voice_name_left, self.voice_title, self.voice_name_right = old_center_name, old_right_name, incoming_name
        else:
            old_right.deleteLater(); old_right_name.deleteLater()
            self.voice_side_left, self.voice_orb, self.voice_side_right = entering, old_left, old_center
            self.voice_name_left, self.voice_title, self.voice_name_right = incoming_name, old_left_name, old_center_name
        self._voice_index = index
        for orb, position, scale, opacity in zip(
            (self.voice_side_left, self.voice_orb, self.voice_side_right),
            anchors, (.50, 1.0, .50), (.45, 1.0, .45)):
            orb.move(position); orb.displayScale = scale; orb.displayOpacity = opacity; orb.motionBlur = 0.0
        for label, position in zip((self.voice_name_left, self.voice_title, self.voice_name_right), label_anchors):
            label.move(position)
        self._style_voice_name_roles()
        self._refresh_voice_carousel()
        self._refresh_tts_choices()
        self._voice_step_pending = False
        self.voice_prev.setEnabled(True)
        self.voice_next.setEnabled(True)
        self.voice_preview_button.setEnabled(True)
        group, self._voice_transition_group = self._voice_transition_group, None
        if group is not None:
            group.deleteLater()

    def _position_voice_orbs(self):
        if not hasattr(self, "voice_orb") or self._voice_step_pending:
            return
        cx = (self.voice_stage.width() - self.voice_orb.width()) // 2
        cy = (self.voice_stage.height() - self.voice_orb.height() - 20) // 2
        self.voice_orb.move(cx, max(0, cy))
        self.voice_title.move((self.voice_stage.width() - self.voice_title.width()) // 2, self.voice_stage.height() - 26)

    def _refresh_voice_carousel(self):
        if not hasattr(self, "voice_orb"):
            return
        voice = VOICES[self._voice_index % len(VOICES)]
        self._selected_voice = voice.key
        self._selected_tts_engine = voice.engine
        self.voice_orb.set_style(self._selected_style)
        self.voice_title.setText(voice.name)
        self.voice_detail.setText("Piper VITS · 100% local · ajuste o tom e a velocidade abaixo")
        self.voice_license.setText(voice.license_note)
        self.voice_preview_button.setText("▶  Ouvir prévia" if voice_available(voice.key) else "↓  Baixar e ouvir prévia")

    def _refresh_tts_choices(self):
        if not hasattr(self, "voice_preview_button"):
            return
        selected = next((voice for voice in VOICES if voice.key == self._selected_voice), VOICES[0])
        self.voice_license.setText(selected.license_note)
        self.voice_preview_button.setText("▶  Ouvir prévia" if voice_available(selected.key) else "↓  Baixar e ouvir prévia")
        if voice_available(selected.key):
            self.voice_status.setText("Voz Faber pronta · Síntese em ~0.4s local via CPU.")
        else:
            self.voice_status.setText("Voz local · o modelo é instalado apenas quando você pede a prévia.")

    def _preview_feedback(self, theme, direction=None):
        entry = self._feedback_sfx.get(f"{theme}:entrada")
        exit_ = self._feedback_sfx.get(f"{theme}:saida")
        if not entry or not exit_ or not entry.source().isValid() or not exit_.source().isValid():
            self.feedback_status.setText("Prévia indisponível")
            return
        for effect in self._feedback_sfx.values(): effect.stop()
        if direction == "entrada":
            self.feedback_status.setText("Entrada…")
            entry.play()
            return
        if direction == "saida":
            self.feedback_status.setText("Saída…")
            exit_.play()
            return
        self.feedback_status.setText("Entrada…")
        entry.play()
        def play_exit():
            self.feedback_status.setText("Saída…")
            exit_.play()
        gap_ms = {"boreal": 980, "pulse": 800, "void": 1080,
                  "prisma": 900, "marea": 980, "lumen": 900,
                  "aether": 1080, "quasar": 880, "ember": 1020}.get(theme, 900)
        QTimer.singleShot(gap_ms, play_exit)

    def _preview_name(self):
        return "Aurora" if self.default_name.isChecked() else (self.assistant_name.text().strip() or "Aurora")

    def _update_preview_phrase(self, *_args):
        phrase = f'“Olá, eu sou {self._preview_name()}. Estou pronta para ajudar.”'
        label = getattr(self, "preview_phrase", None)
        if label is not None:
            label.setText(f"Texto da prévia: {phrase}")

    def _assistant_name_changed(self, *_args):
        self._update_preview_phrase()
        self._refresh_rail_preview()
        if self._wake_recordings or self._wake_profile:
            self._wake_recordings.clear()
            self._wake_profile = None
            self._needs_training = False
            if hasattr(self, "wake_training_progress"):
                self.wake_training_progress.setValue(0)
                self.wake_training_status.setText("O nome mudou. As amostras anteriores foram descartadas; grave o novo nome.")
                self.wake_training_button.setText("Gravar amostra 1 de 4")

    def _preview_voice(self, voice):
        if voice != self._selected_voice:
            self._voice_index = next((i for i, entry in enumerate(VOICES) if entry.key == voice), self._voice_index)
            self._selected_voice = voice
            selected = next((entry for entry in VOICES if entry.key == voice), VOICES[0])
            self._selected_tts_engine = selected.engine
            self._refresh_voice_carousel()
        item = next((entry for entry in VOICES if entry.key == voice), None)
        if item is None:
            return
        if not voice_available(voice):
            worker = getattr(self, "_voice_download_worker", None)
            if worker is not None and worker.isRunning():
                self.voice_status.setText("Aguarde o download da voz selecionada terminar.")
                return
            self.voice_status.setText(f"Baixando apenas o modelo local de {item.name}. A transferência pode ser retomada se a rede cair.")
            self.voice_download_progress.setRange(0, 100)
            self.voice_preview_button.setEnabled(False)
            self.voice_download_progress.setValue(0); self.voice_download_progress.show()
            self._voice_download_worker = _VoiceDownload(voice)
            self._voice_download_worker.progress.connect(self._voice_download_progress)
            self._voice_download_worker.finished_voice.connect(self._voice_downloaded)
            self._voice_download_worker.start()
            return
        self._play_voice_preview(item)

    def _voice_downloaded(self, voice, error):
        self.voice_preview_button.setEnabled(True)
        self.voice_download_progress.hide()
        self._refresh_tts_choices()
        if error:
            self.voice_status.setText(f"Não consegui baixar essa voz: {error}")
            return
        item = next(entry for entry in VOICES if entry.key == voice)
        self._play_voice_preview(item)

    def _voice_preview_error(self, voice, error_type):
        item = next((entry for entry in VOICES if entry.key == voice), None)
        label = item.name if item else "selecionada"
        self.voice_preview_button.setEnabled(True)
        self.voice_status.setText(
            f"A prévia de {label} falhou ({error_type}). A Aurora continua aberta; tente outra voz ou consulte o log local."
        )

    def _voice_download_progress(self, filename, done, total):
        if total > 0:
            self.voice_download_progress.setRange(0, 100)
            self.voice_download_progress.setValue(min(100, int(done * 100 / total)))
            size = f"{done / (1024 * 1024):.1f} / {total / (1024 * 1024):.1f} MB"
            self.voice_status.setText(f"Baixando {filename} · {size}")
        else:
            self.voice_download_progress.setRange(0, 0)
            self.voice_status.setText(f"Baixando {filename}…")

    def _on_pitch_changed(self, value):
        self.pitch_val_label.setText(f"{value}%")

    def _on_speed_changed(self, value):
        self.speed_val_label.setText(f"{value}%")

    def _play_voice_preview(self, item):
        interrupt = getattr(self.speaker, "interrupt", None)
        if callable(interrupt):
            interrupt()
        self.voice_status.setText(f"Gerando prévia local de {item.name}…")
        pitch = float(self.pitch_slider.value()) / 100.0 if hasattr(self, "pitch_slider") else None
        speed = float(self.speed_slider.value()) / 100.0 if hasattr(self, "speed_slider") else None
        self.speaker.say_with_voice(
            f"Olá, eu sou {self._preview_name()}. Estou pronta para ajudar.",
            item.key,
            pitch=pitch,
            speed=speed,
        )
        self._play_sfx("select")

    def _center(self):
        screen = self.screen() or __import__("PySide6.QtWidgets", fromlist=["QApplication"]).QApplication.primaryScreen()
        if screen:
            self.move(screen.availableGeometry().center() - self.rect().center())

    def showEvent(self, event):
        super().showEvent(event)
        self._apply_system_theme()

    def done(self, result):
        for worker in (getattr(self, "_voice_download_worker", None), getattr(self, "_name_worker", None), getattr(self, "_wake_worker", None)):
            if worker is not None and worker.isRunning():
                worker.requestInterruption()
                worker.wait(2500)
        super().done(result)

    def _set_page(self, page, animated=True):
        previous = self._current_page
        if self._transition_group is not None:
            self._transition_group.stop()
            self._finish_page_transition()
        old_page = self.stack.widget(previous) if previous != page else None
        self._current_page = page
        if page == 5 and hasattr(self, "voice_orb"):
            # Re-apply the style selected on the preceding page whenever the
            # voice page opens or is revisited with Back.
            for voice_orb in (self.voice_side_left, self.voice_orb, self.voice_side_right):
                voice_orb.set_style(self._selected_style)
            self._voice_step_pending = False
            self.voice_preview_button.setEnabled(True)
            self.voice_prev.setEnabled(True)
            self.voice_next.setEnabled(True)
        self.stack.setCurrentIndex(page)
        route = [0, 1, 2] + ([3] if self._needs_training else []) + [4, 5, 6]
        self._route_pages = route
        labels = {0: "Boas-vindas", 1: "Seu perfil", 2: "Conversa", 3: "Ativação",
                  4: "Sua bolha", 5: "Sua voz", 6: "Seus sons"}
        page_position = route.index(page) if page in route else len(route) - 1
        self.back_button.setVisible(page_position > 0 and page < 7)
        self.step_label.setText(
            f"ETAPA {page_position + 1:02d}  ·  {labels.get(page, 'PREPARAÇÃO').upper()}"
            if page < 7 else "SALVANDO SUAS ESCOLHAS NESTE COMPUTADOR"
        )
        steps = len(route) - 1
        progress_value = page_position
        self.page_progress.setRange(0, steps)
        progress_value = min(steps, progress_value)
        if animated:
            if self._progress_animation is not None:
                self._progress_animation.stop()
                self._progress_animation.deleteLater()
            animation = QPropertyAnimation(self.page_progress, b"value", self)
            animation.setDuration(340)
            animation.setStartValue(self.page_progress.value())
            animation.setEndValue(progress_value)
            animation.setEasingCurve(QEasingCurve.Type.OutCubic)
            self._progress_animation = animation
            animation.start()
        else:
            self.page_progress.setValue(progress_value)
        self.progress_counter.setText(f"{min(progress_value + 1, len(route)):02d} / {len(route):02d}")
        for step_page, (row, number, _caption) in self._step_rows.items():
            row.setVisible(step_page != 3 or self._needs_training)
            current = page == step_page
            complete = step_page in route and (page == 7 or (page < 7 and route.index(step_page) < page_position))
            row.setProperty("current", current)
            row.setProperty("complete", complete)
            number.setProperty("current", current)
            number.setProperty("complete", complete)
            step_number = route.index(step_page) + 1 if step_page in route else step_page + 1
            number.setText("✓" if complete else ("✦" if step_page == 0 else f"{step_number:02d}"))
            for widget in (row, number):
                widget.style().unpolish(widget)
                widget.style().polish(widget)
        self.next_button.setVisible(page < 7)
        self.next_button.setText({0: "Começar", 6: "Finalizar"}.get(page, "Próximo"))
        self.next_button.setEnabled(True)
        self._refresh_rail_preview()
        if animated:
            new_page = self.stack.currentWidget()
            if old_page is not None and new_page is not old_page:
                direction = 1 if page > previous else -1
                width = max(1, self.stack.width())
                old_page.move(0, 0)
                old_page.show()
                old_page.lower()
                new_page.move(direction * width, 0)
                new_page.show()
                new_page.raise_()
                group = QParallelAnimationGroup(self)
                for widget, start, end in (
                    (old_page, QPoint(0, 0), QPoint(-direction * width, 0)),
                    (new_page, QPoint(direction * width, 0), QPoint(0, 0)),
                ):
                    slide = QPropertyAnimation(widget, b"pos", group)
                    slide.setDuration(340)
                    slide.setStartValue(start)
                    slide.setEndValue(end)
                    slide.setEasingCurve(QEasingCurve.Type.OutCubic)
                    group.addAnimation(slide)
                self._transition_group = group
                self._transition_old_page = old_page
                self._transition_new_page = new_page
                group.finished.connect(self._finish_page_transition)
                group.start()
            self._play_sfx("step")

    def _finish_page_transition(self):
        old_page, new_page = self._transition_old_page, self._transition_new_page
        if old_page is not None:
            old_page.hide()
        if new_page is not None:
            new_page.move(0, 0)
            new_page.show()
            new_page.raise_()
        group, self._transition_group = self._transition_group, None
        self._transition_old_page = None
        self._transition_new_page = None
        if group is not None:
            group.deleteLater()

    def _set_name_checked(self, name, ok, message, needs_training=False):
        self.name_note.setText(message)
        if ok and name == self.assistant_name.text().strip():
            self.next_button.setEnabled(True)
            self._needs_training = False
            self._set_page(2)
        elif needs_training and name == self.assistant_name.text().strip():
            self.next_button.setEnabled(True)
            self._needs_training = True
            self._set_page(2)
        else:
            # An unavailable/corrupt model is an actionable setup error, not
            # evidence that the requested name needs acoustic enrollment.
            self.next_button.setEnabled(True)

    def _capture_wake_sample(self):
        if self._wake_worker is not None and self._wake_worker.isRunning():
            return
        if len(self._wake_recordings) >= 4:
            return
        self.wake_training_button.setEnabled(False)
        self.wake_training_status.setText(f"Gravando… diga ‘{self._preview_name()}’ uma vez, sem completar com outra frase.")
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
            self.wake_training_progress.setValue(count)
            self.wake_training_button.setText(f"Gravar amostra {count + 1} de 4")
            self.wake_training_button.setEnabled(True)
            return
        self._wake_recordings.append(bytes(pcm))
        count = len(self._wake_recordings)
        self.wake_training_progress.setValue(count)
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
            self._set_page(2)
        elif self._current_page == 2:
            self._set_page(3 if self._needs_training else 4)
        elif self._current_page == 3:
            if not self._wake_profile:
                self.wake_training_status.setText("Grave as quatro amostras antes de continuar.")
                return
            self._set_page(4)
        elif self._current_page in (0, 2, 4):
            self._set_page(self._current_page + 1)
        elif self._current_page == 5:
            selected_item = next((v for v in VOICES if v.key == self._selected_voice), None)
            if selected_item and not voice_runtime_available(self._selected_voice):
                self.voice_status.setText("O runtime desta voz não está instalado. Execute setup-voice.sh e tente novamente.")
                return
            if selected_item and not voice_available(self._selected_voice):
                self.voice_status.setText("Ouça/baixe a voz selecionada antes de finalizar. Nenhum modelo será baixado automaticamente.")
                return
            self._set_page(6)
        elif self._current_page == 6:
            self._apply()

    def back(self):
        if self._current_page > 0:
            previous = self._current_page - 1
            if previous == 3 and not self._needs_training:
                previous = 2
            self._set_page(previous)

    def _apply(self):
        voice = getattr(self, "_selected_voice", str(self.cfg.get("tts_voice", "pt_BR-faber-medium")))
        self.result_settings = {
            "user_name": " ".join(self.user_name.text().split())[:80],
            "profile_configured": True,
            "assistant_name": "Aurora" if self.default_name.isChecked() else " ".join(self.assistant_name.text().split())[:80],
            "assistant_personality": str(self.personality_choice.currentData() or "companion"),
            "conversation_tone": int(self.tone_slider.value()),
            "response_detail": str(self.detail_choice.currentData() or "balanced"),
            "custom_instructions": " ".join(self.custom_instructions.text().split())[:240],
            "wake_profile": self._wake_profile if self._needs_training else None,
            "bubble_style": self._selected_style,
            "tts_voice": voice or self.cfg.get("tts_voice", "pt_BR-faber-medium"),
            "tts_engine": self._selected_tts_engine,
            "tts_pitch": round(float(self.pitch_slider.value()) / 100.0, 2) if hasattr(self, "pitch_slider") else 1.25,
            "tts_speed": round(float(self.speed_slider.value()) / 100.0, 2) if hasattr(self, "speed_slider") else 1.0,
            "feedback_theme": self._selected_feedback,
            "onboarding_pending": False,
            "onboarding_boot_id": "",
        }
        self._set_page(7)
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

