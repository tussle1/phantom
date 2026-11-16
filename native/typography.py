"""Load the redistributable UI face before creating or painting any text."""
from pathlib import Path

from PySide6.QtGui import QFont, QFontDatabase, QFontInfo, QFontMetrics

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
        candidate = QFont(FAMILY, 10)
        actual = QFontInfo(candidate).family()
        metrics = QFontMetrics(candidate)
        missing = [f'U+{ord(c):04X}' for c in REQUIRED_TEXT if not metrics.inFontUcs4(ord(c))]
        # Font metrics use the platform text engine. QRawFont.fromFont can be
        # invalid with Windows offscreen/GDI engines despite valid widget fonts.
        if actual not in (FAMILY, FAMILY+' Regular') or missing:
            QFontDatabase.removeApplicationFont(font_id)
            raise RuntimeError(f'UI font validation failed: selected {actual!r}; missing {missing}.')
        _FONT_ID = font_id
    return FAMILY


def ui_font(points):
    font = QFont(configure_fonts(), points)
    # Presentation only: config values, paths, key names and enum identifiers
    # retain their original case in the model and on disk.
    font.setCapitalization(QFont.Capitalization.AllLowercase)
    return font
