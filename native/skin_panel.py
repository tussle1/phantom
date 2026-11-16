"""Native Qt Local Skin Changer panel and live preview card."""
from __future__ import annotations

import random

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .skin_bridge import probe_foundation
from .skins import (
    DEFAULT_SKIN_ENTRY,
    KNIVES,
    MAX_CUSTOM_NAME,
    MAX_PAINT_KIT,
    MAX_SEED,
    MAX_SKINS,
    MAX_STATTRAK,
    MESH_GROUPS,
    RARITY_COLORS,
    STARTER_LOADOUTS,
    WEAPON_BY_ID,
    WEAPON_CATEGORIES,
    WEAPONS,
    WEAR_TIERS,
    display_weapon_name,
    is_custom_knife,
    kit_by_id,
    kits_for_weapon,
    weapon_name,
    wear_tier,
)
from .typography import ui_font


def _theme(widget, name, fallback):
    return getattr(widget.window(), 'appearance_palette', {}).get(name, fallback)


class SkinPreviewCard(QWidget):
    """Natively painted local skin finish preview card."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.weapon_definition = 7
        self.entry = dict(DEFAULT_SKIN_ENTRY)
        self.configured = False
        self.active_knife_override = 0
        self.setFixedHeight(114)
        self.setAccessibleName('Local skin preview')

    def set_state(self, weapon_definition, entry, configured, active_knife_override=0):
        self.weapon_definition = int(weapon_definition)
        self.entry = dict(entry)
        self.configured = bool(configured)
        self.active_knife_override = int(active_knife_override)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        surface = QColor(_theme(self, 'surface', '#201a2b'))
        border = QColor(_theme(self, 'border', '#655278'))
        ink = QColor(_theme(self, 'ink', '#e6ddef'))
        muted = QColor(_theme(self, 'muted', '#9284ac'))
        accent = QColor(_theme(self, 'accent', '#fc589b'))

        kit = kit_by_id(self.entry['paint_kit'], self.weapon_definition)
        rarity = kit.rarity if kit else 'Restricted'
        rarity_color = QColor(RARITY_COLORS.get(rarity, accent.name()))
        swatches = kit.swatches if kit else (accent.name(), border.name(), surface.lighter(135).name())
        kit_title = kit.name if kit else f'Custom kit #{self.entry["paint_kit"]}'

        rect = QRectF(0.5, 0.5, self.width() - 1.0, self.height() - 1.0)
        p.setPen(QPen(rarity_color if self.configured else border, 1.2))
        p.setBrush(surface)
        p.drawRoundedRect(rect, 5, 5)

        # Rarity stripe across the top edge.
        stripe = QLinearGradient(0, 0, self.width(), 0)
        stripe.setColorAt(0.0, rarity_color)
        stripe.setColorAt(1.0, QColor(swatches[1]))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(stripe)
        p.drawRoundedRect(QRectF(1.5, 1.5, self.width() - 3.0, 4.0), 2, 2)

        # Weapon heading & rarity pill.
        w_label = f'{display_weapon_name(self.weapon_definition)} · #{self.weapon_definition}'
        p.setPen(ink)
        p.setFont(ui_font(11))
        p.drawText(QRectF(10, 10, self.width() - 110, 20), Qt.AlignmentFlag.AlignVCenter, w_label)

        pill_rect = QRectF(self.width() - 96, 11, 86, 18)
        pill_bg = QColor(rarity_color)
        pill_bg.setAlpha(45)
        p.setPen(QPen(rarity_color, 1.0))
        p.setBrush(pill_bg)
        p.drawRoundedRect(pill_rect, 8, 8)
        p.setPen(ink)
        p.setFont(ui_font(8))
        p.drawText(pill_rect, Qt.AlignmentFlag.AlignCenter, rarity)

        # Paint kit subtitle & 3-tone swatch strip.
        p.setPen(muted)
        p.setFont(ui_font(9))
        kit_line = f'{kit_title} · kit {self.entry["paint_kit"]}'
        if self.configured:
            kit_line += ' · active'
        p.drawText(QRectF(10, 32, self.width() - 96, 18), Qt.AlignmentFlag.AlignVCenter, kit_line)

        for idx, color_hex in enumerate(swatches):
            swatch_rect = QRectF(self.width() - 78 + idx * 23, 34, 20, 14)
            p.setPen(QPen(border, 0.8))
            p.setBrush(QColor(color_hex))
            p.drawRoundedRect(swatch_rect, 3, 3)

        # Wear spectrum bar with live indicator.
        bar_x, bar_y, bar_w, bar_h = 10.0, 58.0, max(60.0, self.width() - 20.0), 7.0
        wear_grad = QLinearGradient(bar_x, 0, bar_x + bar_w, 0)
        wear_grad.setColorAt(0.00, QColor('#55dc8c'))
        wear_grad.setColorAt(0.07, QColor('#45c7d6'))
        wear_grad.setColorAt(0.26, QColor('#f0c85a'))
        wear_grad.setColorAt(0.45, QColor('#f08c4a'))
        wear_grad.setColorAt(1.00, QColor('#e8586b'))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(wear_grad)
        p.drawRoundedRect(QRectF(bar_x, bar_y, bar_w, bar_h), 3.5, 3.5)

        wear_val = max(0.0, min(1.0, float(self.entry['wear'])))
        marker_x = bar_x + wear_val * bar_w
        p.setPen(QPen(QColor('#ffffff'), 1.6))
        p.setBrush(surface)
        p.drawEllipse(QRectF(marker_x - 4.5, bar_y - 1.5, 9.0, 10.0))

        tier_label, tier_short, tier_color = wear_tier(wear_val)
        p.setPen(QColor(tier_color))
        p.setFont(ui_font(8))
        p.drawText(QRectF(10, 71, self.width() - 20, 16), Qt.AlignmentFlag.AlignVCenter,
                   f'{wear_val:.4f} · {tier_label} ({tier_short})')

        # Bottom badges: seed, StatTrak, knife override, nametag, mesh.
        badges = [f'seed {self.entry["seed"]}', f'mesh {self.entry["mesh_group"]}']
        if self.entry['stattrak'] >= 0:
            badges.insert(1, f'st {self.entry["stattrak"]}')
        if is_custom_knife(self.weapon_definition) and self.active_knife_override == self.weapon_definition:
            badges.insert(0, 'equipped')
        if self.entry['custom_name']:
            badges.append(f'"{self.entry["custom_name"]}"')
        p.setPen(ink)
        p.setFont(ui_font(8))
        badge_text = p.fontMetrics().elidedText(
            ' · '.join(badges), Qt.TextElideMode.ElideRight, max(40, int(self.width() - 86))
        )
        p.drawText(QRectF(10, 90, self.width() - 84, 18), Qt.AlignmentFlag.AlignVCenter, badge_text)

        p.setPen(muted)
        p.drawText(QRectF(self.width() - 74, 90, 64, 18),
                   Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, 'local only')


class SkinPanel(QWidget):
    """Interactive local CS2 weapon skin changer page for ControlPanel."""

    def __init__(self, panel, toggle_cls):
        super().__init__(panel.details)
        self.panel = panel
        self._syncing = False
        self._loaded_entry = None
        self._sections = []
        self._muted_labels = []
        self._secondary_buttons = []
        self._chip_buttons = []
        self.selected_weapon = getattr(panel, 'selected_skin_weapon', 7)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._section(layout, 'LOCAL SKIN CHANGER')
        top_row = QHBoxLayout()
        top_row.addWidget(QLabel('Enable local skins'))
        top_row.addStretch()
        self.enable_toggle = toggle_cls(panel.model.config.skin_changer)
        self.enable_toggle.setAccessibleName('Enable local skins')
        self.enable_toggle.clicked.connect(lambda checked: panel.change('skin_changer', checked))
        panel.toggles['skin_changer'] = self.enable_toggle
        top_row.addWidget(self.enable_toggle)
        layout.addLayout(top_row)

        self.count_label = QLabel()
        self.count_label.setWordWrap(True)
        self._muted_labels.append(self.count_label)
        layout.addWidget(self.count_label)

        knife_row = QHBoxLayout()
        knife_row.addWidget(QLabel('Active knife'))
        knife_row.addStretch()
        self.knife_override_combo = QComboBox()
        self.knife_override_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.knife_override_combo.setFixedWidth(168)
        self.knife_override_combo.setAccessibleName('Active knife model override')
        self.knife_override_combo.addItem('Default knife (off)', 0)
        for knife in KNIVES:
            self.knife_override_combo.addItem(f'★ {knife.name}', knife.definition)
        self.knife_override_combo.currentIndexChanged.connect(self._on_knife_override_changed)
        knife_row.addWidget(self.knife_override_combo)
        layout.addLayout(knife_row)

        self.preview = SkinPreviewCard(self)
        layout.addWidget(self.preview)

        self._section(layout, 'WEAPON & FINISH')
        cat_row = QHBoxLayout()
        cat_row.addWidget(QLabel('Category'))
        cat_row.addStretch()
        self.category_combo = QComboBox()
        self.category_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.category_combo.setFixedWidth(168)
        self.category_combo.setAccessibleName('Weapon category')
        self.category_combo.addItems(list(WEAPON_CATEGORIES))
        self.category_combo.currentTextChanged.connect(self._on_category_changed)
        cat_row.addWidget(self.category_combo)
        layout.addLayout(cat_row)

        weapon_row = QHBoxLayout()
        weapon_row.addWidget(QLabel('Weapon'))
        weapon_row.addStretch()
        self.weapon_combo = QComboBox()
        self.weapon_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.weapon_combo.setFixedWidth(168)
        self.weapon_combo.setAccessibleName('Weapon selector')
        self.weapon_combo.currentIndexChanged.connect(self._on_weapon_changed)
        weapon_row.addWidget(self.weapon_combo)
        layout.addLayout(weapon_row)

        kit_row = QHBoxLayout()
        kit_row.addWidget(QLabel('Skin preset'))
        kit_row.addStretch()
        self.kit_combo = QComboBox()
        self.kit_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.kit_combo.setFixedWidth(168)
        self.kit_combo.setAccessibleName('Skin finish preset')
        self.kit_combo.currentIndexChanged.connect(self._on_kit_preset_changed)
        kit_row.addWidget(self.kit_combo)
        layout.addLayout(kit_row)

        kit_id_row = QHBoxLayout()
        kit_id_row.addWidget(QLabel('Paint kit ID'))
        kit_id_row.addStretch()
        self.kit_spin = QSpinBox()
        self.kit_spin.setRange(0, MAX_PAINT_KIT)
        self.kit_spin.setFixedWidth(168)
        self.kit_spin.setKeyboardTracking(False)
        self.kit_spin.setAccessibleName('Paint kit ID')
        self.kit_spin.valueChanged.connect(self._on_kit_spin_changed)
        kit_id_row.addWidget(self.kit_spin)
        layout.addLayout(kit_id_row)

        self._section(layout, 'FINISH TUNING')
        wear_row = QHBoxLayout()
        wear_lbl = QLabel('Wear float')
        wear_lbl.setFixedWidth(74)
        wear_row.addWidget(wear_lbl)
        self.wear_spin = QDoubleSpinBox()
        self.wear_spin.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        self.wear_spin.setDecimals(4)
        self.wear_spin.setRange(0.0, 1.0)
        self.wear_spin.setSingleStep(0.005)
        self.wear_spin.setFixedWidth(68)
        self.wear_spin.setKeyboardTracking(False)
        self.wear_spin.setAccessibleName('Wear float value')
        self.wear_spin.valueChanged.connect(self._on_wear_spin_changed)
        wear_row.addWidget(self.wear_spin)
        self.wear_slider = QSlider(Qt.Orientation.Horizontal)
        self.wear_slider.setRange(0, 10000)
        self.wear_slider.setAccessibleName('Wear float slider')
        self.wear_slider.valueChanged.connect(self._on_wear_slider_changed)
        wear_row.addWidget(self.wear_slider, 1)
        layout.addLayout(wear_row)

        tier_row = QHBoxLayout()
        tier_row.setSpacing(4)
        self.wear_buttons = {}
        for label, short, _, _, preset_val, _ in WEAR_TIERS:
            btn = QPushButton(short)
            btn.setToolTip(f'{label} ({preset_val:.3f})')
            btn.setAccessibleName(f'Set {label} wear')
            btn.setFixedHeight(26)
            btn.clicked.connect(lambda checked=False, val=preset_val: self._set_wear(val))
            tier_row.addWidget(btn)
            self.wear_buttons[short] = btn
            self._chip_buttons.append(btn)
        layout.addLayout(tier_row)

        seed_row = QHBoxLayout()
        seed_row.addWidget(QLabel('Pattern seed'))
        seed_row.addStretch()
        self.seed_spin = QSpinBox()
        self.seed_spin.setRange(0, MAX_SEED)
        self.seed_spin.setFixedWidth(96)
        self.seed_spin.setKeyboardTracking(False)
        self.seed_spin.setAccessibleName('Pattern seed')
        self.seed_spin.valueChanged.connect(self._update_preview)
        seed_row.addWidget(self.seed_spin)
        self.random_seed_button = QPushButton('Random')
        self.random_seed_button.setAccessibleName('Randomize pattern seed')
        self.random_seed_button.setFixedHeight(28)
        self.random_seed_button.clicked.connect(self._randomize_seed)
        seed_row.addWidget(self.random_seed_button)
        self._secondary_buttons.append(self.random_seed_button)
        layout.addLayout(seed_row)

        st_row = QHBoxLayout()
        st_row.addWidget(QLabel('StatTrak'))
        st_row.addStretch()
        self.stattrak_toggle = toggle_cls(False)
        self.stattrak_toggle.setAccessibleName('Enable StatTrak')
        self.stattrak_toggle.clicked.connect(self._on_stattrak_toggled)
        st_row.addWidget(self.stattrak_toggle)
        self.stattrak_spin = QSpinBox()
        self.stattrak_spin.setRange(0, MAX_STATTRAK)
        self.stattrak_spin.setFixedWidth(116)
        self.stattrak_spin.setEnabled(False)
        self.stattrak_spin.setKeyboardTracking(False)
        self.stattrak_spin.setAccessibleName('StatTrak kill count')
        self.stattrak_spin.valueChanged.connect(self._update_preview)
        st_row.addWidget(self.stattrak_spin)
        layout.addLayout(st_row)

        name_row = QHBoxLayout()
        name_row.addWidget(QLabel('Nametag'))
        name_row.addStretch()
        self.name_edit = QLineEdit()
        self.name_edit.setMaxLength(MAX_CUSTOM_NAME)
        self.name_edit.setFixedWidth(168)
        self.name_edit.setPlaceholderText('Optional local tag')
        self.name_edit.setAccessibleName('Weapon custom nametag')
        self.name_edit.textChanged.connect(self._update_preview)
        name_row.addWidget(self.name_edit)
        layout.addLayout(name_row)

        mesh_row = QHBoxLayout()
        mesh_row.addWidget(QLabel('Model mesh'))
        mesh_row.addStretch()
        self.mesh_combo = QComboBox()
        self.mesh_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.mesh_combo.addItems(list(MESH_GROUPS))
        self.mesh_combo.setFixedWidth(168)
        self.mesh_combo.setAccessibleName('Weapon model mesh group')
        self.mesh_combo.currentTextChanged.connect(self._update_preview)
        mesh_row.addWidget(self.mesh_combo)
        layout.addLayout(mesh_row)

        action_row = QHBoxLayout()
        self.apply_weapon_button = QPushButton('Apply to weapon')
        self.apply_weapon_button.setAccessibleName('Apply skin to selected weapon')
        self.apply_weapon_button.setFixedHeight(30)
        self.apply_weapon_button.clicked.connect(self.apply_current_weapon)
        action_row.addWidget(self.apply_weapon_button, 1)
        self.remove_weapon_button = QPushButton('Remove')
        self.remove_weapon_button.setAccessibleName('Remove skin from selected weapon')
        self.remove_weapon_button.setFixedHeight(30)
        self.remove_weapon_button.clicked.connect(self.remove_current_weapon)
        action_row.addWidget(self.remove_weapon_button)
        self._secondary_buttons.append(self.remove_weapon_button)
        layout.addLayout(action_row)

        self._section(layout, 'ACTIVE LOADOUT')
        self.loadout_list = QListWidget()
        self.loadout_list.setFixedHeight(96)
        self.loadout_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.loadout_list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.loadout_list.setAccessibleName('Configured weapon skins')
        self.loadout_list.itemClicked.connect(self._on_loadout_item_clicked)
        layout.addWidget(self.loadout_list)

        pack_row = QHBoxLayout()
        self.pack_combo = QComboBox()
        self.pack_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.pack_combo.setMinimumWidth(110)
        self.pack_combo.addItems(list(STARTER_LOADOUTS))
        self.pack_combo.setAccessibleName('Starter skin pack')
        pack_row.addWidget(self.pack_combo, 1)
        self.load_pack_button = QPushButton('Load')
        self.load_pack_button.setAccessibleName('Load starter skin pack')
        self.load_pack_button.setFixedHeight(28)
        self.load_pack_button.clicked.connect(self.load_selected_pack)
        pack_row.addWidget(self.load_pack_button)
        self._secondary_buttons.append(self.load_pack_button)
        self.clear_all_button = QPushButton('Clear')
        self.clear_all_button.setAccessibleName('Clear all configured skins')
        self.clear_all_button.setFixedHeight(28)
        self.clear_all_button.clicked.connect(self.clear_all_skins)
        pack_row.addWidget(self.clear_all_button)
        self._secondary_buttons.append(self.clear_all_button)
        layout.addLayout(pack_row)

        self._section(layout, 'LOCAL EXPORT & C++ BRIDGE')
        self.export_button = QPushButton('Sync .skin-loadout.json')
        self.export_button.setAccessibleName('Export skin loadout file')
        self.export_button.setFixedHeight(28)
        self.export_button.clicked.connect(self.sync_loadout_file)
        layout.addWidget(self.export_button)
        self._secondary_buttons.append(self.export_button)

        probe = probe_foundation()
        self.bridge_status = QLabel(probe['summary'])
        self.bridge_status.setWordWrap(True)
        self.bridge_status.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self._muted_labels.append(self.bridge_status)
        layout.addWidget(self.bridge_status)

        note = QLabel(
            'Local client-side cosmetics only (20 knives + 34 firearms); never alters Steam inventory or other players’ views. '
            'Knife overrides write definition/subclass/finish fields; live CS2 3D .vmdl swaps also require an in-process Source 2 UpdateSubclass/SetModel hook (unvalidated live).'
        )
        note.setWordWrap(True)
        note.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self._muted_labels.append(note)
        layout.addWidget(note)
        layout.addSpacing(4)

        self.apply_theme()
        self._populate_weapons()
        self._load_weapon_into_editor(self.selected_weapon)
        self.refresh_from_model()

    def apply_theme(self):
        palette = getattr(self.panel, 'appearance_palette', {})
        surface = palette.get('surface', '#201a2b')
        border = palette.get('border', '#655278')
        ink = palette.get('ink', '#e6ddef')
        muted = palette.get('muted', '#9284ac')
        accent = palette.get('accent', '#fc589b')
        secondary = palette.get('secondary', '#382b49')
        for label in self._sections:
            label.setStyleSheet(f'font-size: 11px; color: {ink}; letter-spacing: .5px;')
        for label in self._muted_labels:
            label.setStyleSheet(f'font-size: 11px; color: {muted};')
        chip_css = (
            f'background: {surface}; color: {ink}; border: 1px solid {border}; '
            'border-radius: 3px; font-size: 11px; padding: 3px 6px;'
        )
        for btn in self._chip_buttons:
            btn.setStyleSheet(chip_css)
        sec_css = (
            f'background: {surface}; color: {ink}; border: 1px solid {border}; '
            'border-radius: 3px; font-size: 11px; padding: 4px 8px;'
        )
        for btn in self._secondary_buttons:
            btn.setStyleSheet(sec_css)
        self.apply_weapon_button.setStyleSheet(
            f'background: {accent}; color: #ffffff; border: 1px solid {accent}; '
            'border-radius: 3px; padding: 5px 8px;'
        )
        self.preview.update()

    def _section(self, layout, text):
        label = QLabel(text)
        label.setFixedHeight(23)
        self._sections.append(label)
        layout.addWidget(label)

    def _populate_weapons(self):
        category = self.category_combo.currentText()
        configured = self.panel.model.config.skins
        self._syncing = True
        self.weapon_combo.clear()
        chosen_index = 0
        for weapon in WEAPONS:
            if category != 'All' and weapon.category != category:
                continue
            tag = ' · set' if str(weapon.definition) in configured else ''
            self.weapon_combo.addItem(f'{display_weapon_name(weapon.definition)} (#{weapon.definition}){tag}', weapon.definition)
            if weapon.definition == self.selected_weapon:
                chosen_index = self.weapon_combo.count() - 1
        if category == 'All':
            for key in sorted(configured, key=int):
                weapon_id = int(key)
                if weapon_id not in WEAPON_BY_ID:
                    self.weapon_combo.addItem(f'{weapon_name(weapon_id)} (#{weapon_id}) · set', weapon_id)
                    if weapon_id == self.selected_weapon:
                        chosen_index = self.weapon_combo.count() - 1
        if self.weapon_combo.count() > 0:
            self.weapon_combo.setCurrentIndex(chosen_index)
            self.selected_weapon = int(self.weapon_combo.currentData())
            self.panel.selected_skin_weapon = self.selected_weapon
        self._syncing = False

    def _populate_kits(self, weapon_definition, current_kit_id):
        self._syncing = True
        self.kit_combo.clear()
        matched_index = -1
        for kit in kits_for_weapon(weapon_definition):
            self.kit_combo.addItem(f'{kit.name} ({kit.paint_kit})', kit.paint_kit)
            if kit.paint_kit == current_kit_id:
                matched_index = self.kit_combo.count() - 1
        self.kit_combo.addItem('Custom paint kit ID', -1)
        self.kit_combo.setCurrentIndex(matched_index if matched_index >= 0 else self.kit_combo.count() - 1)
        self._syncing = False

    def _load_weapon_into_editor(self, weapon_definition):
        self.selected_weapon = int(weapon_definition)
        self.panel.selected_skin_weapon = self.selected_weapon
        stored = self.panel.model.config.skins.get(str(self.selected_weapon))
        self._loaded_entry = dict(stored) if stored is not None else None
        entry = stored if stored is not None else DEFAULT_SKIN_ENTRY
        self._populate_kits(self.selected_weapon, entry['paint_kit'])
        self._syncing = True
        self.kit_spin.setValue(int(entry['paint_kit']))
        self.wear_spin.setValue(float(entry['wear']))
        self.wear_slider.setValue(round(float(entry['wear']) * 10000))
        self.seed_spin.setValue(int(entry['seed']))
        st_enabled = int(entry['stattrak']) >= 0
        self.stattrak_toggle.blockSignals(True)
        self.stattrak_toggle.setChecked(st_enabled)
        self.stattrak_toggle.blockSignals(False)
        self.stattrak_spin.setEnabled(st_enabled)
        self.stattrak_spin.setValue(int(entry['stattrak']) if st_enabled else 0)
        self.name_edit.setText(entry['custom_name'])
        self.mesh_combo.setCurrentText(entry['mesh_group'])
        self._syncing = False
        self._update_preview()

    def draft_entry(self):
        return {
            'paint_kit': int(self.kit_spin.value()),
            'seed': int(self.seed_spin.value()),
            'wear': round(float(self.wear_spin.value()), 4),
            'stattrak': int(self.stattrak_spin.value()) if self.stattrak_toggle.isChecked() else -1,
            'custom_name': self.name_edit.text(),
            'mesh_group': self.mesh_combo.currentText(),
        }

    def _update_preview(self, *_):
        if self._syncing:
            return
        configured = str(self.selected_weapon) in self.panel.model.config.skins
        self.preview.set_state(
            self.selected_weapon,
            self.draft_entry(),
            configured,
            active_knife_override=self.panel.model.config.knife_override,
        )
        self.remove_weapon_button.setEnabled(configured)

    def _on_knife_override_changed(self, index):
        if self._syncing or index < 0:
            return
        knife_id = int(self.knife_override_combo.itemData(index) or 0)
        try:
            self.panel.model.set_knife_override(knife_id)
            self.panel.apply_timer.start()
            if knife_id:
                self.panel.message.setText(
                    f'Active knife override set to {display_weapon_name(knife_id)}. Save in Configs or sync .skin-loadout.json.'
                )
            else:
                self.panel.message.setText('Active knife override cleared (using default knife).')
            self.refresh_from_model()
        except ValueError as error:
            self.panel.message.setText(str(error))

    def _on_category_changed(self, _text):
        self._populate_weapons()
        self._load_weapon_into_editor(self.selected_weapon)

    def _on_weapon_changed(self, index):
        if self._syncing or index < 0:
            return
        weapon_id = self.weapon_combo.itemData(index)
        if weapon_id is not None:
            self._load_weapon_into_editor(int(weapon_id))

    def _on_kit_preset_changed(self, index):
        if self._syncing or index < 0:
            return
        kit_id = self.kit_combo.itemData(index)
        if kit_id is None or int(kit_id) < 0:
            return
        self._syncing = True
        self.kit_spin.setValue(int(kit_id))
        kit = kit_by_id(int(kit_id), self.selected_weapon)
        if kit is not None:
            self.mesh_combo.setCurrentText(kit.mesh_group)
        self._syncing = False
        self._update_preview()

    def _on_kit_spin_changed(self, value):
        if self._syncing:
            return
        self._syncing = True
        idx = self.kit_combo.findData(int(value))
        self.kit_combo.setCurrentIndex(idx if idx >= 0 else self.kit_combo.count() - 1)
        self._syncing = False
        self._update_preview()

    def _set_wear(self, value):
        self._syncing = True
        self.wear_spin.setValue(float(value))
        self.wear_slider.setValue(round(float(value) * 10000))
        self._syncing = False
        self._update_preview()

    def _on_wear_spin_changed(self, value):
        if self._syncing:
            return
        self._syncing = True
        self.wear_slider.setValue(round(float(value) * 10000))
        self._syncing = False
        self._update_preview()

    def _on_wear_slider_changed(self, value):
        if self._syncing:
            return
        self._syncing = True
        self.wear_spin.setValue(value / 10000.0)
        self._syncing = False
        self._update_preview()

    def _randomize_seed(self):
        self.seed_spin.setValue(random.randint(0, MAX_SEED))

    def _on_stattrak_toggled(self, checked):
        self.stattrak_spin.setEnabled(bool(checked))
        self._update_preview()

    def _on_loadout_item_clicked(self, item):
        weapon_id = item.data(Qt.ItemDataRole.UserRole)
        if weapon_id is None:
            return
        self.selected_weapon = int(weapon_id)
        if self.category_combo.currentText() != 'All':
            self.category_combo.setCurrentText('All')
        else:
            self._populate_weapons()
        self._load_weapon_into_editor(self.selected_weapon)

    def apply_current_weapon(self):
        try:
            self.panel.model.set_skin(self.selected_weapon, self.draft_entry())
            if is_custom_knife(self.selected_weapon) and self.panel.model.config.knife_override == 0:
                self.panel.model.set_knife_override(self.selected_weapon)
            self.panel.apply_timer.start()
            self.refresh_from_model()
            self.panel.message.setText(
                f'Updated {display_weapon_name(self.selected_weapon)} locally. Save in Configs or sync .skin-loadout.json.'
            )
        except ValueError as error:
            self.panel.message.setText(str(error))

    def remove_current_weapon(self):
        if self.panel.model.remove_skin(self.selected_weapon):
            self.panel.apply_timer.start()
            self._load_weapon_into_editor(self.selected_weapon)
            self.refresh_from_model()
            self.panel.message.setText(f'Removed {display_weapon_name(self.selected_weapon)} from local skin loadout.')

    def load_selected_pack(self):
        pack = self.pack_combo.currentText()
        try:
            self.panel.model.apply_skin_pack(pack)
            self.panel.apply_timer.start()
            self._load_weapon_into_editor(self.selected_weapon)
            self.refresh_from_model()
            self.panel.message.setText(f'Loaded starter pack “{pack}” (unsaved). Save in Configs or sync loadout.')
        except ValueError as error:
            self.panel.message.setText(str(error))

    def clear_all_skins(self):
        self.panel.model.clear_skins()
        self.panel.apply_timer.start()
        self._load_weapon_into_editor(self.selected_weapon)
        self.refresh_from_model()
        self.panel.message.setText('Cleared local skin loadout (unsaved).')

    def sync_loadout_file(self):
        try:
            exported = self.panel.model.export_skins()
            knife_id = self.panel.model.config.knife_override
            knife_part = f', knife {display_weapon_name(knife_id)}' if knife_id else ''
            self.panel.message.setText(
                f'Synced local skin loadout to {exported.name} ({len(self.panel.model.config.skins)} weapons{knife_part}).'
            )
        except (OSError, ValueError) as error:
            self.panel.message.setText(str(error))

    def refresh_from_model(self):
        skins = self.panel.model.config.skins
        knife_override = self.panel.model.config.knife_override
        stored = skins.get(str(self.selected_weapon))
        if stored != self._loaded_entry:
            self._load_weapon_into_editor(self.selected_weapon)
        self._syncing = True
        k_idx = self.knife_override_combo.findData(knife_override)
        self.knife_override_combo.setCurrentIndex(k_idx if k_idx >= 0 else 0)
        self._syncing = False
        state = 'enabled' if self.panel.model.config.skin_changer else 'disabled'
        knife_text = f' · knife {display_weapon_name(knife_override)}' if knife_override else ''
        self.count_label.setText(f'{len(skins)} / {MAX_SKINS} weapons configured{knife_text} · local skin changer {state}')
        self._populate_weapons()
        self.loadout_list.clear()
        for key in sorted(skins, key=int):
            weapon_id = int(key)
            entry = skins[key]
            kit = kit_by_id(entry['paint_kit'], weapon_id)
            kit_name = kit.name if kit else f'kit {entry["paint_kit"]}'
            _, short, _ = wear_tier(entry['wear'])
            st_part = f' · st {entry["stattrak"]}' if entry['stattrak'] >= 0 else ''
            eq_part = ' · equipped' if weapon_id == knife_override else ''
            item = QListWidgetItem(
                f'{display_weapon_name(weapon_id)} · {kit_name} ({short} {entry["wear"]:.3f}{st_part}{eq_part})'
            )
            item.setData(Qt.ItemDataRole.UserRole, weapon_id)
            self.loadout_list.addItem(item)
        self.clear_all_button.setEnabled(bool(skins) or knife_override != 0)
        self._update_preview()
