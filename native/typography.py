"""Load the redistributable UI face before creating or painting any text."""
from pathlib import Path

from PySide6.QtGui import QFont, QFontDatabase, QRawFont

FAMILY = 'Poppins'
_FONT_ID = None
# All non-ASCII punctuation retained in the control panel; icons are painted.
REQUIRED_TEXT = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789°·—…“”–'


def configure_fonts():
    global _FONT_ID
    if _FONT_ID is None:
        path = Path(__file__).resolve().parent/'assets/fonts/Poppins-Regular.ttf'
        font_id = QFontDatabase.addApplicationFont(str(path))
        if font_id < 0 or FAMILY not in QFontDatabase.applicationFontFamilies(font_id):
            raise RuntimeError('The bundled Poppins font could not be loaded. Extract/reinstall the complete package.')
        face = QRawFont.fromFont(QFont(FAMILY, 10))
        if not face.isValid() or face.familyName() != FAMILY or any(not face.supportsCharacter(c) for c in REQUIRED_TEXT):
            QFontDatabase.removeApplicationFont(font_id)
            raise RuntimeError('The UI font is missing required glyphs; the panel cannot be rendered reliably.')
        _FONT_ID = font_id
    return FAMILY


def ui_font(points):
    return QFont(configure_fonts(), points)
