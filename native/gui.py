"""Compact native Qt panel inspired by the supplied Keyfall screenshots."""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import random
import sys
import time

from PySide6.QtCore import Qt, QTimer, Signal, QRectF, QPointF, QEvent, QVariantAnimation, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QColor, QPainter, QPen, QLinearGradient, QPixmap, QPolygonF, QFont, QIcon
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QSlider, QDoubleSpinBox, QComboBox, QLineEdit, QFrame, QScrollArea,
    QFileDialog, QMessageBox, QSizePolicy, QGraphicsOpacityEffect)

from .gui_model import SettingsModel, SLIDERS
from .schema import load_profile
from .session import RuntimeSession
from .typography import configure_fonts, ui_font
from .hotkeys import MenuHotkey, capture_vk
from .version import __version__

BG, DARK, INK, MUTED, PINK = '#272234', '#201a2b', '#c5b5f6', '#9284ac', '#fc589b'
STYLE = '''
QWidget { background: #272234; color: #c5b5f6; font-family: 'Poppins'; font-size: 13px; }
QLabel { background: transparent; }
QPushButton { background: transparent; border: 0; padding: 4px; }
QPushButton:hover { color: white; }
QPushButton:focus { border: 1px solid #b49bf4; border-radius: 3px; }
QLineEdit, QComboBox { background: #201a2b; color: #e6ddef; border: 1px solid #655278; border-radius: 3px; padding: 4px 7px; }
QLineEdit:focus, QComboBox:focus { border-color: #b49bf4; }
QComboBox::drop-down { border: 0; width: 20px; }
QComboBox QAbstractItemView { background: #272234; color: #e6ddef; selection-background-color: #7150a2; }
QDoubleSpinBox { background: transparent; color: #eee7f6; border: 0; padding: 0; font-size: 12px; }
QSlider::groove:horizontal { height: 4px; background: #1e1929; border-radius: 2px; }
QSlider::handle:horizontal { background: #272234; border: 1px solid #bda6ff; width: 14px; height: 14px; margin: -6px 0; border-radius: 8px; }
QSlider::handle:horizontal:hover { background: #4b3c67; }
QScrollArea { border: 0; }
QScrollBar:vertical { width: 5px; background: #272234; }
QScrollBar::handle:vertical { background: #655278; border-radius: 2px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QToolTip { color: #eee7f6; background: #201a2b; border: 1px solid #655278; }
QPushButton:disabled { color: #82758f; }
'''


class IconButton(QPushButton):
    def __init__(self, icon):
        super().__init__()
        self.icon = icon

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor('#f1e8ff' if self.underMouse() else MUTED), 1.4))
        x, y = self.width()/2, self.height()/2
        if self.icon == 'close':
            p.drawLine(QPointF(x-3,y-3),QPointF(x+3,y+3))
            p.drawLine(QPointF(x-3,y+3),QPointF(x+3,y-3))
        elif self.icon == 'minimize':
            p.drawLine(QPointF(x-4,y),QPointF(x+4,y))
        else:
            p.drawArc(QRectF(x-4,y-4,8,8),20*16,290*16)
            p.drawLine(QPointF(x+4,y-4),QPointF(x+4,y))
            p.drawLine(QPointF(x+4,y),QPointF(x,y))
        if self.hasFocus():
            p.setPen(QPen(QColor(INK),1,Qt.PenStyle.DotLine))
            p.drawRect(1,1,self.width()-3,self.height()-3)


class Toggle(QPushButton):
    def __init__(self, checked=False, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.position = float(checked)
        self.motion = QVariantAnimation(self)
        self.motion.setDuration(160)
        self.motion.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.motion.valueChanged.connect(self.set_position)
        self.toggled.connect(self.animate_checked)
        self.setFixedSize(29, 23)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def blend(self, start, end):
        a, b = QColor(start), QColor(end)
        return QColor.fromRgbF(*(a.getRgbF()[i]*(1-self.position)+b.getRgbF()[i]*self.position for i in range(4)))

    def set_position(self, value):
        self.position = float(value)
        self.update()

    def setChecked(self, checked):
        super().setChecked(checked)
        # Model refresh intentionally blocks signals; visuals must still follow.
        if hasattr(self, 'motion'):
            self.animate_checked(checked)

    def animate_checked(self, checked):
        target = float(checked)
        if self.motion.endValue() == target and self.motion.state() == QVariantAnimation.State.Running:
            return
        self.motion.stop()
        if abs(self.position-target) < 0.001:
            self.set_position(target)
            return
        self.motion.setStartValue(self.position)
        self.motion.setEndValue(target)
        self.motion.start()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        track = QRectF(2, 5, 24, 12)
        painter.setPen(QPen(QColor(PINK), 1.5))
        painter.setBrush(self.blend(BG, PINK))
        painter.drawRoundedRect(track, 6, 6)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.blend('#9987ad', '#fff5fc'))
        painter.drawEllipse(QPointF(8+12*self.position, 11), 3, 3)
        if self.hasFocus():
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(INK), 1, Qt.PenStyle.DotLine))
            painter.drawRoundedRect(QRectF(.5, .5, 28, 22), 4, 4)


