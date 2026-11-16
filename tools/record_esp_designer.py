"""Record every skeleton ESP designer control with real Qt window captures.

Optional dependency: imageio-ffmpeg==0.6.0. No worker is started. All settings
and saved config files are isolated in a temporary directory. Qt color pickers
are forced only in this recorder so their real widgets can be captured.
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
FPS, SECONDS = 30, 78


def record(output):
    from unittest.mock import patch
    import imageio_ffmpeg as ff
    from PySide6.QtCore import Qt, QTimer, QPoint
    from PySide6.QtGui import QColor, QImage, QPainter
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QColorDialog, QMessageBox, QPushButton
    from native.gui import ControlPanel
    from native.config import load_config
    from native.esp_style import DEFAULT_STYLE, TARGETS
    from native.typography import ui_font

    app = QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory(prefix='phantom-designer-video-') as directory:
        panel = ControlPanel(ROOT/'native/profiles/reference-26598758.json', directory, 'designer-demo')
        panel.menu_timer.stop()
        panel.show();panel.select_page('Visuals');app.processEvents()
        state = {'frame':0, 'caption':'skeleton esp designer · full control walkthrough',
                 'error':None, 'saved':None, 'saved_color':None}
        actions = {}

        def add(second, caption, callback):
            def action():
                state['caption'] = caption
                callback()
                assert panel.session.process is None
                assert panel.model.config.aim == 'off'
            actions[round(second*FPS)] = action

        def editor():
            return panel.esp_editor

        def click(widget):
            # QCheckBox hit regions stop at the label, not the full layout row.
            QTest.mouseClick(widget,Qt.MouseButton.LeftButton,pos=QPoint(8,widget.height()//2))

        def button(text):
            return next(widget for widget in editor().findChildren(QPushButton) if widget.text().lower()==text)

        def open_editor():
            panel.select_page('Visuals')
            panel.editor_button.click()

        def select_target(name):
            x,y = editor().preview.points()[name]
            QTest.mouseClick(editor().preview,Qt.MouseButton.LeftButton,pos=QPoint(round(x),round(y)))
            assert panel.model.config.priority_bone == name

        def picker():
            dialog = app.activeModalWidget()
            if not isinstance(dialog,QColorDialog):
                raise RuntimeError('Expected a real Qt color picker.')
            return dialog

        def set_color(value):
            picker().setCurrentColor(QColor(value))

        def finish_color(key,value):
            picker().accept()
            # getColor returns on the next event-loop unwind; assertions happen
            # in the following scheduled action or at the end of the recording.

        add(1.5,'open the designer from visuals',open_editor)
        for second,name in zip((3,4.5,6,7.5),TARGETS):
            add(second,'click aim target: '+name,lambda name=name: select_target(name))
        for index,name in enumerate(TARGETS):
            def keyboard(index=index,name=name):
                editor().preview.setFocus()
                QTest.keyClick(editor().preview,Qt.Key(Qt.Key.Key_1+index))
                assert panel.model.config.priority_bone == name
            add(9+index,'keyboard '+str(index+1)+': '+name+' · aim stays off',keyboard)
        for key,off,on in [('esp',13,15),('skeleton',16,18),('health',19,21),('armor',22,24)]:
            add(off,key+' off · faint selection guide remains',lambda key=key: click(editor().checks[key]))
            add(on,key+' back on',lambda key=key: click(editor().checks[key]))
        for key,at in [('box',25),('box',27),('box',28),('names',29),('names',31),('distance',32),('distance',34)]:
            add(at,'toggle '+key.replace('_',' '),lambda key=key: click(editor().style_checks[key]))
        for width,second in zip((1,2,3,4),(35,36.5,38,39.5)):
            add(second,'skeleton and box line width: '+str(width),lambda width=width: editor().width_combo.setCurrentText(str(width)))
        colors = [('visible_color','#fc589b',41),('hidden_color','#ff7755',45),
                  ('team_color','#b2a1ff',49),('health_color','#72f2b4',52),('armor_color','#70bfff',55)]
        add(44,'preview an unspotted enemy',lambda: editor().sample_combo.setCurrentText('unspotted enemy'))
        add(48,'preview a teammate',lambda: editor().sample_combo.setCurrentText('teammate'))
        for key,value,second in colors:
            add(second,'open '+key.replace('_',' ')+' picker',lambda key=key: editor().color_buttons[key][0].click())
            add(second+1,'choose '+value+' in the real color picker',lambda value=value: set_color(value))
            add(second+2,'accept custom '+key.replace('_',' '),lambda key=key,value=value: finish_color(key,value))
        add(58,'return to spotted-enemy sample',lambda: editor().sample_combo.setCurrentText('spotted enemy'))
        add(59,'open color picker again',lambda: editor().color_buttons['visible_color'][0].click())
        add(60,'cancel picker · previous color preserved',lambda: picker().reject())
        add(61,'try reserved transparency color',lambda: editor().color_buttons['visible_color'][0].click())
        add(62,'pure black is reserved for overlay transparency',lambda: set_color('#000000'))
        add(63,'reject invalid black · valid pink remains',lambda: picker().accept())

        def save():
            for key,value,_ in colors:
                assert panel.model.config.esp_style[key]==value
            assert panel.model.config.esp_style['line_width']==4
            assert panel.model.config.esp_style['box']
            button('save current config').click()
            state['saved'] = load_config(panel.model.path)
            assert state['saved']==panel.model.config
        add(64,'save the edited designer-demo config',save)

        def reset():
            button('reset esp style').click()
            assert panel.model.config.esp_style==DEFAULT_STYLE
            assert load_config(panel.model.path)==state['saved']
        add(66,'reset style · saved file is unchanged until saved again',reset)
        add(68,'done · return to the main settings panel',lambda: button('done').click())
        add(69,'open configs to reload the saved design',lambda: panel.select_page('Configs'))

        def load_saved():
            panel.saved_combo.setCurrentText('designer-demo')
            panel.load_named()
        add(70,'load designer-demo · real confirmation dialog',load_saved)

        def approve():
            modal = app.activeModalWidget()
            if not isinstance(modal,QMessageBox):
                raise RuntimeError('Expected config-load confirmation.')
            modal.button(QMessageBox.StandardButton.Yes).click()
        add(71,'confirm reloading saved settings',approve)

        def reopen():
            assert panel.model.config==state['saved']
            open_editor()
            assert panel.model.config.esp_style['line_width']==4
        add(72,'reopen designer · saved colors, target and width restored',reopen)
        add(75,'finish · no game worker was started',lambda: button('done').click())

        output = Path(output).resolve();output.parent.mkdir(parents=True,exist_ok=True)
        width,height = 900,760
        command = [ff.get_ffmpeg_exe(),'-v','error','-y','-f','rawvideo','-pixel_format','rgba',
                   '-video_size',f'{width}x{height}','-framerate',str(FPS),'-i','-','-an',
                   '-c:v','libx264','-preset','veryfast','-crf','20','-pix_fmt','yuv420p',
                   '-movflags','+faststart',str(output)]
        real_get_color = QColorDialog.getColor
        def qt_picker(initial,parent,title):
            return real_get_color(initial,parent,title,options=QColorDialog.ColorDialogOption.DontUseNativeDialog)
        with tempfile.TemporaryFile() as errors:
            encoder = subprocess.Popen(command,stdin=subprocess.PIPE,stderr=errors)
            timer = QTimer();timer.setTimerType(Qt.TimerType.PreciseTimer);timer.setInterval(33)

            def finish():
                timer.stop()
                modal = app.activeModalWidget()
                if modal is not None and modal is not getattr(panel,'esp_editor',None):
                    modal.reject()
                panel.close();app.quit()

            def invoke(action):
                try:
                    action()
                except Exception as error:
                    state['error']=error;finish()

            def capture():
                try:
                    index = state['frame']
                    if index >= FPS*SECONDS:
                        finish();return
                    # Separate callbacks allow real modal dialogs to run while
                    # the capture timer keeps recording their nested event loop.
                    if index in actions:
                        QTimer.singleShot(0,lambda action=actions[index]: invoke(action))
                    canvas = QImage(width,height,QImage.Format.Format_RGBA8888);canvas.fill(QColor('#17131f'))
                    painter = QPainter(canvas)
                    base = editor() if hasattr(panel,'esp_editor') and editor().isVisible() else panel
                    shot = base.grab();painter.drawPixmap((width-base.width())//2,8,shot)
                    modal = app.activeModalWidget()
                    if modal is not None and modal is not base:
                        # Composite actual dialog capture, centered for legibility.
                        dialog_shot = modal.grab()
                        if dialog_shot.width()>width-20 or dialog_shot.height()>height-100:
                            dialog_shot = dialog_shot.scaled(width-20,height-100,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation)
                        painter.drawPixmap((width-dialog_shot.width())//2,40,dialog_shot)
                    painter.setFont(ui_font(11));painter.setPen(QColor('#e6ddef'))
                    painter.drawText(0,height-72,width,32,Qt.AlignmentFlag.AlignCenter,state['caption'])
                    painter.setFont(ui_font(9));painter.setPen(QColor('#9284ac'))
                    painter.drawText(0,height-38,width,26,Qt.AlignmentFlag.AlignCenter,'actual qt windows · temporary config · aim off · no game connection')
                    painter.end();encoder.stdin.write(bytes(canvas.constBits()));state['frame']+=1
                except Exception as error:
                    state['error']=error;finish()

            timer.timeout.connect(capture)
            with patch.object(QColorDialog,'getColor',side_effect=qt_picker):
                timer.start();app.exec()
            encoder.stdin.close()
            try:
                code = encoder.wait(timeout=60)
            except subprocess.TimeoutExpired:
                encoder.kill();encoder.wait();raise RuntimeError('Encoder timed out.')
            errors.seek(0)
            if state['error'] is not None or code or state['frame']!=FPS*SECONDS:
                output.unlink(missing_ok=True)
                raise RuntimeError(f'Recording failed: {state["error"]}; {errors.read().decode(errors="replace")}')
        print(f'{output}: {FPS*SECONDS} frames, {SECONDS} seconds, {width}x{height}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',default='artifacts/esp-designer-walkthrough.mp4')
    record(parser.parse_args().output)
