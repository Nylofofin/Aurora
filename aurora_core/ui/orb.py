from __future__ import annotations

from PySide6.QtCore import Qt, QObject, Signal, QTimer, QPoint, QRectF, QUrl, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QColor, QSurfaceFormat
from PySide6.QtQuickWidgets import QQuickWidget
from PySide6.QtWidgets import QApplication
import sys
from ..config import APP_DIR, settings_save

class AuroraOrb(QObject):
    start_voice=Signal(); quit_requested=Signal(); hide_requested=Signal(); hidden=Signal()
    def __init__(self,cfg):
        super().__init__(); self.cfg=cfg; self.anchor=QRectF(0,0,136,136).toRect(); self.mode='hidden'; self.hiding=False; self.visibility_generation=0; self.visibility_attempts=0
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
        self.root.setProperty('entranceActive',False)
        if not self.view.isVisible():
            # Never depend on the compositor's window-opacity animation to
            # make the orb visible; spring scale and ripple supply the entrance.
            self.view.setGeometry(self.anchor); self.root.setProperty('revealScale',.68); self.view.setWindowOpacity(1.0)
            self.view.show(); self.view.raise_()
            self.root.setProperty('entranceActive',True)
            self.scale_anim.setStartValue(.68); self.scale_anim.setEndValue(1.0); self.scale_anim.start()
        else:
            self.root.setProperty('revealScale',1.0); self.view.setWindowOpacity(1.0); self.view.setGeometry(self.anchor); self.view.raise_()
        # XWayland can acknowledge show() before Mutter has exposed the
        # surface. Re-raise briefly until exposure so the wake sound and
        # floating orb cannot drift apart during compositor handoff.
        for delay in (0,80,180,360):
            QTimer.singleShot(delay,lambda g=generation:self._ensure_exposed(g))
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
        self.root.setProperty('entranceActive',False)
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
    def hide(self): self.hiding=True; self.view.hide(); self.root.setProperty('motionEnabled',False)
    def show(self): self.hiding=False; self.view.show(); self.view.raise_()
    def raise_(self): self.view.raise_()
    def move(self,x,y):
        self._drag_moved(x,y)
