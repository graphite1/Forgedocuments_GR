"""Private, optional print-font prototype. Never install it into Windows."""
import hashlib
from pathlib import Path
import sys

PROFILE='tomei-sample-digits-v1'
LABEL='生コン専用印字（数字・.-B／他は標準）'
FILENAME='tomei-sample-digits.ttf'
SHA256='e65eb34b517e6d4bd97713507800cbef8b24cca0f1fc3c0cfc21b485873c342d'
SUPPORTED=frozenset('0123456789.-B')


def font_file():
    root=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent))
    return root/'private-assets'/FILENAME


def validated_file(path=None):
    path=Path(path) if path is not None else font_file()
    if not path.is_file():return None
    if hashlib.sha256(path.read_bytes()).hexdigest()!=SHA256:
        raise ValueError('専用印字フォントの検証に失敗しました。確認用ビルドを再配置してください。')
    return path


def input_font(template,fallback):
    if template.get('form_id')!='tomei_taiheiyo' or template.get('input_font_profile')!=PROFILE:
        return fallback
    path=validated_file()
    if path is None:
        raise ValueError('生コン専用印字フォントが同梱されていません。設定で標準書体を選択してください。')
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from input_fonts import InputFont
    name='TomeiSampleDigitsV1'
    if name not in pdfmetrics.getRegisteredFontNames():pdfmetrics.registerFont(TTFont(name,str(path),validate=1))
    if not all(ord(char) in pdfmetrics.getFont(name).face.charToGlyph for char in SUPPORTED):
        raise ValueError('専用印字フォントに必要な文字がありません。')
    return InputFont(fallback,name,SUPPORTED)