class FacetButton(QPushButton):
    def __init__(self, title, subtitle='', color='#9c6ce0', seed=3):
        super().__init__()
        self.caption, self.subtitle, self.color, self.seed = title, subtitle, color, seed
        self.selected = False
        self.hover_progress = 0.0
        self.hover_motion = QVariantAnimation(self)
        self.hover_motion.setDuration(140)
        self.hover_motion.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.hover_motion.valueChanged.connect(self.set_hover_progress)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(58 if subtitle else 26)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAccessibleName(title)

    def set_hover_progress(self, value):
        self.hover_progress = float(value)
        self.update()

    def animate_hover(self, target):
        self.hover_motion.stop()
        self.hover_motion.setStartValue(self.hover_progress)
        self.hover_motion.setEndValue(target)
        self.hover_motion.start()

    def enterEvent(self, event):
        self.animate_hover(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.animate_hover(0.0)
        super().leaveEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        base = QColor(self.color)
        if not self.isEnabled():
            base = base.darker(155)
        else:
            base = base.lighter(100+round(8*self.hover_progress))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(base)
        p.drawRoundedRect(self.rect(), 3, 3)
        p.save()
        from PySide6.QtGui import QPainterPath
        clip = QPainterPath(); clip.addRoundedRect(QRectF(self.rect()), 3, 3)
        p.setClipPath(clip)
        rng = random.Random(self.seed)
        for x in range(-20, self.width()+35, 27):
            for y in range(-20, self.height()+30, 24):
                shade = QColor(base).lighter(rng.randint(80, 130))
                p.setBrush(shade)
                p.drawPolygon(QPolygonF([QPointF(x,y), QPointF(x+35,y+12), QPointF(x+15,y+43)]))
        p.restore()
        if self.selected or self.hasFocus():
            p.setPen(QPen(QColor('#dab9ff'), 1.5))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(QRectF(1,1,self.width()-2,self.height()-2), 3, 3)
        p.setPen(QColor('#fff2ff'))
        font = ui_font(13 if self.subtitle else 9)
        p.setFont(font)
        p.drawText(QRectF(0,5 if self.subtitle else 0,self.width(),25 if self.subtitle else self.height()), Qt.AlignmentFlag.AlignCenter, self.caption)
        if self.subtitle:
            p.setPen(QColor('#dfcbe9'));p.setFont(ui_font(8))
            p.drawText(QRectF(0,31,self.width(),19), Qt.AlignmentFlag.AlignCenter, self.subtitle)


class Hero(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedHeight(104)
        self.image = QPixmap(str(Path(__file__).resolve().parent/'assets/banner.png'))
        self.status = 'READY'
        self.profile = 'Reference profile'

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor('#57425f'))
        if not self.image.isNull():
            # The reference banner includes a baked-in uppercase status badge.
            # Crop it out; only the live, lowercase status above is rendered.
            source = self.image.rect()
            source.setWidth(round(source.width()*.80))
            p.drawPixmap(self.rect(), self.image, source)
        gradient = QLinearGradient(0,0,0,self.height())
        gradient.setColorAt(0,QColor(20,12,28,15));gradient.setColorAt(.4,QColor(20,12,28,30));gradient.setColorAt(1,QColor(20,12,28,210))
        p.fillRect(self.rect(),gradient)
        p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor(32,26,43,220))
        p.drawRoundedRect(QRectF(self.width()-81,8,71,22),11,11)
        p.setPen(QColor('#fff4fc'));p.setFont(ui_font(8))
        p.drawText(QRectF(self.width()-81,8,71,22),Qt.AlignmentFlag.AlignCenter,self.status)
        p.setFont(ui_font(18));p.drawText(9,70,'CS2 · native workspace')
        p.setFont(ui_font(9));p.drawText(10,92,self.profile)


