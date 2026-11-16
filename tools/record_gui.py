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
    from PySide6.QtWidgets import QApplication
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

            actions = {
                30: lambda: click(panel.toggles['esp'], 'smooth toggle motion and colors'),
                55: lambda: click(panel.toggles['esp'], 'smooth toggle motion and colors'),
                85: lambda: click(panel.tab_buttons['Visuals'], 'visuals · actual settings-page fade'),
                130: lambda: click(panel.tab_buttons['Input'], 'input · custom bindings'),
                175: lambda: click(panel.tab_buttons['Configs'], 'configs · local settings'),
                220: lambda: click(panel.tab_buttons['Aim'], 'aim · settings-page transition'),
                260: lambda: click(panel.more, 'compact overview'),
                305: lambda: click(panel.more, 'expanded horizontal layout'),
                345: lambda: hover(True),
                370: lambda: hover(False),
                390: lambda: hover(True),
                415: lambda: hover(False),
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
                    if index >= 450:
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
                                     f'phantom v{__version__} · actual qt capture · no game connection')
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
            if state['error'] is not None or code or state['frame'] != 450:
                output.unlink(missing_ok=True)
                raise RuntimeError(f'GUI recording failed: {state["error"]}; {diagnostics}')
            print(f'{output}: 450 actual Qt frames, 30 fps, 15 seconds, {width}x{height}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='artifacts/gui-demo.mp4')
    args = parser.parse_args()
    record(args.output)
