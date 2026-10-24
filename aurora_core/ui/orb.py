# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from PySide6.QtCore import Qt, QObject, Signal, QTimer, QPoint, QRectF, QUrl, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QColor, QSurfaceFormat
from PySide6.QtQuickWidgets import QQuickWidget
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QPushButton, QVBoxLayout
import sys
from ..config import APP_DIR, settings_save

class AuroraOrb(QObject):
    start_voice=Signal(); quit_requested=Signal(); hide_requested=Signal(); hidden=Signal(); error_report_requested=Signal()
    def __init__(self,cfg):
        super().__init__(); self.cfg=cfg; self.anchor=QRectF(0,0,136,136).toRect(); self.mode='hidden'; self.hiding=False; self.visibility_generation=0; self.visibility_attempts=0; self._completion_pulse_generation=0
        # Embed Quick in a translucent QWidget top-level. QQuickView's scene
        # rendered in its FBO but XWayland returned a black native surface on
        # this host; QQuickWidget paints the same QML into the composited
        # backing store while retaining the always-on-top desktop window.
        self.view=QQuickWidget(); self.view.setWindowFlags(Qt.WindowType.Window|Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowStaysOnTopHint)
        self.view.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.view.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        surface=QSurfaceFormat(); surface.setSamples(4); surface.setAlphaBufferSize(8); self.view.setFormat(surface)
        self.view.setClearColor(QColor(0,0,0,0)); self.view.resize(136,136); self.view.setWindowTitle('Aurora')
        self.view.setResizeMode(QQuickWidget.ResizeMode.SizeRootObjectToView)
        self.view.setSource(QUrl.fromLocalFile(str(APP_DIR/'orb.qml')))
        if not self.view.rootObject():
            details='; '.join(error.toString() for error in self.view.errors())
            raise RuntimeError('Falha ao carregar a orb Qt Quick: '+details)
        self.root=self.view.rootObject()
        self.error_notice=QDialog(self.view,Qt.WindowType.Tool|Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowStaysOnTopHint)
        self.error_notice.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.error_notice.setFixedSize(276,104)
        self.error_notice.setStyleSheet('QDialog { background: #171923; border: 1px solid #695e83; border-radius: 16px; } QLabel { color: #f4efff; background: transparent; border: 0; font-size: 14px; font-weight: 600; } QPushButton { color: #ffffff; background: #7458ad; border: 0; border-radius: 9px; padding: 8px 18px; font-weight: 600; } QPushButton:hover { background: #876cc0; }')
        notice_layout=QVBoxLayout(self.error_notice); notice_layout.setContentsMargins(16,12,16,12); notice_layout.setSpacing(9)
        self.error_notice_label=QLabel('Aurora encontrou um erro interno.')
        self.error_notice_label.setWordWrap(True)
        self.error_report_button=QPushButton('Reportar')
        notice_layout.addWidget(self.error_notice_label)
        notice_layout.addWidget(self.error_report_button,0,Qt.AlignmentFlag.AlignRight)
        self.error_report_button.clicked.connect(self.error_report_requested.emit)
        self.root.startVoice.connect(self.start_voice.emit)
        self.root.hideRequested.connect(self.hide_requested.emit)
        self.root.quitRequested.connect(self.quit_requested.emit)
        self.root.positionChanged.connect(self._dragged)
        self.root.dragMoved.connect(self._drag_moved)
        geo=QApplication.primaryScreen().availableGeometry(); self.view.move(geo.right()-153,geo.bottom()-153)
        self._keep_on_screen()
        self.anchor=QRectF(self.view.x(),self.view.y(),136,136).toRect()
        self.root.setProperty('windowX',self.view.x()); self.root.setProperty('windowY',self.view.y())
        self.scale_anim=QPropertyAnimation(self.root,b'revealScale',self.view); self.scale_anim.setDuration(520); self.scale_anim.setEasingCurve(QEasingCurve.Type.OutBack)
        self.opacity_anim=QPropertyAnimation(self.view,b'windowOpacity',self.view); self.opacity_anim.setDuration(260); self.opacity_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.scale_anim.finished.connect(self._animation_finished)
        self.opacity_anim.finished.connect(self._animation_finished)
    def _keep_on_screen(self):
        screen=QApplication.screenAt(QPoint(self.view.x()+68,self.view.y()+68)) or QApplication.primaryScreen()
        area=screen.availableGeometry()
        x=max(area.left(),min(self.view.x(),max(area.left(),area.right()-135)))
        y=max(area.top(),min(self.view.y(),max(area.top(),area.bottom()-135)))
        self.view.move(x,y)
        self.root.setProperty('windowX',x); self.root.setProperty('windowY',y)
        self.anchor=QRectF(x,y,136,136).toRect()
        position=[x,y]
        if self.cfg.get('bubble_position')!=position:
            self.cfg['bubble_position']=position
            settings_save(self.cfg)
    def _drag_moved(self,x,y):
        screen=QApplication.screenAt(QPoint(int(x)+68,int(y)+68)) or QApplication.primaryScreen(); area=screen.availableGeometry()
        x=max(area.left(),min(int(x),area.right()-135)); y=max(area.top(),min(int(y),area.bottom()-135))
        self.view.move(x,y); self.anchor=QRectF(x,y,136,136).toRect()
        self.root.setProperty('windowX',x); self.root.setProperty('windowY',y)
    def _dragged(self,x,y):
        self._drag_moved(x,y)
        self.cfg['bubble_position']=[self.view.x(),self.view.y()]; settings_save(self.cfg)
    def set_mode(self,mode):
        self.mode=mode; self.root.setProperty('mode',mode)
        if mode!='speaking': self.root.setProperty('speechPulse',0.0)
        if mode!='listening': self.root.setProperty('inputLevel',0.0)
    def set_input_level(self,level):
        if self.mode=='listening': self.root.setProperty('inputLevel',max(0.0,min(1.0,float(level))))
    def set_speech_level(self,level):
        # Queued word-boundary events can arrive after a sentence or cancellation.
        # Ignore them outside active playback so an old pulse cannot animate late.
        if self.mode=='speaking': self.root.setProperty('speechPulse',max(0.0,min(1.0,float(level))))
    def pulse_complete(self):
        self._completion_pulse_generation+=1; generation=self._completion_pulse_generation
        self.root.setProperty('completionPulse',0.0); self.root.setProperty('completionPulse',1.0)
        QTimer.singleShot(140,lambda g=generation:self.root.setProperty('completionPulse',0.0) if g==self._completion_pulse_generation else None)
    def reveal(self,mode='listening'):
        self.visibility_generation+=1; generation=self.visibility_generation; self.visibility_attempts=0
        self.hiding=False
        self.scale_anim.setDuration(520); self.scale_anim.setEasingCurve(QEasingCurve.Type.OutBack)
        self.set_mode(mode); self.scale_anim.stop(); self.opacity_anim.stop()
        # Each activation starts in the primary display's lower-right corner;
        # the user can drag it anywhere while it remains visible.
        area=QApplication.primaryScreen().availableGeometry()
        self.view.move(area.right()-153,area.bottom()-153)
        self._keep_on_screen()
        self.root.setProperty('motionEnabled',True)
        if not self.view.isVisible():
            # Never depend on the compositor's window-opacity animation to
            # make the orb visible; spring scale and ripple supply the entrance.
            self.view.setGeometry(self.anchor); self.root.setProperty('revealScale',.68); self.view.setWindowOpacity(1.0)
            self.view.show(); self.view.raise_()
            self.scale_anim.setStartValue(.68); self.scale_anim.setEndValue(1.0); self.scale_anim.start()
        else:
            self.root.setProperty('revealScale',1.0); self.view.setWindowOpacity(1.0); self.view.setGeometry(self.anchor); self.view.raise_()
        # XWayland can acknowledge show() before Mutter has exposed the
        # surface. Re-raise briefly until exposure so the wake sound and
        # floating orb cannot drift apart during compositor handoff.
        for delay in (0,80,180,360):
            QTimer.singleShot(delay,lambda g=generation:self._ensure_exposed(g))
    def show_error_notice(self,message='Aurora encontrou um erro interno.'):
        if self.view.isVisible(): self.set_mode('error')
        else: self.reveal('error')
        self.error_notice_label.setText(str(message)[:180])
        screen=QApplication.screenAt(QPoint(self.view.x()+68,self.view.y()+68)) or QApplication.primaryScreen()
        area=screen.availableGeometry()
        x=max(area.left(),min(self.view.x()+self.view.width()-self.error_notice.width(),area.right()-self.error_notice.width()+1))
        y=max(area.top(),self.view.y()-self.error_notice.height()-10)
        self.error_notice.move(x,y)
        self.error_notice.show(); self.error_notice.raise_()
    def set_error_notice_status(self,message): self.error_notice_label.setText(str(message)[:180])
    def clear_error_notice(self): self.error_notice.hide()
    def _ensure_exposed(self,generation):
        if generation!=self.visibility_generation or not self.view.isVisible(): return
        self.view.raise_()
        handle=self.view.windowHandle(); exposed=bool(handle and handle.isExposed())
        if not exposed and self.visibility_attempts<8:
            self.visibility_attempts+=1
            QTimer.singleShot(100,lambda g=generation:self._ensure_exposed(g))
        elif exposed or self.visibility_attempts:
            print(f'[orb] visible={self.view.isVisible()} exposed={exposed} opacity={self.view.windowOpacity():.2f} geometry={self.view.geometry().getRect()}',file=sys.stderr,flush=True)
    def dismiss(self):
        if not self.view.isVisible(): return
        self.hiding=True
        self.scale_anim.stop(); self.opacity_anim.stop()
        start=float(self.root.property('revealScale'))
        self.scale_anim.setStartValue(start); self.scale_anim.setEndValue(.70); self.scale_anim.setDuration(280); self.scale_anim.setEasingCurve(QEasingCurve.Type.InBack); self.scale_anim.start()
        self.opacity_anim.setStartValue(self.view.windowOpacity()); self.opacity_anim.setEndValue(0.0); self.opacity_anim.setDuration(260); self.opacity_anim.setEasingCurve(QEasingCurve.Type.InCubic); self.opacity_anim.start()
    def _animation_finished(self):
        if self.hiding and (self.view.windowOpacity()<.01 or float(self.root.property('revealScale'))<.90):
            self.hiding=False
            self.view.hide(); self.root.setProperty('motionEnabled',False); self.root.setProperty('revealScale',1.0); self.view.setWindowOpacity(1.0)
            self.hidden.emit()
    def frameGeometry(self): return self.view.frameGeometry()
    def isVisible(self): return self.view.isVisible()
    def hide(self): self.hiding=True; self.view.hide(); self.root.setProperty('motionEnabled',False); self.root.setProperty('inputLevel',0.0)
    def show(self): self.hiding=False; self.view.show(); self.view.raise_()
    def raise_(self): self.view.raise_()
    def move(self,x,y):
        self._drag_moved(x,y)
