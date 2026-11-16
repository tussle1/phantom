"""Interactive sample-only ESP designer, using the real overlay drawing commands."""
from PySide6.QtCore import Qt, QPointF, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (QWidget, QDialog, QHBoxLayout, QVBoxLayout, QLabel,
    QPushButton, QCheckBox, QComboBox, QColorDialog, QScrollArea)

from .esp_style import POSE, TARGETS, DEFAULT_STYLE, Line, player_commands
from .core import BONE_LINKS
from .typography import ui_font


class SkeletonPreview(QWidget):
    target_selected = Signal(str)

    def __init__(self, config_provider):
        super().__init__()
        self.config_provider = config_provider
        self.sample = 'spotted enemy'
        self.setMinimumSize(320,430)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName('Sample skeleton aim target selector')
        self.setAccessibleDescription('Click head, neck, chest or pelvis; keyboard keys 1 to 4 select those targets. Does not enable aim.')

    def points(self):
        area = self.rect().adjusted(42,42,-78,-40)
        return {name:(area.left()+x*area.width(),area.top()+y*area.height()) for name,(x,y) in POSE.items()}

    def hit_target(self, point):
        hits = [(QPointF(*self.points()[name])-point).manhattanLength() for name in TARGETS]
        best = min(range(len(hits)),key=hits.__getitem__)
        return TARGETS[best] if hits[best] <= 20 else None

    def mousePressEvent(self,event):
        if event.button() == Qt.MouseButton.LeftButton:
            target = self.hit_target(event.position())
            if target:
                self.setFocus();self.target_selected.emit(target)
        super().mousePressEvent(event)

    def mouseMoveEvent(self,event):
        self.setCursor(Qt.CursorShape.PointingHandCursor if self.hit_target(event.position()) else Qt.CursorShape.ArrowCursor)
        super().mouseMoveEvent(event)

    def keyPressEvent(self,event):
        index = event.key()-Qt.Key.Key_1
        if 0 <= index < len(TARGETS):
            self.target_selected.emit(TARGETS[index]);event.accept();return
        super().keyPressEvent(event)

    def paintEvent(self,event):
        config = self.config_provider()
        points = self.points()
        p = QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(),QColor('#15121d'))
        p.setFont(ui_font(9));p.setPen(QColor('#ada1bf'))
        p.drawText(14,22,'design preview · sample actor')
        # Always keep a faint selection guide, separate from actual ESP output.
        p.setPen(QPen(QColor('#51495f'),1,Qt.PenStyle.DashLine))
        for a,b in BONE_LINKS:
            p.drawLine(QPointF(*points[a]),QPointF(*points[b]))
        commands = player_commands(points,'sample player',42,76,60,
                                   self.sample=='spotted enemy',self.sample=='teammate',config)
        for command in commands:
            if isinstance(command,Line):
                p.setPen(QPen(QColor(command.color),command.width))
                p.drawLine(QPointF(*command.start),QPointF(*command.end))
            else:
                p.setPen(QColor(command.color))
                p.drawText(QPointF(command.at[0],command.at[1]+12),command.text)
        for index,name in enumerate(TARGETS):
            selected = config.priority_bone == name
            p.setPen(QPen(QColor('#fc589b' if selected else '#d5c9e6'),2 if selected else 1))
            p.setBrush(QColor('#fc589b' if selected else '#25202e'))
            p.drawEllipse(QPointF(*points[name]),7 if selected else 5,7 if selected else 5)
            p.setPen(QColor('#fff1fa' if selected else '#b7a9c9'))
            p.drawText(QPointF(points[name][0]+18,points[name][1]+4),f'{index+1} · {name}')
        p.setPen(QColor('#c5b5f6'))
        p.drawText(14,self.height()-14,'aim target: '+config.priority_bone+' · guide is editor-only')