class SliderRow(QWidget):
    changed = Signal(str, float)
    reset_requested = Signal(str)

    def __init__(self, label, key, multiplier, low, high, decimals, suffix, value):
        super().__init__()
        self.key, self.multiplier = key, multiplier
        layout = QHBoxLayout(self);layout.setContentsMargins(0,0,0,0);layout.setSpacing(6)
        name = QLabel(label);name.setFixedWidth(88)
        self.value = QDoubleSpinBox();self.value.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        self.value.setDecimals(decimals);self.value.setRange(low,high);self.value.setSuffix(suffix)
        self.value.setFixedWidth(82);self.value.setKeyboardTracking(False)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.precision = 10**decimals
        self.slider.setRange(round(low*self.precision),round(high*self.precision))
        self.slider.setAccessibleName(label)
        reset = IconButton('reset');reset.setFixedSize(24,24);reset.setToolTip('Reset '+label)
        reset.setAccessibleName('Reset '+label);reset.clicked.connect(lambda: self.reset_requested.emit(key))
        layout.addWidget(name);layout.addWidget(self.value);layout.addWidget(self.slider,1);layout.addWidget(reset)
        self.setFixedHeight(28)
        self.slider.valueChanged.connect(self.on_slide)
        self.value.valueChanged.connect(self.on_value)
        self.set_value(value)

    def set_value(self, value):
        self.slider.blockSignals(True);self.value.blockSignals(True)
        displayed = value*self.multiplier
        self.value.setValue(displayed);self.slider.setValue(round(displayed*self.precision))
        self.slider.blockSignals(False);self.value.blockSignals(False)

    def on_slide(self, value):
        self.value.blockSignals(True);self.value.setValue(value/self.precision);self.value.blockSignals(False)
        self.changed.emit(self.key,value/self.precision/self.multiplier)

    def on_value(self, value):
        self.slider.blockSignals(True);self.slider.setValue(round(value*self.precision));self.slider.blockSignals(False)
        self.changed.emit(self.key,value/self.multiplier)


