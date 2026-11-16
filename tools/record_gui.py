"""Record real Qt widget frames, without starting the game worker.

Optional capture dependency: pip install imageio-ffmpeg==0.6.0
Run: python tools/record_gui.py --output artifacts/gui-demo.mp4
The video is actual offscreen Qt rendering, with explanatory footer captions.
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


def record(output):
    import imageio_ffmpeg
    from PySide6.QtCore import Qt, QTimer, QEvent, QPointF
    from PySide6.QtGui import QColor, QImage, QPainter, QPen, QEnterEvent
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QMessageBox
    from unittest.mock import patch
    from native.gui import ControlPanel
    from native.typography import ui_font
    from native.version import __version__

    app = QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory(prefix='phantom-video-') as directory:
        panel = ControlPanel(ROOT/'native/profiles/reference-26598758.json', directory)
        # No menu hotkey or worker may interfere with a deterministic demo.
        panel.menu_timer.stop()
        panel.show()
        app.processEvents()
        width = panel.width() + panel.width() % 2
        height = panel.height()+80
        height += height % 2
        output = Path(output).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        command = [imageio_ffmpeg.get_ffmpeg_exe(), '-hide_banner', '-loglevel', 'error',
                   '-y', '-f', 'rawvideo', '-pixel_format', 'rgba', '-video_size',
                   f'{width}x{height}', '-framerate', '30', '-i', '-', '-an',
                   '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20',
                   '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(output)]
        # Put encoder diagnostics in a file so a full stderr pipe cannot deadlock.
        with tempfile.TemporaryFile() as errors:
            encoder = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=errors)
            state = {'frame': 0, 'caption': 'poppins · lowercase · horizontal', 'click': None,
                     'error': None}

            def click(widget, caption):
                point = widget.mapTo(panel, widget.rect().center())
                state['click'] = (point, state['frame'])
                state['caption'] = caption
                QTest.mouseClick(widget, Qt.MouseButton.LeftButton)

            def hover(enter):
                button = panel.start_button
                center = QPointF(button.rect().center())
                app.sendEvent(button, QEnterEvent(center, center, center) if enter else QEvent(QEvent.Type.Leave))
                state['caption'] = 'soft hover highlights · no runtime started'

            def theme(name):
                panel.theme_combo.setCurrentText(name)
                state['caption'] = name+' theme · live color preview'

            def density(name):
                panel.appearance_controls['spacing'].setCurrentText(name)
                state['caption'] = name+' spacing · live layout preview'

            def apply_preset(name):
                panel.preset_combo.setCurrentText(name)
                # Demo only: script the normal confirmation without blocking the
                # frame timer in a nested modal loop. No game worker is started.
                with patch('native.gui.QMessageBox.question', return_value=QMessageBox.StandardButton.Yes):
                    click(panel.preset_apply_button, name+' · applied, not saved')

            actions = {
                30: lambda: click(panel.appearance_button, 'appearance · colors and layout'),
                55: lambda: theme('midnight'),
                95: lambda: theme('forest'),
                130: lambda: density('compact'),
                170: lambda: density('comfortable'),
                205: lambda: click(panel.tab_buttons['Configs'], 'built-in configuration presets'),
                235: lambda: apply_preset('esp minimal'),
                280: lambda: click(panel.tab_buttons['Visuals'], 'minimal esp · health only, 100 m'),
                325: lambda: click(panel.tab_buttons['Configs'], 'smooth aim practice preset'),
                350: lambda: apply_preset('smooth aim practice'),
                395: lambda: click(panel.tab_buttons['Aim'], 'smooth aim · 2 degree fov, 200 ms, chest'),
                445: lambda: click(panel.tab_buttons['Configs'], 'combined settings preset'),
                470: lambda: apply_preset('combined practice'),
                520: lambda: click(panel.tab_buttons['Aim'], 'combined · smooth aim and detailed esp'),
                565: lambda: click(panel.appearance_button, 'appearance stays separate from gameplay configs'),
                590: lambda: theme('midnight'),
                620: lambda: click(panel.more, 'compact overview'),
                660: lambda: click(panel.more, 'expanded customization page'),
                695: lambda: hover(True),
            }
            timer = QTimer()
            timer.setTimerType(Qt.TimerType.PreciseTimer)
            timer.setInterval(33)

            def finish():
                timer.stop()
                panel.close()
                app.quit()

            def frame():
                try:
                    index = state['frame']
                    if index >= 720:
                        finish()
                        return
                    if index in actions:
                        actions[index]()
                    canvas = QImage(width, height, QImage.Format.Format_RGBA8888)
                    canvas.fill(QColor('#17131f'))
                    painter = QPainter(canvas)
                    snapshot = panel.grab()
                    x = (width-snapshot.width())//2
                    painter.drawPixmap(x, 0, snapshot)
                    if state['click'] is not None:
                        point, began = state['click']
                        age = index-began
                        if age < 12:
                            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                            painter.setBrush(Qt.BrushStyle.NoBrush)
                            painter.setPen(QPen(QColor(252, 88, 155, round(220*(1-age/12))), 2))
                            painter.drawEllipse(QPointF(x+point.x(), point.y()), 12+age, 12+age)
                    painter.setPen(QColor('#e6ddef'))
                    painter.setFont(ui_font(11))
                    painter.drawText(0, height-69, width, 30, Qt.AlignmentFlag.AlignCenter, state['caption'])
                    painter.setPen(QColor('#9284ac'))
                    painter.setFont(ui_font(9))
                    painter.drawText(0, height-37, width, 26, Qt.AlignmentFlag.AlignCenter,
                                     f'phantom v{__version__} · scripted qt demo · no game connection')
                    painter.end()
                    encoder.stdin.write(bytes(canvas.constBits()))
                    state['frame'] += 1
                except Exception as error:
                    state['error'] = error
                    finish()

            timer.timeout.connect(frame)
            timer.start()
            app.exec()
            encoder.stdin.close()
            try:
                code = encoder.wait(timeout=60)
            except subprocess.TimeoutExpired:
                encoder.kill()
                encoder.wait()
                raise RuntimeError('Video encoder timed out.')
            errors.seek(0)
            diagnostics = errors.read().decode(errors='replace')
            if state['error'] is not None or code or state['frame'] != 720:
                output.unlink(missing_ok=True)
                raise RuntimeError(f'GUI recording failed: {state["error"]}; {diagnostics}')
            print(f'{output}: 720 actual Qt frames, 30 fps, 24 seconds, {width}x{height}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='artifacts/gui-demo.mp4')
    args = parser.parse_args()
    record(args.output)