class EspEditor(QDialog):
    def __init__(self,panel):
        super().__init__(panel)
        self.panel = panel
        self.setWindowTitle('phantom · esp designer')
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.setWindowIcon(panel.windowIcon())
        self.setFont(ui_font(10))
        outer = QVBoxLayout(self)
        note = QLabel('sample design only — not live game footage. click a target or press 1–4. selection does not enable aim.');note.setWordWrap(True);outer.addWidget(note)
        content = QWidget();columns = QHBoxLayout(content)
        self.preview = SkeletonPreview(lambda: panel.model.config)
        self.preview.target_selected.connect(lambda target: panel.change('priority_bone',target))
        columns.addWidget(self.preview,1)
        settings = QWidget();controls = QVBoxLayout(settings);settings.setMinimumWidth(250)
        self.checks = {}
        for key,label in [('esp','ESP output'),('skeleton','Skeleton'),('health','Health bar'),('armor','Armor bar')]:
            control = QCheckBox(label);control.toggled.connect(lambda value,key=key: panel.change(key,value));controls.addWidget(control);self.checks[key] = control
        self.style_checks = {}
        for key,label in [('box','Bounding box'),('names','Player name'),('distance','Distance label')]:
            control = QCheckBox(label);control.toggled.connect(lambda value,key=key: self.change_style(key,value));controls.addWidget(control);self.style_checks[key] = control
        row = QHBoxLayout();row.addWidget(QLabel('Box style'))
        self.box_style_combo = QComboBox();self.box_style_combo.addItems(['full','corner']);self.box_style_combo.setAccessibleName('ESP box style')
        self.box_style_combo.currentTextChanged.connect(lambda value: self.change_style('box_style',value));row.addWidget(self.box_style_combo);controls.addLayout(row)
        row = QHBoxLayout();row.addWidget(QLabel('Line width'))
        self.width_combo = QComboBox();self.width_combo.addItems(['1','2','3','4']);self.width_combo.setAccessibleName('ESP line width')
        self.width_combo.currentTextChanged.connect(lambda value: self.change_style('line_width',int(value)));row.addWidget(self.width_combo);controls.addLayout(row)
        self.color_buttons = {}
        for key,label in [('visible_color','Spotted enemy'),('hidden_color','Unspotted enemy'),('team_color','Teammate'),('health_color','Health'),('armor_color','Armor')]:
            button = QPushButton();button.setAccessibleName(label+' ESP color');button.clicked.connect(lambda checked=False,key=key: self.choose_color(key))
            controls.addWidget(button);self.color_buttons[key] = (button,label)
        self.sample_combo = QComboBox();self.sample_combo.addItems(['spotted enemy','unspotted enemy','teammate']);self.sample_combo.setAccessibleName('Preview sample state')
        self.sample_combo.currentTextChanged.connect(self.change_sample);controls.addWidget(self.sample_combo)
        reset = QPushButton('Reset ESP style');reset.clicked.connect(lambda: panel.change('esp_style',dict(DEFAULT_STYLE)));controls.addWidget(reset)
        controls.addStretch();columns.addWidget(settings)
        scroll = QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(content);outer.addWidget(scroll,1)
        self.status = QLabel();self.status.setWordWrap(True);outer.addWidget(self.status)
        footer = QHBoxLayout()
        save = QPushButton('Save current config');save.clicked.connect(self.save_config);footer.addWidget(save)
        close = QPushButton('Done');close.clicked.connect(self.close);footer.addWidget(close);outer.addLayout(footer)
        screen = self.screen().availableGeometry()
        self.resize(min(800,screen.width()-24),min(640,screen.height()-24))
        self.refresh()

    def change_sample(self,value):
        self.preview.sample = value;self.preview.update()

    def change_style(self,key,value):
        style = {**self.panel.model.config.esp_style,key:value}
        self.panel.change('esp_style',style)

    def choose_color(self,key):
        color = QColorDialog.getColor(QColor(self.panel.model.config.esp_style[key]),self,'Choose ESP color')
        if color.isValid():
            self.change_style(key,color.name())

    def refresh(self):
        config = self.panel.model.config
        for key,control in self.checks.items():
            control.blockSignals(True);control.setChecked(getattr(config,key));control.blockSignals(False)
        for key,control in self.style_checks.items():
            control.blockSignals(True);control.setChecked(config.esp_style[key]);control.blockSignals(False)
        self.box_style_combo.blockSignals(True);self.box_style_combo.setCurrentText(config.esp_style['box_style']);self.box_style_combo.blockSignals(False)
        self.width_combo.blockSignals(True);self.width_combo.setCurrentText(str(config.esp_style['line_width']));self.width_combo.blockSignals(False)
        for key,(button,label) in self.color_buttons.items():
            button.setText(label+' · '+config.esp_style[key])
        self.preview.update()
        self.status.setText('Target: '+config.priority_bone+' · aim mode: '+config.aim+'. Changes are unsaved until you save. Guide dots are not overlay hitboxes. Pure black is reserved for transparency.')

    def save_config(self):
        try:
            self.panel.model.save()
            self.status.setText('Saved current config: '+self.panel.model.name)
        except (OSError,ValueError) as error:
            self.status.setText(str(error))
