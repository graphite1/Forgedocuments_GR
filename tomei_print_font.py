"""Approved numeric subset, loaded locally without Windows font installation."""
import hashlib
from pathlib import Path
import sys

PROFILE='tomei-sample-digits-v1'
LABEL='生コン専用印字（数字・.-B／他は標準）'
FILENAME='tomei-sample-digits-qa.ttf'
SHA256='9511a838776102e226de15a6d5f5f6f33c792e8a4bcd7e30657907b4d0cf7997'
SUPPORTED=frozenset('0123456789.-B')
NUMERIC_PROFILE='tomei-numeric-only-v2'
NUMERIC_LABEL='数字・.-専用／他は標準'
NUMERIC_SUPPORTED=frozenset('0123456789.-')
PROFILES={PROFILE:(LABEL,SUPPORTED),NUMERIC_PROFILE:(NUMERIC_LABEL,NUMERIC_SUPPORTED)}


def font_file():
    root=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent))
    return root/'assets'/FILENAME


def validated_file(path=None):
    path=Path(path) if path is not None else font_file()
    if not path.is_file():return None
    if hashlib.sha256(path.read_bytes()).hexdigest()!=SHA256:
        raise ValueError('専用印字フォントの検証に失敗しました。確認用ビルドを再配置してください。')
    return path


def input_font(template,fallback):
    profile=template.get('input_font_profile')
    if template.get('form_id')!='tomei_taiheiyo' or profile not in PROFILES:
        return fallback
    path=validated_file()
    if path is None:
        raise ValueError('生コン専用印字フォントが同梱されていません。設定で標準書体を選択してください。')
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from input_fonts import InputFont
    name='TomeiSampleDigitsV1'
    if name not in pdfmetrics.getRegisteredFontNames():pdfmetrics.registerFont(TTFont(name,str(path),validate=1))
    supported=PROFILES[profile][1]
    if not all(ord(char) in pdfmetrics.getFont(name).face.charToGlyph for char in supported):
        raise ValueError('専用印字フォントに必要な文字がありません。')
    return InputFont(fallback,name,supported)