class ControlPanel(QWidget):
    def __init__(self, profile, config_dir, config_name='default'):
        super().__init__()
        self.profile_path = Path(profile)
        self.model = SettingsModel(config_dir, config_name)
        configure_fonts()
        QApplication.instance().setFont(ui_font(10))
        self.session = RuntimeSession()
        self.menu_hotkey = MenuHotkey()
        self.page, self.expanded = 'Aim', True
        self.drag_origin = None
        self.closing = False
        self.capture = None
        self.last_frame = 0
        self.sliders, self.toggles, self.combos, self.tab_buttons = {}, {}, {}, {}
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle('phantom — native control panel')
        self.setFixedWidth(440)
        self.setStyleSheet(STYLE)
        self.setFont(ui_font(10))
        self.setAccessibleName('Phantom native control panel')
        outer = QVBoxLayout(self);outer.setContentsMargins(0,0,0,0);outer.setSpacing(0)
        self.titlebar = QWidget();self.titlebar.setObjectName('titlebar');self.titlebar.setStyleSheet('#titlebar { background: #201a2b; }')
        title = QHBoxLayout(self.titlebar);title.setContentsMargins(11,0,8,0);title.setSpacing(7)
        assets = Path(__file__).resolve().parent/'assets'
        logo = QPixmap(str(assets/'phantom-icon.png'))
        app_icon = QIcon(str(assets/'phantom.ico'))
        if logo.isNull() or app_icon.isNull():
            raise RuntimeError('The bundled Phantom logo is missing or invalid. Reinstall the complete package.')
        self.setWindowIcon(app_icon)
        QApplication.instance().setWindowIcon(app_icon)
        self.logo_label = QLabel()
        self.logo_label.setAccessibleName('phantom logo')
        self.logo_label.setFixedSize(28,28)
        logo_small = logo.scaled(56,56,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation)
        logo_small.setDevicePixelRatio(2)
        self.logo_label.setPixmap(logo_small)
        self.logo_label.setToolTip('phantom')
        title.addWidget(self.logo_label);title.addWidget(QLabel('phantom v'+__version__));title.addStretch()
        minimize = IconButton('minimize');minimize.setFixedSize(32,32);minimize.setAccessibleName('Minimize');minimize.clicked.connect(self.showMinimized)
        close = IconButton('close');close.setFixedSize(27,32);close.setAccessibleName('Close');close.clicked.connect(self.close)
        title.addWidget(minimize);title.addWidget(close);self.titlebar.setFixedHeight(36)
        self.titlebar.mousePressEvent = self.drag_start;self.titlebar.mouseMoveEvent = self.drag_move
        outer.addWidget(self.titlebar)
        self.workspace = QWidget()
        columns = QHBoxLayout(self.workspace);columns.setContentsMargins(0,0,0,0);columns.setSpacing(0)
        self.overview = QWidget()
        overview_layout = QVBoxLayout(self.overview);overview_layout.setContentsMargins(0,0,0,0);overview_layout.setSpacing(0)
        columns.addWidget(self.overview)
        outer.addWidget(self.workspace,1)
        body = QWidget();body_layout = QVBoxLayout(body);body_layout.setContentsMargins(10,4,10,0);body_layout.setSpacing(0)
        self.hero = Hero();body_layout.addWidget(self.hero);body_layout.addSpacing(12)
        for spec in SLIDERS:
            self.add_slider(body_layout,*spec)
        body_layout.addSpacing(10)
        self.players = QLabel('—');self.config_label = QLabel(self.model.name);self.runtime_label = QLabel('Stopped')
        self.add_summary(body_layout,'Players read',self.players,'ESP overlay','esp')
        self.add_summary(body_layout,'Config',self.config_label,'Aim assist','aim')
        self.add_summary(body_layout,'Runtime',self.runtime_label,'Trigger','trigger')
        body_layout.addSpacing(11)
        tabs = QHBoxLayout();tabs.setSpacing(5)
        subtitles = {'Visuals':'Skeleton\nRadar · teams','Aim':'Priority bone\nSmoothing','Input':'Keybinds\nMovement','Configs':'Save · load\nProfiles'}
        for i, label in enumerate(subtitles):
            column = QVBoxLayout();column.setSpacing(0)
            button = FacetButton(label,color='#9562cd',seed=10+i);button.setFixedHeight(25);button.setMinimumHeight(25)
            button.clicked.connect(lambda checked=False, name=label:self.select_page(name))
            self.tab_buttons[label] = button;column.addWidget(button)
            sub = QLabel(subtitles[label]);sub.setAlignment(Qt.AlignmentFlag.AlignCenter);sub.setStyleSheet('color: #77628f; font-size: 10px;');sub.setFixedHeight(33)
            column.addWidget(sub);tabs.addLayout(column)
        body_layout.addLayout(tabs);overview_layout.addWidget(body);overview_layout.addStretch()
        morebar = QWidget();morebar.setStyleSheet('background: #201a2b;')
        morelayout = QHBoxLayout(morebar);morelayout.setContentsMargins(12,0,12,0)
        morelayout.addSpacing(85);morelayout.addStretch();self.more = QPushButton('Less');self.more.setFixedHeight(23);self.more.clicked.connect(self.toggle_more)
        morelayout.addWidget(self.more);morelayout.addStretch();self.menu_hint = QLabel();self.menu_hint.setStyleSheet('font-size: 9px; color: #b9809d;');morelayout.addWidget(self.menu_hint)
        overview_layout.addWidget(morebar)
        self.details = QWidget();self.details_layout = QVBoxLayout(self.details);self.details_layout.setContentsMargins(18,13,18,7);self.details_layout.setSpacing(5)
        self.details_scroll = QScrollArea();self.details_scroll.setWidgetResizable(True);self.details_scroll.setWidget(self.details);self.details_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.details_scroll.setStyleSheet('QScrollArea { border-left: 1px solid #3a304a; }')
        columns.addWidget(self.details_scroll,1)
        self.details_opacity = QGraphicsOpacityEffect(self.details)
        self.details_opacity.setOpacity(1.0)
        self.details.setGraphicsEffect(self.details_opacity)
        self.page_motion = QPropertyAnimation(self.details_opacity, b'opacity', self)
        self.page_motion.setDuration(180)
        self.page_motion.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.message = QLabel('Changes apply to the running session. Save keeps them on disk.');self.message.setWordWrap(True);self.message.setFixedHeight(39);self.message.setContentsMargins(18,0,18,0);self.message.setStyleSheet('font-size: 11px; color: #9284ac;')
        outer.addWidget(self.message)
        footer = QWidget();footer.setStyleSheet('background: #201a2b;');buttons = QHBoxLayout(footer);buttons.setContentsMargins(10,8,10,10);buttons.setSpacing(6)
        self.stop_button = FacetButton('Stop','Stop runtime','#357698',8);self.stop_button.setFixedWidth(133);self.stop_button.clicked.connect(self.stop_runtime)
        self.start_button = FacetButton('Start runtime','Native · foreground gated','#ba237b',22);self.start_button.clicked.connect(self.start_runtime)
        buttons.addWidget(self.stop_button);buttons.addWidget(self.start_button,1);outer.addWidget(footer)
        self.apply_timer = QTimer(self);self.apply_timer.setSingleShot(True);self.apply_timer.setInterval(100);self.apply_timer.timeout.connect(self.apply_settings)
        self.timer = QTimer(self);self.timer.setInterval(100);self.timer.timeout.connect(self.poll_runtime);self.timer.start()
        self.capture_timer = QTimer(self);self.capture_timer.setSingleShot(True);self.capture_timer.timeout.connect(self.cancel_capture)
        self.menu_timer = QTimer(self);self.menu_timer.setInterval(16);self.menu_timer.timeout.connect(self.poll_menu_hotkey);self.menu_timer.start()
        self.build_details();self.refresh();self.update_session_buttons()
        self.resize_panel()

    def poll_menu_hotkey(self):
        app = QApplication.instance()
        blocked = self.closing or self.capture is not None or app.activeModalWidget() is not None or app.activePopupWidget() is not None
        if self.menu_hotkey.poll(self.model.config.keys['menu_toggle'], blocked):
            self.toggle_menu()

    def toggle_menu(self):
        if self.closing:
            return
        if self.isVisible() and not self.isMinimized():
            self.hide()
        else:
            # Pause the child before displaying the menu, even if Windows declines
            # to grant keyboard focus. No game input should run behind the panel.
            self.session.set_menu_visible(True)
            self.showNormal();self.raise_();self.activateWindow()

    def showEvent(self,event):
        self.session.set_menu_visible(True)
        super().showEvent(event)

    def hideEvent(self,event):
        self.session.set_menu_visible(False)
        super().hideEvent(event)

    def changeEvent(self,event):
        if event.type() == QEvent.Type.WindowStateChange:
            self.session.set_menu_visible(not self.isMinimized() and self.isVisible())
        super().changeEvent(event)

    def drag_start(self,event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_origin = event.globalPosition().toPoint()-self.frameGeometry().topLeft()

    def drag_move(self,event):
        if event.buttons() & Qt.MouseButton.LeftButton and self.drag_origin is not None:
            self.move(event.globalPosition().toPoint()-self.drag_origin)

    def add_slider(self, layout, label, key, multiplier, low, high, decimals, suffix):
        row = SliderRow(label,key,multiplier,low,high,decimals,suffix,getattr(self.model.config,key))
        row.changed.connect(self.change);row.reset_requested.connect(self.reset_setting)
        self.sliders[key] = row;layout.addWidget(row)
        return row

    def add_summary(self,layout,label,value,toggle_label,key):
        row = QHBoxLayout();row.setContentsMargins(8,0,8,0);row.setSpacing(0)
        name = QLabel(label);name.setFixedWidth(88);row.addWidget(name);value.setStyleSheet('color: #eee7f6; font-size: 12px;');value.setMaximumWidth(140);row.addWidget(value);row.addStretch()
        text = QLabel(toggle_label);row.addWidget(text);row.addSpacing(7)
        switch = Toggle();switch.setAccessibleName(toggle_label);switch.clicked.connect(lambda checked:self.change(key,'smooth' if checked else 'off') if key=='aim' else self.change(key,checked))
        self.toggles[key] = switch;row.addWidget(switch);layout.addLayout(row)

    def change(self,key,value):
        try:
            self.model.set(key,value)
            self.apply_timer.start()
            self.refresh()
            self.message.setText('Changes apply to the running session. Save keeps them on disk.')
        except ValueError as error:
            self.message.setText(str(error));self.refresh()

    def reset_setting(self,key):
        self.model.reset(key);self.refresh();self.apply_timer.start()

    def apply_settings(self):
        self.session.update(asdict(self.model.config),self.model.revision)

    def refresh(self):
        for key,row in self.sliders.items():
            row.set_value(getattr(self.model.config,key))
        for key,switch in self.toggles.items():
            switch.blockSignals(True);switch.setChecked(self.model.config.aim!='off' if key=='aim' else getattr(self.model.config,key));switch.blockSignals(False)
        for key,combo in self.combos.items():
            combo.blockSignals(True);combo.setCurrentText(str(getattr(self.model.config,key)));combo.blockSignals(False)
        for name,button in self.tab_buttons.items():
            button.selected = self.expanded and name == self.page;button.update()
        self.config_label.setText(self.model.name)
        menu_key = self.model.config.keys['menu_toggle']
        self.menu_hint.setText(self.key_name(menu_key)+' · menu')
        if menu_key != self.menu_hotkey.key:
            self.menu_hotkey.prime(menu_key)
        for key,button in getattr(self,'binding_buttons',{}).items():
            if self.page=='Input' and (self.capture is None or self.capture[0]!=key):
                button.setText(self.key_name(self.model.config.keys[key]))
        try:
            profile = load_profile(self.profile_path)
            self.hero.profile = 'Pinned profile · '+profile.source[:12]
        except (OSError,ValueError):
            self.hero.profile = 'Select an offset profile in Configs'
        self.hero.update()

    def fade_details(self):
        self.page_motion.stop()
        self.page_motion.setStartValue(0.25)
        self.page_motion.setEndValue(1.0)
        self.page_motion.start()

    def select_page(self,name):
        self.page,self.expanded = name,True;self.build_details();self.resize_panel();self.refresh()
        self.fade_details()

    def toggle_more(self):
        self.expanded = not self.expanded;self.resize_panel();self.refresh()
        if self.expanded:
            self.fade_details()
        else:
            self.page_motion.stop()
            self.details_opacity.setOpacity(1.0)

    def resize_panel(self):
        self.more.setText('Less' if self.expanded else 'More')
        self.details_scroll.setVisible(self.expanded)
        screen = self.screen() or QApplication.primaryScreen()
        available = screen.availableGeometry() if screen else None
        width = min(980, available.width()-24) if available else 980
        # Keep the overview readable and let longer detail pages scroll.
        # On narrow desktops compact mode still uses the original small panel.
        self.setFixedWidth(width if self.expanded else 440)
        self.overview.setFixedWidth(min(440, width//2) if self.expanded else 440)
        wanted = 600 if self.expanded else 558
        self.setFixedHeight(min(wanted, available.height()-24) if available else wanted)

    def clear_details(self):
        self.cancel_capture()
        self.binding_buttons = {}
        # Top-level controls survive; detail controls are rebuilt on tab changes.
        self.sliders = {key:value for key,value in self.sliders.items() if key in {spec[1] for spec in SLIDERS}}
        self.toggles = {key:value for key,value in self.toggles.items() if key in ('esp','aim','trigger')}
        self.combos.clear()
        while self.details_layout.count():
            item = self.details_layout.takeAt(0)
            if item.widget():item.widget().deleteLater()
            elif item.layout():self.delete_layout(item.layout())

    def delete_layout(self,layout):
        while layout.count():
            item=layout.takeAt(0)
            if item.widget():item.widget().deleteLater()
            elif item.layout():self.delete_layout(item.layout())

    def section(self,text):
        label=QLabel(text);label.setStyleSheet('font-size: 11px; color: #d4c4f9; letter-spacing: .5px;');label.setFixedHeight(23);self.details_layout.addWidget(label)

    def detail_toggle(self,label,key):
        row=QHBoxLayout();row.addWidget(QLabel(label));row.addStretch();switch=Toggle();switch.setAccessibleName(label)
        switch.clicked.connect(lambda checked:self.change(key,checked));self.toggles[key]=switch;row.addWidget(switch);self.details_layout.addLayout(row)

    def detail_combo(self,label,key,values):
        row=QHBoxLayout();row.addWidget(QLabel(label));row.addStretch();combo=QComboBox();combo.addItems(values);combo.setFixedWidth(170);combo.setAccessibleName(label)
        combo.currentTextChanged.connect(lambda value:self.change(key,value));self.combos[key]=combo;row.addWidget(combo);self.details_layout.addLayout(row)

    def note(self,text):
        label=QLabel(text);label.setWordWrap(True);label.setStyleSheet('font-size: 11px; color: #9284ac;');self.details_layout.addWidget(label)

    def build_details(self):
        self.clear_details()
        if self.page=='Aim':
            self.section('AIM TUNING')
            self.detail_combo('Aim mode','aim',['off','smooth','hardlock'])
            self.detail_combo('Priority bone','priority_bone',['head','neck','chest','pelvis'])
            self.add_slider(self.details_layout,'Max speed','max_aim_speed',1,1,360,0,'°/s')
            self.note('Smooth uses a critically damped response. Prediction is constant-velocity look-ahead, not a ballistic model.')
            self.section('ACTIVATION')
            self.note('Hold right mouse to aim and left Alt to trigger by default. Edit either binding in Input. New configurations start with both features off.')
            self.note('Target filtering uses an entity spotted-mask proxy, not per-bone or map visibility.')
        elif self.page=='Visuals':
            self.section('OVERLAY DISPLAY')
            for label,key in [('Skeleton','skeleton'),('Health bars','health'),('Armor bars','armor'),('Show teammates','teammates'),('Circular radar','radar'),('Spectator list','spectators')]:
                self.detail_toggle(label,key)
            self.add_slider(self.details_layout,'Range','max_distance_m',1,1,1000,0,'m')
            self.note('An external overlay, not in-game glow. Colors indicate the local spotted mask; they do not prove line of sight.')
        elif self.page=='Input':
            self.section('MOVEMENT & BINDINGS')
            self.detail_toggle('Bunny hop','bunny_hop')
            self.binding_buttons={}
            for key,label in [('menu_toggle','Menu toggle'),('aim_hold','Hold aim'),('trigger_hold','Hold trigger'),('jump_hold','Hold jump'),('esp_toggle','Toggle ESP'),('aim_toggle','Toggle aim'),('trigger_toggle','Toggle trigger'),('radar_toggle','Toggle radar'),('reload','Reload config'),('save','Save config'),('exit','Emergency exit')]:
                row=QHBoxLayout();row.addWidget(QLabel(label));row.addStretch();button=QPushButton(self.key_name(self.model.config.keys[key]));button.setFixedSize(108,23);button.setStyleSheet('background: #201a2b; border: 1px solid #655278; border-radius: 3px; font-size: 11px;');button.setAccessibleName('Bind '+label)
                button.clicked.connect(lambda checked=False,name=key,b=button:self.begin_capture(name,b));row.addWidget(button);self.binding_buttons[key]=button;self.details_layout.addLayout(row)
            self.note('Click a binding, then press a key or mouse button. Right Shift opens/closes the menu by default. Escape cancels. Save in Configs to keep changes.')
        else:
            self.section('LOCAL CONFIGURATIONS')
            self.name_edit=QLineEdit(self.model.name);self.name_edit.setPlaceholderText('Configuration name');self.name_edit.setMaxLength(40);self.name_edit.setAccessibleName('Configuration name');self.details_layout.addWidget(self.name_edit)
            row=QHBoxLayout();save=QPushButton('Save named config');save.setStyleSheet('background: #7145a1; color: white; border-radius: 3px; padding: 6px;');save.clicked.connect(self.save_named);row.addWidget(save)
            self.saved_combo=QComboBox();self.saved_combo.addItems(self.model.names());self.saved_combo.setAccessibleName('Saved configurations');row.addWidget(self.saved_combo,1)
            load=QPushButton('Load');load.clicked.connect(self.load_named);row.addWidget(load);self.details_layout.addLayout(row)
            self.note('Saving an existing name replaces it. Stop the runtime before switching named configurations.')
            self.section('OFFSET PROFILE')
            self.profile_label=QLabel(str(self.profile_path));self.profile_label.setWordWrap(True);self.profile_label.setStyleSheet('font-size: 10px; color: #9284ac;');self.details_layout.addWidget(self.profile_label)
            browse=QPushButton('Choose profile JSON…');browse.setStyleSheet('background: #382b49; border: 1px solid #655278; border-radius: 3px; padding: 5px;');browse.clicked.connect(self.choose_profile);self.details_layout.addWidget(browse)
            self.note('Profile checks validate file structure, not live game compatibility. No offsets are downloaded silently.')
        self.details_layout.addStretch()

    def save_named(self):
        name=self.name_edit.text().strip()
        if self.session.process is not None and name!=self.model.name:
            self.message.setText('Stop the runtime before changing the active config name.');return
        if name!=self.model.name and any(n.casefold()==name.casefold() for n in self.model.names()) and QMessageBox.question(self,'Replace config?',f'Replace “{name}”?')!=QMessageBox.StandardButton.Yes:
            return
        try:
            self.model.save(name);self.saved_combo.clear();self.saved_combo.addItems(self.model.names());self.refresh();self.message.setText('Saved locally: '+self.model.name)
        except (OSError,ValueError) as error:self.message.setText(str(error))

    def load_named(self):
        if self.session.process is not None:
            self.message.setText('Stop the runtime before loading another configuration.');return
        name=self.saved_combo.currentText()
        if not name:return
        if QMessageBox.question(self,'Load configuration?', 'Replace current preferences, including unsaved changes?')!=QMessageBox.StandardButton.Yes:return
        try:
            self.model.load(name);self.name_edit.setText(name);self.refresh();self.message.setText('Loaded '+name)
        except (OSError,ValueError) as error:self.message.setText(str(error))

    def choose_profile(self):
        if self.session.process is not None:
            self.message.setText('Stop the runtime before changing the offset profile.');return
        name,_=QFileDialog.getOpenFileName(self,'Select a native offset profile',str(self.profile_path.parent),'JSON profiles (*.json)')
        if name:
            try:
                load_profile(name);self.profile_path=Path(name);self.profile_label.setText(name);self.refresh();self.message.setText('Profile structure accepted. Live compatibility is unverified.')
            except (OSError,ValueError) as error:self.message.setText(str(error))

    @staticmethod
    def key_name(vk):
        names={1:'Mouse left',2:'Mouse right',4:'Mouse middle',5:'Mouse 4',6:'Mouse 5',0x10:'Shift',0x11:'Ctrl',0x12:'Alt',0x20:'Space',0x23:'End',0x24:'Home',0x2D:'Insert',0x2E:'Delete',0xA0:'Left Shift',0xA1:'Right Shift',0xA2:'Left Ctrl',0xA3:'Right Ctrl',0xA4:'Left Alt',0xA5:'Right Alt'}
        if vk in names:return names[vk]
        if 0x70<=vk<=0x7B:return 'F'+str(vk-0x6F)
        if 0x30<=vk<=0x5A:return chr(vk)
        return f'VK {vk:02X}'

    def begin_capture(self,key,button):
        self.cancel_capture();self.capture=(key,button);button.setText('Press a key…');QApplication.instance().installEventFilter(self);self.capture_timer.start(8000)

    def cancel_capture(self):
        if self.capture is not None:
            key,button=self.capture;button.setText(self.key_name(self.model.config.keys[key]));self.capture=None
            QApplication.instance().removeEventFilter(self);self.capture_timer.stop()
            self.menu_hotkey.prime(self.model.config.keys['menu_toggle'])

    def eventFilter(self,watched,event):
        if self.capture and event.type() in (QEvent.Type.KeyPress,QEvent.Type.MouseButtonPress):
            if event.type()==QEvent.Type.KeyPress:
                if event.key()==Qt.Key.Key_Escape:self.cancel_capture();return True
                code=capture_vk(int(event.key()), int(event.nativeVirtualKey()) if sys.platform=='win32' else 0, int(event.nativeScanCode()) if sys.platform=='win32' else 0)
            else:code={Qt.MouseButton.LeftButton:1,Qt.MouseButton.RightButton:2,Qt.MouseButton.MiddleButton:4,Qt.MouseButton.BackButton:5,Qt.MouseButton.ForwardButton:6}.get(event.button(),0)
            if not 1<=code<=254:self.message.setText('That key is not supported. Escape cancels.');return True
            key,_=self.capture
            try:
                self.model.set_key(key,int(code));self.cancel_capture();self.apply_timer.start();self.message.setText('Binding updated; save in Configs to keep it.');self.refresh()
            except ValueError as error:self.message.setText(str(error))
            return True
        return super().eventFilter(watched,event)

    def start_runtime(self):
        try:
            self.apply_timer.stop();self.model.save()
            self.session.start(self.profile_path,self.model.document(),self.model.path)
            self.session.update(asdict(self.model.config),self.model.revision)
            self.hero.status='STARTING';self.runtime_label.setText('Starting');self.message.setText('Runtime starts paused. Hide the menu with '+self.key_name(self.model.config.keys['menu_toggle'])+' to resume.');self.update_session_buttons()
        except (OSError,ValueError) as error:self.message.setText(str(error))

    def stop_runtime(self):
        self.session.stop()
        if self.session.process is not None:
            self.runtime_label.setText('Stopping');self.hero.status='STOPPING';self.hero.update()
        self.update_session_buttons()

    def update_session_buttons(self):
        active=self.session.process is not None
        self.start_button.setEnabled(not active);self.stop_button.setEnabled(active and self.session.stopping_since is None)

    def poll_runtime(self):
        for event in self.session.poll():
            kind=event.get('kind')
            if kind=='status':
                message=event.get('message','');self.message.setText(message)
                self.runtime_label.setText('Reading' if message.startswith('Live reads:') else 'Paused' if message.startswith('Paused') else 'Waiting' if 'Waiting' in message or 'No usable' in message else 'Running')
                self.hero.status='PAUSED' if message.startswith('Paused') else 'RUNNING'
            elif kind=='frame':self.players.setText(str(event['players']));self.last_frame=time.monotonic()
            elif kind=='settings':
                try:
                    if not self.apply_timer.isActive() and self.model.accept_runtime(event['settings'],event['revision']):self.refresh()
                except ValueError:self.message.setText('Invalid runtime settings report ignored.')
            elif kind=='error':self.message.setText(event.get('message','Runtime failed.'));self.hero.status='ERROR'
            elif kind=='stopped':
                self.runtime_label.setText('Stopped');self.hero.status='READY';self.players.setText('—')
        if self.last_frame and time.monotonic()-self.last_frame>2:self.players.setText('—')
        self.hero.update();self.update_session_buttons()
        if self.closing and self.session.process is None:self.close()

    def closeEvent(self,event):
        self.cancel_capture()
        if self.session.process is not None:
            self.closing=True;self.stop_runtime();event.ignore();return
        self.timer.stop();self.menu_timer.stop();self.apply_timer.stop()
        for motion in self.findChildren(QVariantAnimation):
            motion.stop()
        event.accept()


def launch(profile,config_dir,config_name='default',screenshots=None):
    app=QApplication.instance() or QApplication([])
    try:
        panel=ControlPanel(profile,config_dir,config_name)
    except (OSError,ValueError,RuntimeError) as error:
        if screenshots is None:
            QMessageBox.critical(None,'Phantom could not open',str(error))
        return 1
    panel.show()
    if screenshots is not None:
        def capture():
            try:
                directory=Path(screenshots);directory.mkdir(parents=True,exist_ok=True)
                panel.resize_panel();app.processEvents()
                if panel.hero.image.isNull():
                    raise OSError('The bundled banner asset is missing.')
                if not panel.grab().save(str(directory/'gui-expanded.png')):
                    raise OSError('Could not save expanded GUI screenshot.')
                panel.toggle_more();app.processEvents()
                if not panel.grab().save(str(directory/'gui-compact.png')):
                    raise OSError('Could not save compact GUI screenshot.')
                panel.close();app.exit(0)
            except (OSError,ValueError):
                panel.close();app.exit(1)
        QTimer.singleShot(250,capture)
    return app.exec()
