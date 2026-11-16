"""Record a focused real-Qt walkthrough of the Phantom CS2 Knife Skin Changer GUI.

Optional capture dependency: pip install -r requirements-gui.txt imageio-ffmpeg==0.6.0
Run: python tools/record_knife_gui.py --output docs/demos/knife-skin-changer.mp4
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
    import imageio_ffmpeg as ff
    from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
    from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPolygonF
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from native.gui import ControlPanel
    from native.skins import loadout_path
    from native.typography import ui_font
    from native.version import __version__

    app = QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory(prefix='phantom-knife-demo-') as directory:
        panel = ControlPanel(ROOT / 'native/profiles/reference-26598758.json', directory, 'default')
        panel.menu_timer.stop()
        panel.show()
        app.processEvents()
        # Open directly on the Skins tab — knife skin changer only.
        panel.select_page('Skins')
        app.processEvents()

        state = {
            'frame': 0,
            'chapter': 'knife skins',
            'caption': 'local cs2 knife skin changer · all 20 knives + 36 curated finishes',
            'error': None,
            'cursor': QPointF(CANVAS_W * 0.68, CANVAS_H * 0.24),
            'cursor_from': QPointF(CANVAS_W * 0.68, CANVAS_H * 0.24),
            'cursor_to': QPointF(CANVAS_W * 0.68, CANVAS_H * 0.24),
            'cursor_start': 0,
            'cursor_dur': 1,
            'clicks': [],
            'scroll_anim': None,
            'slider_anim': None,
        }
        actions = {}
        timeline = [0.0]

        def base_origin():
            return QPointF((CANVAS_W - panel.width()) / 2.0, 14.0)

        def widget_canvas_point(widget, local_pos=None):
            if widget is None:
                return state['cursor']
            pt = local_pos if local_pos is not None else widget.rect().center()
            mapped = widget.mapTo(panel, pt)
            orig = base_origin()
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
                app.processEvents()
            actions[f_exec] = run

        def click_widget(widget):
            pt = widget_canvas_point(widget)
            register_click(pt)
            QTest.mouseClick(widget, Qt.MouseButton.LeftButton)

        def animate_scroll(target, dur=18):
            sb = panel.details_scroll.verticalScrollBar()
            v1 = max(0, min(sb.maximum(), target))
            state['scroll_anim'] = (sb, sb.value(), v1, state['frame'], dur)

        def animate_slider(slider, target, dur=16):
            state['slider_anim'] = (slider, slider.value(), target, state['frame'], dur)

        def draw_cursor(painter, pt):
            arrow = QPolygonF([
                pt,
                QPointF(pt.x(), pt.y() + 17),
                QPointF(pt.x() + 4.5, pt.y() + 13),
                QPointF(pt.x() + 8.5, pt.y() + 20),
                QPointF(pt.x() + 11.2, pt.y() + 18.6),
                QPointF(pt.x() + 7.2, pt.y() + 11.6),
                QPointF(pt.x() + 12.8, pt.y() + 11.2),
            ])
            painter.setPen(QPen(QColor('#120e19'), 2.2, Qt.PenStyle.SolidLine,
                                Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            painter.setBrush(QColor('#ffffff'))
            painter.drawPolygon(arrow)

        def sp():
            return panel.skin_panel

        # ── 1. Enable local skin changer & filter to Knives ───────────────────
        schedule(
            1.1, 'knife skins',
            'enable local skin changer',
            lambda: click_widget(sp().enable_toggle),
            aim_fn=lambda: widget_canvas_point(sp().enable_toggle),
        )
        schedule(
            1.3, '20 cs2 knives',
            'filter category to knives — all 20 custom cs2 models (#500–#526)',
            lambda: (register_click(widget_canvas_point(sp().category_combo)),
                     sp().category_combo.setCurrentText('Knives')),
            aim_fn=lambda: widget_canvas_point(sp().category_combo),
        )

        # ── 2. Configure ★ Karambit · Doppler (Ruby) ──────────────────────────
        def pick_knife(weapon_id):
            idx = sp().weapon_combo.findData(weapon_id)
            register_click(widget_canvas_point(sp().weapon_combo))
            if idx >= 0:
                sp().weapon_combo.setCurrentIndex(idx)

        def pick_kit(kit_id):
            idx = sp().kit_combo.findData(kit_id)
            register_click(widget_canvas_point(sp().kit_combo))
            if idx >= 0:
                sp().kit_combo.setCurrentIndex(idx)
            else:
                sp().kit_spin.setValue(kit_id)

        schedule(
            1.4, 'karambit ruby',
            'select ★ karambit (#507)',
            lambda: pick_knife(507),
            aim_fn=lambda: widget_canvas_point(sp().weapon_combo),
        )
        schedule(
            1.5, 'karambit ruby',
            'choose doppler (ruby) (kit 415) — live swatches & covert badge',
            lambda: pick_kit(415),
            aim_fn=lambda: widget_canvas_point(sp().kit_combo),
        )
        schedule(
            1.6, 'finish tuning',
            'scroll to wear float, pattern seed, stattrak & nametag controls',
            lambda: animate_scroll(230, dur=18),
        )
        schedule(
            1.1, 'finish tuning',
            'slide wear float across spectrum (fn → ft) then snap to fn',
            lambda: animate_slider(sp().wear_slider, 2200, dur=16),
            aim_fn=lambda: widget_canvas_point(sp().wear_slider),
        )
        schedule(
            1.0, 'finish tuning',
            'click fn quick-wear preset (0.0010 factory new)',
            lambda: click_widget(sp().wear_buttons['FN']),
            aim_fn=lambda: widget_canvas_point(sp().wear_buttons['FN']),
        )
        schedule(
            1.1, 'finish tuning',
            'set pattern seed 387, enable stattrak (777) & custom local nametag',
            lambda: (sp().seed_spin.setValue(387),
                     click_widget(sp().stattrak_toggle),
                     sp().stattrak_spin.setValue(777),
                     sp().name_edit.setText('ruby blade')),
            aim_fn=lambda: widget_canvas_point(sp().stattrak_toggle),
        )
        schedule(
            1.2, 'karambit ruby',
            'scroll to apply button for ★ karambit',
            lambda: animate_scroll(320, dur=10),
        )
        schedule(
            0.5, 'karambit ruby',
            'apply to ★ karambit — auto-equips active knife override (#507)',
            lambda: click_widget(sp().apply_weapon_button),
            aim_fn=lambda: widget_canvas_point(sp().apply_weapon_button),
        )

        # ── 3. Preview & switch across other iconic CS2 knives ────────────────
        schedule(
            1.5, 'knife preview',
            'scroll up — ★ karambit equipped with ruby finish, seed 387 & st 777',
            lambda: animate_scroll(0, dur=18),
        )
        schedule(
            1.7, 'butterfly emerald',
            'switch weapon to ★ butterfly knife (#515)',
            lambda: pick_knife(515),
            aim_fn=lambda: widget_canvas_point(sp().weapon_combo),
        )
        schedule(
            1.4, 'butterfly emerald',
            'select gamma doppler (emerald) (kit 568)',
            lambda: pick_kit(568),
            aim_fn=lambda: widget_canvas_point(sp().kit_combo),
        )
        schedule(
            1.5, 'active knife',
            'switch active knife override dropdown to ★ butterfly knife',
            lambda: (register_click(widget_canvas_point(sp().knife_override_combo)),
                     sp().knife_override_combo.setCurrentIndex(sp().knife_override_combo.findData(515))),
            aim_fn=lambda: widget_canvas_point(sp().knife_override_combo),
        )
        schedule(
            1.6, 'm9 sapphire',
            'preview ★ m9 bayonet (#508) · doppler (sapphire) (kit 416)',
            lambda: (pick_knife(508), pick_kit(416)),
            aim_fn=lambda: widget_canvas_point(sp().weapon_combo),
        )
        schedule(
            1.6, 'skeleton blue gem',
            'preview ★ skeleton knife (#525) · case hardened (kit 44)',
            lambda: (pick_knife(525), pick_kit(44), sp().seed_spin.setValue(403)),
            aim_fn=lambda: widget_canvas_point(sp().weapon_combo),
        )
        schedule(
            1.6, 'kukri fade',
            'preview ★ kukri knife (#526) · fade (kit 38)',
            lambda: (pick_knife(526), pick_kit(38)),
            aim_fn=lambda: widget_canvas_point(sp().weapon_combo),
        )

        # ── 4. Load knife gems starter pack & export .skin-loadout.json ───────
        schedule(
            1.5, 'knife gems pack',
            'scroll down to active knife loadout & starter packs',
            lambda: animate_scroll(panel.details_scroll.verticalScrollBar().maximum(), dur=20),
        )
        schedule(
            1.3, 'knife gems pack',
            'select starter pack "knife gems" (5 configured ★ knives)',
            lambda: (register_click(widget_canvas_point(sp().pack_combo)),
                     sp().pack_combo.setCurrentText('knife gems')),
            aim_fn=lambda: widget_canvas_point(sp().pack_combo),
        )
        schedule(
            1.2, 'knife gems pack',
            'load "knife gems" into active loadout list',
            lambda: click_widget(sp().load_pack_button),
            aim_fn=lambda: widget_canvas_point(sp().load_pack_button),
        )
        schedule(
            1.6, 'local export',
            'sync .skin-loadout.json with knife_override + all knife entries',
            lambda: click_widget(sp().export_button),
            aim_fn=lambda: widget_canvas_point(sp().export_button),
        )
        schedule(
            1.4, 'knife skins',
            'scroll back to top after syncing .skin-loadout.json',
            lambda: animate_scroll(0, dur=16),
        )
        schedule(
            0.8, 'knife skins',
            'inspect ★ butterfly knife · gamma doppler (emerald) equipped locally',
            lambda: pick_knife(515),
            aim_fn=lambda: widget_canvas_point(sp().weapon_combo),
        )
        schedule(
            2.2, 'knife skins',
            'all 20 cs2 knives + 36 curated finishes ready · local only',
            lambda: None,
        )

        total_frames = round((timeline[0] + 0.4) * FPS)
        output = Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        ffmpeg = ff.get_ffmpeg_exe()
        cmd = [
            ffmpeg, '-y', '-f', 'rawvideo', '-pix_fmt', 'rgba',
            '-s', f'{CANVAS_W}x{CANVAS_H}', '-r', str(FPS), '-i', '-',
            '-an', '-c:v', 'libx264', '-preset', 'medium', '-crf', '18',
            '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(output),
        ]
        with tempfile.TemporaryFile() as errors:
            encoder = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=errors)
            timer = QTimer()
            timer.setInterval(0)

            def finish():
                timer.stop()
                panel.close()
                app.quit()

            def invoke(fn):
                try:
                    fn()
                except Exception:
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

                    ct = min(1.0, (idx - state['cursor_start']) / max(1, state['cursor_dur']))
                    ce = 1.0 - (1.0 - ct) ** 3
                    c0, c1 = state['cursor_from'], state['cursor_to']
                    state['cursor'] = QPointF(c0.x() + (c1.x() - c0.x()) * ce,
                                              c0.y() + (c1.y() - c0.y()) * ce)

                    canvas = QImage(CANVAS_W, CANVAS_H, QImage.Format.Format_RGBA8888)
                    canvas.fill(QColor('#120e19'))
                    painter = QPainter(canvas)
                    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

                    shot = panel.grab()
                    orig = base_origin()
                    bx, by = round(orig.x()), round(orig.y())
                    painter.setPen(QPen(QColor('#3a304a'), 1.5))
                    painter.setBrush(QColor('#1c1726'))
                    painter.drawRoundedRect(QRectF(bx - 1, by - 1, shot.width() + 2, shot.height() + 2), 6, 6)
                    painter.drawPixmap(bx, by, shot)

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

                    footer_y = CANVAS_H - 72
                    painter.fillRect(0, footer_y, CANVAS_W, 72, QColor('#181322'))
                    painter.setPen(QPen(QColor('#2d243c'), 1))
                    painter.drawLine(0, footer_y, CANVAS_W, footer_y)

                    prog_w = CANVAS_W * (idx / max(1, total_frames - 1))
                    painter.fillRect(QRectF(0, footer_y, prog_w, 2.5), QColor('#fc589b'))

                    badge_rect = QRectF(20, footer_y + 14, 156, 22)
                    painter.setPen(QPen(QColor('#fc589b'), 1.0))
                    painter.setBrush(QColor(252, 88, 155, 36))
                    painter.drawRoundedRect(badge_rect, 11, 11)
                    painter.setPen(QColor('#ffd8ea'))
                    painter.setFont(ui_font(8))
                    painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, state['chapter'])

                    painter.setPen(QColor('#efe8f8'))
                    painter.setFont(ui_font(11))
                    painter.drawText(QRectF(188, footer_y + 10, CANVAS_W - 206, 28),
                                     Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                                     state['caption'])

                    painter.setPen(QColor('#9284ac'))
                    painter.setFont(ui_font(8))
                    elapsed = idx / FPS
                    total_s = total_frames / FPS
                    painter.drawText(QRectF(20, footer_y + 42, CANVAS_W - 40, 22),
                                     Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                                     f'phantom v{__version__} · cs2 knife skin changer gui · real qt6 offscreen capture')
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
                    f'Knife GUI recording failed at frame {state["frame"]}/{total_frames}: {state["error"]}; {diag}'
                )
            assert loadout_path(directory).is_file(), 'Expected .skin-loadout.json export during demo'
        secs = total_frames / FPS
        size_kb = output.stat().st_size / 1024.0
        print(f'{output}: {total_frames} actual Qt frames, {FPS} fps, {secs:.1f}s, {CANVAS_W}x{CANVAS_H}, {size_kb:.0f} KB')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='docs/demos/knife-skin-changer.mp4')
    record(parser.parse_args().output)
