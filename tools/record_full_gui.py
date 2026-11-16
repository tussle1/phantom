"""Record a complete real-Qt walkthrough exercising every Phantom GUI feature.

Optional capture dependency: pip install -r requirements-gui.txt imageio-ffmpeg==0.6.0
Run: python tools/record_full_gui.py --output docs/demos/gui-full-walkthrough.mp4
All frames are genuine offscreen Qt widget renders; no game process is attached.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FPS = 30
CANVAS_W = 880
CANVAS_H = 740


def record(output):
    from unittest.mock import patch
    import imageio_ffmpeg as ff
    from PySide6.QtCore import QEvent, QPoint, QPointF, QRectF, Qt, QTimer
    from PySide6.QtGui import (
        QColor,
        QEnterEvent,
        QImage,
        QPainter,
        QPainterPath,
        QPen,
        QPolygonF,
    )
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import (
        QApplication,
        QColorDialog,
        QMessageBox,
        QPushButton,
    )
    from native.esp_style import TARGETS
    from native.gui import ControlPanel
    from native.skins import loadout_path
    from native.typography import ui_font
    from native.version import __version__

    app = QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory(prefix='phantom-full-demo-') as directory:
        panel = ControlPanel(ROOT / 'native/profiles/reference-26598758.json', directory, 'default')
        panel.menu_timer.stop()
        panel.show()
        app.processEvents()

        state = {
            'frame': 0,
            'chapter': 'overview',
            'caption': f'phantom v{__version__} · full native qt gui walkthrough',
            'error': None,
            'cursor': QPointF(CANVAS_W * 0.5, CANVAS_H * 0.45),
            'cursor_from': QPointF(CANVAS_W * 0.5, CANVAS_H * 0.45),
            'cursor_to': QPointF(CANVAS_W * 0.5, CANVAS_H * 0.45),
            'cursor_start': 0,
            'cursor_dur': 1,
            'clicks': [],  # list of (QPointF, start_frame)
            'scroll_anim': None,  # (scrollbar, start_val, end_val, start_frame, dur)
            'slider_anim': None,  # (slider, start_val, end_val, start_frame, dur)
        }
        actions = {}
        timeline = [0.0]

        def active_base():
            if hasattr(panel, 'esp_editor') and panel.esp_editor.isVisible():
                return panel.esp_editor
            return panel

        def base_origin(base):
            return QPointF((CANVAS_W - base.width()) / 2.0, 14.0)

        def widget_canvas_point(widget, local_pos=None):
            if widget is None:
                return state['cursor']
            top = widget.window()
            base = active_base()
            modal = app.activeModalWidget()
            pt = local_pos if local_pos is not None else widget.rect().center()
            mapped = widget.mapTo(top, pt)
            if modal is not None and top is modal and modal is not base:
                modal_w = min(modal.width(), CANVAS_W - 24)
                modal_h = min(modal.height(), CANVAS_H - 110)
                sx = modal_w / max(1, modal.width())
                sy = modal_h / max(1, modal.height())
                ox = (CANVAS_W - modal_w) / 2.0
                oy = 40.0
                return QPointF(ox + mapped.x() * sx, oy + mapped.y() * sy)
            orig = base_origin(base)
            return QPointF(orig.x() + mapped.x(), orig.y() + mapped.y())

        def move_cursor(target_pt, dur=8):
            state['cursor_from'] = QPointF(state['cursor'])
            state['cursor_to'] = QPointF(target_pt)
            state['cursor_start'] = state['frame']
            state['cursor_dur'] = max(1, dur)

        def register_click(pt):
            move_cursor(pt, dur=1)
            state['cursor'] = QPointF(pt)
            state['clicks'].append((QPointF(pt), state['frame']))

        def schedule(delay, chapter, caption, callback, aim_fn=None):
            t_exec = timeline[0] + delay
            timeline[0] = t_exec
            f_exec = round(t_exec * FPS)
            if aim_fn is not None and f_exec >= 9:
                f_pre = f_exec - 8
                prev = actions.get(f_pre)
                def pre_move(fn=aim_fn, prev_fn=prev):
                    if prev_fn is not None:
                        prev_fn()
                    pt = fn()
                    if pt is not None:
                        move_cursor(pt, dur=7)
                actions[f_pre] = pre_move
            prev_exec = actions.get(f_exec)
            def run(ch=chapter, cap=caption, cb=callback, prev_fn=prev_exec):
                if prev_fn is not None:
                    prev_fn()
                state['chapter'] = ch
                state['caption'] = cap
                cb()
            actions[f_exec] = run

        def ensure_visible(widget):
            if widget is not None and panel.details_scroll.isAncestorOf(widget):
                panel.details_scroll.ensureWidgetVisible(widget, 0, 56)

        def click_widget(widget, pos=None):
            ensure_visible(widget)
            pt = widget_canvas_point(widget, pos)
            register_click(pt)
            if pos is not None:
                QTest.mouseClick(widget, Qt.MouseButton.LeftButton, pos=pos)
            else:
                QTest.mouseClick(widget, Qt.MouseButton.LeftButton)

        def animate_slider(slider, target, frames=10):
            ensure_visible(slider)
            register_click(widget_canvas_point(slider))
            state['slider_anim'] = (slider, slider.value(), int(target), state['frame'], frames)

        def animate_scroll(ratio, frames=14):
            sb = panel.details_scroll.verticalScrollBar()
            target = round(sb.maximum() * ratio)
            state['scroll_anim'] = (sb, sb.value(), target, state['frame'], frames)

        def esp_button(text):
            return next(w for w in panel.esp_editor.findChildren(QPushButton) if w.text().lower() == text)

        def config_button(text):
            return next(w for w in panel.details.findChildren(QPushButton) if w.text().lower() == text)

        def modal_picker():
            dialog = app.activeModalWidget()
            if not isinstance(dialog, QColorDialog):
                raise RuntimeError('Expected a real QColorDialog.')
            return dialog

        def modal_message():
            dialog = app.activeModalWidget()
            if not isinstance(dialog, QMessageBox):
                raise RuntimeError('Expected a real QMessageBox.')
            return dialog

        def confirm_modal_yes():
            modal = modal_message()
            pt = widget_canvas_point(modal, QPoint(round(modal.width() * 0.68), modal.height() - 24))
            register_click(pt)
            QTest.keyClick(modal, Qt.Key.Key_Y)

        # ── 1. MAIN OVERVIEW CONTROLS ──────────────────────────────────────
        schedule(1.0, 'overview', 'main sliders · drag aim fov to 6.5°',
                 lambda: animate_slider(panel.sliders['aim_fov'].slider, 65),
                 aim_fn=lambda: widget_canvas_point(panel.sliders['aim_fov'].slider))
        schedule(0.85, 'overview', 'main sliders · adjust smoothing to 220 ms',
                 lambda: animate_slider(panel.sliders['smooth_time'].slider, 220),
                 aim_fn=lambda: widget_canvas_point(panel.sliders['smooth_time'].slider))
        schedule(0.85, 'overview', 'main sliders · set prediction look-ahead to 35 ms',
                 lambda: animate_slider(panel.sliders['prediction_ms'].slider, 35),
                 aim_fn=lambda: widget_canvas_point(panel.sliders['prediction_ms'].slider))
        schedule(0.85, 'overview', 'main sliders · tune trigger shot delay to 80 ms',
                 lambda: animate_slider(panel.sliders['trigger_delay_ms'].slider, 80),
                 aim_fn=lambda: widget_canvas_point(panel.sliders['trigger_delay_ms'].slider))
        schedule(0.85, 'overview', 'per-slider reset · restore default aim fov',
                 lambda: click_widget(panel.sliders['aim_fov'].findChild(QPushButton)),
                 aim_fn=lambda: widget_canvas_point(panel.sliders['aim_fov'].findChild(QPushButton)))
        schedule(0.8, 'overview', 'overview pills · toggle esp overlay off then on',
                 lambda: click_widget(panel.toggles['esp']),
                 aim_fn=lambda: widget_canvas_point(panel.toggles['esp']))
        schedule(0.6, 'overview', 'overview pills · esp overlay back on',
                 lambda: click_widget(panel.toggles['esp']),
                 aim_fn=lambda: widget_canvas_point(panel.toggles['esp']))
        schedule(0.65, 'overview', 'overview pills · toggle aim assist on',
                 lambda: click_widget(panel.toggles['aim']),
                 aim_fn=lambda: widget_canvas_point(panel.toggles['aim']))
        schedule(0.65, 'overview', 'overview pills · toggle trigger assist on',
                 lambda: click_widget(panel.toggles['trigger']),
                 aim_fn=lambda: widget_canvas_point(panel.toggles['trigger']))
        schedule(0.7, 'overview', 'overview pills · return aim and trigger off for safe demo',
                 lambda: (click_widget(panel.toggles['aim']), QTest.mouseClick(panel.toggles['trigger'], Qt.MouseButton.LeftButton)),
                 aim_fn=lambda: widget_canvas_point(panel.toggles['aim']))

        # ── 2. VISUALS TAB ─────────────────────────────────────────────────
        schedule(0.9, 'visuals', 'visuals tab · overlay display toggles & range',
                 lambda: click_widget(panel.tab_buttons['Visuals']),
                 aim_fn=lambda: widget_canvas_point(panel.tab_buttons['Visuals']))
        for key, label in [('skeleton', 'skeleton'), ('health', 'health bars'),
                           ('armor', 'armor bars'), ('teammates', 'show teammates'),
                           ('radar', 'circular radar'), ('spectators', 'spectator list')]:
            schedule(0.6, 'visuals', f'visuals · toggle {label}',
                     lambda k=key: click_widget(panel.toggles[k]),
                     aim_fn=lambda k=key: widget_canvas_point(panel.toggles[k]))
        schedule(0.6, 'visuals', 'visuals · restore skeleton, health & armor',
                 lambda: (click_widget(panel.toggles['skeleton']),
                          QTest.mouseClick(panel.toggles['health'], Qt.MouseButton.LeftButton),
                          QTest.mouseClick(panel.toggles['armor'], Qt.MouseButton.LeftButton)),
                 aim_fn=lambda: widget_canvas_point(panel.toggles['skeleton']))
        schedule(0.8, 'visuals', 'visuals · extend esp range to 360 m',
                 lambda: animate_slider(panel.sliders['max_distance_m'].slider, 360),
                 aim_fn=lambda: widget_canvas_point(panel.sliders['max_distance_m'].slider))

        # ── 3. INTERACTIVE SKELETON ESP DESIGNER ───────────────────────────
        schedule(1.0, 'esp designer', 'open interactive skeleton esp designer dialog',
                 lambda: click_widget(panel.editor_button),
                 aim_fn=lambda: widget_canvas_point(panel.editor_button))

        def click_esp_target(name):
            x, y = panel.esp_editor.preview.points()[name]
            click_widget(panel.esp_editor.preview, QPoint(round(x), round(y)))

        for name in TARGETS:
            schedule(0.75, 'esp designer', f'skeleton designer · click aim target: {name}',
                     lambda n=name: click_esp_target(n),
                     aim_fn=lambda n=name: widget_canvas_point(
                         panel.esp_editor.preview,
                         QPoint(round(panel.esp_editor.preview.points()[n][0]),
                                round(panel.esp_editor.preview.points()[n][1]))))

        schedule(0.75, 'esp designer', 'skeleton designer · keyboard shortcut 1 selects head',
                 lambda: (panel.esp_editor.preview.setFocus(),
                          QTest.keyClick(panel.esp_editor.preview, Qt.Key.Key_1)))

        def click_check(w):
            click_widget(w, QPoint(10, w.height() // 2))

        for key, lbl in [('box', 'bounding box'), ('names', 'player name'), ('distance', 'distance label')]:
            schedule(0.65, 'esp designer', f'skeleton designer · toggle {lbl}',
                     lambda k=key: click_check(panel.esp_editor.style_checks[k]),
                     aim_fn=lambda k=key: widget_canvas_point(panel.esp_editor.style_checks[k], QPoint(10, 10)))
        schedule(0.7, 'esp designer', 'skeleton designer · switch box style to corner',
                 lambda: (register_click(widget_canvas_point(panel.esp_editor.box_style_combo)),
                          panel.esp_editor.box_style_combo.setCurrentText('corner')),
                 aim_fn=lambda: widget_canvas_point(panel.esp_editor.box_style_combo))
        schedule(0.7, 'esp designer', 'skeleton designer · increase line width to 3 px',
                 lambda: (register_click(widget_canvas_point(panel.esp_editor.width_combo)),
                          panel.esp_editor.width_combo.setCurrentText('3')),
                 aim_fn=lambda: widget_canvas_point(panel.esp_editor.width_combo))
        schedule(0.75, 'esp designer', 'skeleton designer · preview unspotted enemy sample',
                 lambda: (register_click(widget_canvas_point(panel.esp_editor.sample_combo)),
                          panel.esp_editor.sample_combo.setCurrentText('unspotted enemy')),
                 aim_fn=lambda: widget_canvas_point(panel.esp_editor.sample_combo))
        schedule(0.75, 'esp designer', 'skeleton designer · preview teammate sample',
                 lambda: (register_click(widget_canvas_point(panel.esp_editor.sample_combo)),
                          panel.esp_editor.sample_combo.setCurrentText('teammate')),
                 aim_fn=lambda: widget_canvas_point(panel.esp_editor.sample_combo))
        schedule(0.75, 'esp designer', 'skeleton designer · return to spotted enemy sample',
                 lambda: (register_click(widget_canvas_point(panel.esp_editor.sample_combo)),
                          panel.esp_editor.sample_combo.setCurrentText('spotted enemy')),
                 aim_fn=lambda: widget_canvas_point(panel.esp_editor.sample_combo))
        schedule(0.8, 'esp designer', 'skeleton designer · open real qt color picker for spotted enemy',
                 lambda: (register_click(widget_canvas_point(panel.esp_editor.color_buttons['visible_color'][0])),
                          panel.esp_editor.color_buttons['visible_color'][0].click()),
                 aim_fn=lambda: widget_canvas_point(panel.esp_editor.color_buttons['visible_color'][0]))
        schedule(0.9, 'esp designer', 'color picker · choose vivid pink #fc589b',
                 lambda: modal_picker().setCurrentColor(QColor('#fc589b')))
        schedule(0.8, 'esp designer', 'color picker · accept custom spotted color',
                 lambda: modal_picker().accept())
        schedule(0.85, 'esp designer', 'skeleton designer · test reserved pure black rejection',
                 lambda: (register_click(widget_canvas_point(panel.esp_editor.color_buttons['visible_color'][0])),
                          panel.esp_editor.color_buttons['visible_color'][0].click()),
                 aim_fn=lambda: widget_canvas_point(panel.esp_editor.color_buttons['visible_color'][0]))
        schedule(0.8, 'esp designer', 'color picker · black #000000 is rejected to protect transparency',
                 lambda: modal_picker().setCurrentColor(QColor('#000000')))
        schedule(0.75, 'esp designer', 'color picker · valid pink preserved after rejection',
                 lambda: modal_picker().accept())
        schedule(0.8, 'esp designer', 'skeleton designer · close designer & return to panel',
                 lambda: click_widget(esp_button('done')),
                 aim_fn=lambda: widget_canvas_point(esp_button('done')))

        # ── 4. AIM TAB ─────────────────────────────────────────────────────
        schedule(0.9, 'aim', 'aim tab · modes, fov ring, priority bone & curve tuning',
                 lambda: click_widget(panel.tab_buttons['Aim']),
                 aim_fn=lambda: widget_canvas_point(panel.tab_buttons['Aim']))
        for mode in ('smooth', 'hardlock', 'catalyst', 'smooth'):
            schedule(0.75, 'aim', f'aim mode · select {mode}',
                     lambda m=mode: (register_click(widget_canvas_point(panel.combos['aim'])),
                                     panel.combos['aim'].setCurrentText(m)),
                     aim_fn=lambda: widget_canvas_point(panel.combos['aim']))
        schedule(0.75, 'aim', 'aim · enable projected aim fov ring',
                 lambda: click_widget(panel.toggles['aim_draw_fov']),
                 aim_fn=lambda: widget_canvas_point(panel.toggles['aim_draw_fov']))
        for bone in ('neck', 'chest', 'head'):
            schedule(0.6, 'aim', f'aim · set priority bone to {bone}',
                     lambda b=bone: (register_click(widget_canvas_point(panel.combos['priority_bone'])),
                                     panel.combos['priority_bone'].setCurrentText(b)),
                     aim_fn=lambda: widget_canvas_point(panel.combos['priority_bone']))
        schedule(0.75, 'aim', 'aim · raise max aim speed to 180°/s',
                 lambda: animate_slider(panel.sliders['max_aim_speed'].slider, 180),
                 aim_fn=lambda: widget_canvas_point(panel.sliders['max_aim_speed'].slider))
        schedule(0.8, 'aim', 'aim · adjust catalyst smoothing to 18',
                 lambda: animate_slider(panel.sliders['catalyst_smoothing'].slider, 18),
                 aim_fn=lambda: widget_canvas_point(panel.sliders['catalyst_smoothing'].slider))
        schedule(0.7, 'aim', 'aim · turn aim mode back off',
                 lambda: (register_click(widget_canvas_point(panel.combos['aim'])),
                          panel.combos['aim'].setCurrentText('off')),
                 aim_fn=lambda: widget_canvas_point(panel.combos['aim']))

        # ── 5. SKINS TAB (LOCAL SKIN CHANGER) ──────────────────────────────
        schedule(1.0, 'local skin changer', 'skins tab · local client-side cs2 weapon skin changer',
                 lambda: click_widget(panel.tab_buttons['Skins']),
                 aim_fn=lambda: widget_canvas_point(panel.tab_buttons['Skins']))
        schedule(0.9, 'local skin changer', 'skins · enable local skin changer',
                 lambda: click_widget(panel.skin_panel.enable_toggle),
                 aim_fn=lambda: widget_canvas_point(panel.skin_panel.enable_toggle))
        schedule(0.9, 'local skin changer', 'skins · scroll to starter packs & load phantom neon',
                 lambda: animate_scroll(1.0, frames=14))
        schedule(0.85, 'local skin changer', 'skins · click load pack (populates 8 curated weapons)',
                 lambda: click_widget(panel.skin_panel.load_pack_button),
                 aim_fn=lambda: widget_canvas_point(panel.skin_panel.load_pack_button))
        schedule(1.0, 'local skin changer', 'skins · scroll back up to live finish preview card',
                 lambda: animate_scroll(0.0, frames=14))
        schedule(1.1, 'local skin changer', 'skins · browse weapon categories → rifles',
                 lambda: (register_click(widget_canvas_point(panel.skin_panel.category_combo)),
                          panel.skin_panel.category_combo.setCurrentText('Rifles')),
                 aim_fn=lambda: widget_canvas_point(panel.skin_panel.category_combo))

        def pick_weapon_id(wid):
            sp = panel.skin_panel
            idx = sp.weapon_combo.findData(wid)
            if idx >= 0:
                register_click(widget_canvas_point(sp.weapon_combo))
                sp.weapon_combo.setCurrentIndex(idx)

        def pick_kit_id(kid):
            sp = panel.skin_panel
            idx = sp.kit_combo.findData(kid)
            if idx >= 0:
                register_click(widget_canvas_point(sp.kit_combo))
                sp.kit_combo.setCurrentIndex(idx)

        schedule(0.85, 'local skin changer', 'skins · select awp & preview dragon lore',
                 lambda: pick_weapon_id(9),
                 aim_fn=lambda: widget_canvas_point(panel.skin_panel.weapon_combo))
        schedule(0.85, 'local skin changer', 'skins · apply awp · dragon lore (kit 344)',
                 lambda: pick_kit_id(344),
                 aim_fn=lambda: widget_canvas_point(panel.skin_panel.kit_combo))
        schedule(0.9, 'local skin changer', 'skins · browse knives category → karambit fade',
                 lambda: (register_click(widget_canvas_point(panel.skin_panel.category_combo)),
                          panel.skin_panel.category_combo.setCurrentText('Knives')),
                 aim_fn=lambda: widget_canvas_point(panel.skin_panel.category_combo))
        schedule(0.85, 'local skin changer', 'skins · select karambit (#507)',
                 lambda: pick_weapon_id(507),
                 aim_fn=lambda: widget_canvas_point(panel.skin_panel.weapon_combo))
        schedule(0.85, 'local skin changer', 'skins · choose fade finish (covert gradient)',
                 lambda: pick_kit_id(38),
                 aim_fn=lambda: widget_canvas_point(panel.skin_panel.kit_combo))
        schedule(0.85, 'local skin changer', 'skins · try doppler phase finish',
                 lambda: pick_kit_id(415),
                 aim_fn=lambda: widget_canvas_point(panel.skin_panel.kit_combo))
        schedule(0.85, 'local skin changer', 'skins · return to all weapons & select ak-47',
                 lambda: (panel.skin_panel.category_combo.setCurrentText('All'), pick_weapon_id(7)),
                 aim_fn=lambda: widget_canvas_point(panel.skin_panel.category_combo))
        schedule(0.85, 'local skin changer', 'skins · enter paint kit id 282 (ak-47 redline)',
                 lambda: (register_click(widget_canvas_point(panel.skin_panel.kit_spin)),
                          panel.skin_panel.kit_spin.setValue(282)),
                 aim_fn=lambda: widget_canvas_point(panel.skin_panel.kit_spin))
        schedule(0.9, 'local skin changer', 'skins · scroll to wear float, pattern seed, stattrak & nametag',
                 lambda: animate_scroll(0.48, frames=14))
        for tier, label in [('MW', 'minimal wear'), ('FT', 'field-tested'),
                            ('WW', 'well-worn'), ('BS', 'battle-scarred'), ('FN', 'factory new')]:
            schedule(0.65, 'local skin changer', f'skins · wear preset chip → {label} ({tier.lower()})',
                     lambda t=tier: click_widget(panel.skin_panel.wear_buttons[t]),
                     aim_fn=lambda t=tier: widget_canvas_point(panel.skin_panel.wear_buttons[t]))
        schedule(0.75, 'local skin changer', 'skins · fine-tune wear float slider to 0.1500',
                 lambda: animate_slider(panel.skin_panel.wear_slider, 1500, frames=10),
                 aim_fn=lambda: widget_canvas_point(panel.skin_panel.wear_slider))
        schedule(0.8, 'local skin changer', 'skins · click random pattern seed generator',
                 lambda: click_widget(panel.skin_panel.random_seed_button),
                 aim_fn=lambda: widget_canvas_point(panel.skin_panel.random_seed_button))
        schedule(0.75, 'local skin changer', 'skins · set stattrak kill counter to 2026',
                 lambda: (register_click(widget_canvas_point(panel.skin_panel.stattrak_spin)),
                          panel.skin_panel.stattrak_spin.setValue(2026)),
                 aim_fn=lambda: widget_canvas_point(panel.skin_panel.stattrak_spin))
        schedule(0.8, 'local skin changer', 'skins · type custom local nametag "phantom ace"',
                 lambda: (register_click(widget_canvas_point(panel.skin_panel.name_edit)),
                          panel.skin_panel.name_edit.setText('phantom ace')),
                 aim_fn=lambda: widget_canvas_point(panel.skin_panel.name_edit))
        schedule(0.75, 'local skin changer', 'skins · switch model mesh group (modern → legacy)',
                 lambda: (register_click(widget_canvas_point(panel.skin_panel.mesh_combo)),
                          panel.skin_panel.mesh_combo.setCurrentText('modern'),
                          panel.skin_panel.mesh_combo.setCurrentText('legacy')),
                 aim_fn=lambda: widget_canvas_point(panel.skin_panel.mesh_combo))
        schedule(0.85, 'local skin changer', 'skins · click apply to weapon',
                 lambda: click_widget(panel.skin_panel.apply_weapon_button),
                 aim_fn=lambda: widget_canvas_point(panel.skin_panel.apply_weapon_button))
        schedule(0.85, 'local skin changer', 'skins · scroll up to verify updated ak-47 preview card',
                 lambda: animate_scroll(0.0, frames=12))
        schedule(1.15, 'local skin changer', 'skins · scroll to active loadout & local export bridge',
                 lambda: animate_scroll(1.0, frames=14))
        schedule(0.85, 'local skin changer', 'skins · select weapon directly from active loadout list',
                 lambda: (register_click(widget_canvas_point(panel.skin_panel.loadout_list)),
                          panel.skin_panel.loadout_list.setCurrentRow(0),
                          panel.skin_panel._on_loadout_item_clicked(panel.skin_panel.loadout_list.item(0))),
                 aim_fn=lambda: widget_canvas_point(panel.skin_panel.loadout_list))
        schedule(0.85, 'local skin changer', 'skins · switch pack to classic covert & load pack',
                 lambda: (panel.skin_panel.pack_combo.setCurrentText('classic covert'),
                          click_widget(panel.skin_panel.load_pack_button)),
                 aim_fn=lambda: widget_canvas_point(panel.skin_panel.load_pack_button))
        schedule(0.85, 'local skin changer', 'skins · click sync .skin-loadout.json for c++ foundation',
                 lambda: (click_widget(panel.skin_panel.export_button),
                          assert_true(loadout_path(directory).is_file())),
                 aim_fn=lambda: widget_canvas_point(panel.skin_panel.export_button))

        # ── 6. INPUT & KEYBIND CAPTURE ─────────────────────────────────────
        schedule(1.1, 'input & keybinds', 'input tab · movement & live keybind capture',
                 lambda: click_widget(panel.tab_buttons['Input']),
                 aim_fn=lambda: widget_canvas_point(panel.tab_buttons['Input']))
        schedule(0.8, 'input & keybinds', 'input · toggle bunny hop on',
                 lambda: click_widget(panel.toggles['bunny_hop']),
                 aim_fn=lambda: widget_canvas_point(panel.toggles['bunny_hop']))
        schedule(0.7, 'input & keybinds', 'input · toggle bunny hop back off',
                 lambda: click_widget(panel.toggles['bunny_hop']),
                 aim_fn=lambda: widget_canvas_point(panel.toggles['bunny_hop']))
        schedule(0.8, 'input & keybinds', 'input · click hold aim binding to enter capture mode',
                 lambda: click_widget(panel.binding_buttons['aim_hold']),
                 aim_fn=lambda: widget_canvas_point(panel.binding_buttons['aim_hold']))
        schedule(0.8, 'input & keybinds', 'input · press f4 to rebind hold aim live',
                 lambda: QTest.keyClick(panel.binding_buttons['aim_hold'], Qt.Key.Key_F4))
        schedule(0.8, 'input & keybinds', 'input · click menu toggle then press escape to cancel',
                 lambda: click_widget(panel.binding_buttons['menu_toggle']),
                 aim_fn=lambda: widget_canvas_point(panel.binding_buttons['menu_toggle']))
        schedule(0.75, 'input & keybinds', 'input · escape cancels capture without changing binding',
                 lambda: QTest.keyClick(panel.binding_buttons['menu_toggle'], Qt.Key.Key_Escape))

        # ── 7. CONFIGS & BUILT-IN PRESETS ──────────────────────────────────
        schedule(1.0, 'configs & presets', 'configs tab · built-in presets, save/load & offset profile',
                 lambda: click_widget(panel.tab_buttons['Configs']),
                 aim_fn=lambda: widget_canvas_point(panel.tab_buttons['Configs']))
        schedule(0.8, 'configs & presets', 'presets · select combined practice preset',
                 lambda: (register_click(widget_canvas_point(panel.preset_combo)),
                          panel.preset_combo.setCurrentText('combined practice')),
                 aim_fn=lambda: widget_canvas_point(panel.preset_combo))
        schedule(0.85, 'configs & presets', 'presets · click apply preset (real confirmation dialog)',
                 lambda: (register_click(widget_canvas_point(panel.preset_apply_button)),
                          panel.preset_apply_button.click()),
                 aim_fn=lambda: widget_canvas_point(panel.preset_apply_button))
        schedule(0.95, 'configs & presets', 'presets · confirm — keybinds & local skin loadout preserved',
                 confirm_modal_yes)
        schedule(0.85, 'configs & presets', 'configs · name & save local configuration "showcase-demo"',
                 lambda: (panel.name_edit.setText('showcase-demo'),
                          click_widget(config_button('save named config'))),
                 aim_fn=lambda: widget_canvas_point(config_button('save named config')))
        schedule(0.9, 'configs & presets', 'configs · load saved configuration with confirmation',
                 lambda: (panel.saved_combo.setCurrentText('showcase-demo'),
                          register_click(widget_canvas_point(config_button('load'))),
                          config_button('load').click()),
                 aim_fn=lambda: widget_canvas_point(config_button('load')))
        schedule(0.85, 'configs & presets', 'configs · confirm loading "showcase-demo"',
                 confirm_modal_yes)

        # ── 8. APPEARANCE & LIVE THEMING ───────────────────────────────────
        schedule(1.0, 'appearance', 'appearance · live color themes, accent picker & layout density',
                 lambda: click_widget(panel.appearance_button),
                 aim_fn=lambda: widget_canvas_point(panel.appearance_button))
        for theme_name in ('midnight', 'slate', 'forest'):
            schedule(0.95, 'appearance', f'theme preset · {theme_name} live palette',
                     lambda t=theme_name: (register_click(widget_canvas_point(panel.theme_combo)),
                                           panel.theme_combo.setCurrentText(t)),
                     aim_fn=lambda: widget_canvas_point(panel.theme_combo))
        schedule(1.0, 'appearance', 'theme propagation · skins preview card adapts live to forest theme',
                 lambda: click_widget(panel.tab_buttons['Skins']),
                 aim_fn=lambda: widget_canvas_point(panel.tab_buttons['Skins']))
        schedule(1.2, 'appearance', 'appearance · return & preview light theme',
                 lambda: (click_widget(panel.appearance_button), panel.theme_combo.setCurrentText('light')),
                 aim_fn=lambda: widget_canvas_point(panel.appearance_button))
        schedule(1.0, 'appearance', 'appearance · open real qt color picker for custom accent',
                 lambda: (register_click(widget_canvas_point(panel.color_buttons['accent'])),
                          panel.color_buttons['accent'].click()),
                 aim_fn=lambda: widget_canvas_point(panel.color_buttons['accent']))
        schedule(0.85, 'appearance', 'color picker · pick custom violet accent #7c4dff',
                 lambda: modal_picker().setCurrentColor(QColor('#7c4dff')))
        schedule(0.75, 'appearance', 'color picker · accept custom accent color',
                 lambda: modal_picker().accept())
        schedule(0.85, 'appearance', 'appearance · compact layout density preview',
                 lambda: (register_click(widget_canvas_point(panel.appearance_controls['spacing'])),
                          panel.appearance_controls['spacing'].setCurrentText('compact')),
                 aim_fn=lambda: widget_canvas_point(panel.appearance_controls['spacing']))
        schedule(0.9, 'appearance', 'appearance · reset back to default phantom purple theme',
                 lambda: click_widget(config_button('reset appearance')),
                 aim_fn=lambda: widget_canvas_point(config_button('reset appearance')))
        schedule(0.85, 'appearance', 'appearance · save appearance preferences locally',
                 lambda: click_widget(config_button('save appearance')),
                 aim_fn=lambda: widget_canvas_point(config_button('save appearance')))

        # ── 9. COMPACT MODE, HOVERS & FOOTER CONTROLS ──────────────────────
        schedule(0.9, 'compact & footer', 'skins tab · show final configured neon loadout',
                 lambda: click_widget(panel.tab_buttons['Skins']),
                 aim_fn=lambda: widget_canvas_point(panel.tab_buttons['Skins']))
        schedule(1.0, 'compact & footer', 'collapse to compact 440 px overview panel',
                 lambda: click_widget(panel.more),
                 aim_fn=lambda: widget_canvas_point(panel.more))
        schedule(1.1, 'compact & footer', 'expand back to full horizontal workspace',
                 lambda: click_widget(panel.more),
                 aim_fn=lambda: widget_canvas_point(panel.more))

        def hover_button(btn, enter):
            c = QPointF(btn.rect().center())
            if enter:
                move_cursor(widget_canvas_point(btn), dur=6)
            app.sendEvent(btn, QEnterEvent(c, c, c) if enter else QEvent(QEvent.Type.Leave))

        schedule(0.9, 'compact & footer', 'animated facet button hover · stop runtime',
                 lambda: hover_button(panel.stop_button, True))
        schedule(0.75, 'compact & footer', 'animated facet button hover · start runtime',
                 lambda: (hover_button(panel.stop_button, False), hover_button(panel.start_button, True)))
        schedule(0.85, 'compact & footer', 'start runtime · safely gated outside 64-bit windows',
                 lambda: click_widget(panel.start_button),
                 aim_fn=lambda: widget_canvas_point(panel.start_button))
        schedule(1.5, 'complete', f'phantom v{__version__} · every gui feature verified in real qt',
                 lambda: hover_button(panel.start_button, False))

        total_frames = round((timeline[0] + 1.5) * FPS)

        def assert_true(cond):
            if not cond:
                raise AssertionError('Expected condition failed during demo.')

        output = Path(output).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        command = [
            ff.get_ffmpeg_exe(), '-hide_banner', '-loglevel', 'error', '-y',
            '-f', 'rawvideo', '-pixel_format', 'rgba',
            '-video_size', f'{CANVAS_W}x{CANVAS_H}',
            '-framerate', str(FPS), '-i', '-', '-an',
            '-c:v', 'libx264', '-preset', 'medium', '-crf', '20',
            '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(output),
        ]

        real_get_color = QColorDialog.getColor

        def qt_picker(initial, parent, title):
            return real_get_color(initial, parent, title, options=QColorDialog.ColorDialogOption.DontUseNativeDialog)

        def draw_cursor(painter, pt):
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            poly = QPolygonF([
                QPointF(pt.x(), pt.y()),
                QPointF(pt.x(), pt.y() + 17),
                QPointF(pt.x() + 4.5, pt.y() + 13),
                QPointF(pt.x() + 8.5, pt.y() + 20),
                QPointF(pt.x() + 11.2, pt.y() + 18.5),
                QPointF(pt.x() + 7.2, pt.y() + 11.8),
                QPointF(pt.x() + 13, pt.y() + 11.5),
            ])
            painter.setPen(QPen(QColor('#17131f'), 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            painter.setBrush(QColor('#ffffff'))
            painter.drawPolygon(poly)
            painter.restore()

        with tempfile.TemporaryFile() as errors:
            encoder = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=errors)
            timer = QTimer()
            timer.setTimerType(Qt.TimerType.PreciseTimer)
            timer.setInterval(33)

            def finish():
                timer.stop()
                modal = app.activeModalWidget()
                if modal is not None and modal is not getattr(panel, 'esp_editor', None):
                    modal.reject()
                if hasattr(panel, 'esp_editor') and panel.esp_editor.isVisible():
                    panel.esp_editor.close()
                panel.close()
                app.quit()

            def invoke(fn):
                try:
                    fn()
                except Exception as error:
                    import traceback
                    state['error'] = traceback.format_exc()
                    finish()

            def step_frame():
                try:
                    idx = state['frame']
                    if idx >= total_frames:
                        finish()
                        return
                    if idx in actions:
                        QTimer.singleShot(0, lambda fn=actions[idx]: invoke(fn))

                    # Update smooth scroll & slider animations.
                    if state['scroll_anim'] is not None:
                        sb, v0, v1, s0, dur = state['scroll_anim']
                        t = min(1.0, (idx - s0) / max(1, dur))
                        eased = 1.0 - (1.0 - t) ** 3
                        sb.setValue(round(v0 + (v1 - v0) * eased))
                        if t >= 1.0:
                            state['scroll_anim'] = None
                    if state['slider_anim'] is not None:
                        sl, v0, v1, s0, dur = state['slider_anim']
                        t = min(1.0, (idx - s0) / max(1, dur))
                        eased = 1.0 - (1.0 - t) ** 3
                        sl.setValue(round(v0 + (v1 - v0) * eased))
                        if t >= 1.0:
                            state['slider_anim'] = None

                    # Update smooth cursor motion.
                    ct = min(1.0, (idx - state['cursor_start']) / max(1, state['cursor_dur']))
                    ce = 1.0 - (1.0 - ct) ** 3
                    c0, c1 = state['cursor_from'], state['cursor_to']
                    state['cursor'] = QPointF(c0.x() + (c1.x() - c0.x()) * ce,
                                              c0.y() + (c1.y() - c0.y()) * ce)

                    canvas = QImage(CANVAS_W, CANVAS_H, QImage.Format.Format_RGBA8888)
                    canvas.fill(QColor('#120e19'))
                    painter = QPainter(canvas)
                    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

                    base = active_base()
                    shot = base.grab()
                    orig = base_origin(base)
                    bx, by = round(orig.x()), round(orig.y())
                    # Soft border frame around the active Qt window.
                    painter.setPen(QPen(QColor('#3a304a'), 1.5))
                    painter.setBrush(QColor('#1c1726'))
                    painter.drawRoundedRect(QRectF(bx - 1, by - 1, shot.width() + 2, shot.height() + 2), 6, 6)
                    painter.drawPixmap(bx, by, shot)

                    modal = app.activeModalWidget()
                    if modal is not None and modal is not base:
                        painter.fillRect(0, 0, CANVAS_W, CANVAS_H - 78, QColor(12, 9, 18, 125))
                        dshot = modal.grab()
                        if dshot.width() > CANVAS_W - 24 or dshot.height() > CANVAS_H - 110:
                            dshot = dshot.scaled(CANVAS_W - 24, CANVAS_H - 110,
                                                 Qt.AspectRatioMode.KeepAspectRatio,
                                                 Qt.TransformationMode.SmoothTransformation)
                        dx = (CANVAS_W - dshot.width()) // 2
                        dy = 40
                        painter.setPen(QPen(QColor('#fc589b'), 1.4))
                        painter.drawRoundedRect(QRectF(dx - 1, dy - 1, dshot.width() + 2, dshot.height() + 2), 5, 5)
                        painter.drawPixmap(dx, dy, dshot)

                    # Click ripple rings.
                    alive = []
                    for pt, began in state['clicks']:
                        age = idx - began
                        if 0 <= age < 14:
                            alpha = round(230 * (1.0 - age / 14.0))
                            painter.setBrush(Qt.BrushStyle.NoBrush)
                            painter.setPen(QPen(QColor(252, 88, 155, alpha), 2.2))
                            r = 9.0 + age * 1.4
                            painter.drawEllipse(pt, r, r)
                            alive.append((pt, began))
                    state['clicks'] = alive

                    draw_cursor(painter, state['cursor'])

                    # Clean footer bar with chapter pill + caption + subtle progress bar.
                    footer_y = CANVAS_H - 72
                    painter.fillRect(0, footer_y, CANVAS_W, 72, QColor('#181322'))
                    painter.setPen(QPen(QColor('#2d243c'), 1))
                    painter.drawLine(0, footer_y, CANVAS_W, footer_y)

                    # Progress hairline along top of footer.
                    prog_w = CANVAS_W * (idx / max(1, total_frames - 1))
                    painter.fillRect(QRectF(0, footer_y, prog_w, 2.5), QColor('#fc589b'))

                    # Chapter badge.
                    badge_rect = QRectF(20, footer_y + 14, 146, 22)
                    painter.setPen(QPen(QColor('#fc589b'), 1.0))
                    painter.setBrush(QColor(252, 88, 155, 36))
                    painter.drawRoundedRect(badge_rect, 11, 11)
                    painter.setPen(QColor('#ffd8ea'))
                    painter.setFont(ui_font(8))
                    painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, state['chapter'])

                    # Main caption text.
                    painter.setPen(QColor('#efe8f8'))
                    painter.setFont(ui_font(11))
                    painter.drawText(QRectF(178, footer_y + 10, CANVAS_W - 196, 28),
                                     Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                                     state['caption'])

                    # Subtitle line.
                    painter.setPen(QColor('#9284ac'))
                    painter.setFont(ui_font(8))
                    elapsed = idx / FPS
                    total_s = total_frames / FPS
                    painter.drawText(QRectF(20, footer_y + 42, CANVAS_W - 40, 22),
                                     Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                                     f'phantom v{__version__} · genuine offscreen qt6 widgets · isolated temp config · no game connection')
                    painter.drawText(QRectF(20, footer_y + 42, CANVAS_W - 40, 22),
                                     Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                                     f'{elapsed:04.1f}s / {total_s:04.1f}s')

                    painter.end()
                    encoder.stdin.write(bytes(canvas.constBits()))
                    state['frame'] += 1
                except Exception as error:
                    state['error'] = error
                    finish()

            timer.timeout.connect(step_frame)
            with patch.object(QColorDialog, 'getColor', side_effect=qt_picker):
                timer.start()
                app.exec()
            encoder.stdin.close()
            try:
                code = encoder.wait(timeout=120)
            except subprocess.TimeoutExpired:
                encoder.kill()
                encoder.wait()
                raise RuntimeError('Video encoder timed out.')
            errors.seek(0)
            diag = errors.read().decode(errors='replace')
            if state['error'] is not None or code or state['frame'] != total_frames:
                output.unlink(missing_ok=True)
                raise RuntimeError(
                    f'Full GUI recording failed at frame {state["frame"]}/{total_frames}: {state["error"]}; {diag}'
                )
        secs = total_frames / FPS
        size_kb = output.stat().st_size / 1024.0
        print(f'{output}: {total_frames} actual Qt frames, {FPS} fps, {secs:.1f}s, {CANVAS_W}x{CANVAS_H}, {size_kb:.0f} KB')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='docs/demos/gui-full-walkthrough.mp4')
    record(parser.parse_args().output)
