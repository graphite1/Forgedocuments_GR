"""Source-observed print glyphs and approved numeric subsets, loaded locally without Windows font installation."""
import hashlib
from pathlib import Path
import sys

PROFILE='tomei-sample-digits-v1'
LABEL='数字・.-B専用／他は標準'
FILENAME='tomei-sample-digits-qa.ttf'
SHA256='9511a838776102e226de15a6d5f5f6f33c792e8a4bcd7e30657907b4d0cf7997'
SUPPORTED=frozenset('0123456789.-B')
NUMERIC_PROFILE='tomei-numeric-only-v2'
NUMERIC_LABEL='数字・.-専用／他は標準'
NUMERIC_SUPPORTED=frozenset('0123456789.-')
OBSERVED_PROFILE='tomei-observed-46-v2'
OBSERVED_LABEL='生コン専用印字（採取46字／未収録字は標準）'
OBSERVED_FILENAME='tomei-observed-46-v2.ttf'
OBSERVED_SHA256='24112fd704e2ac9dfc6ca4e721c54f2086125b08be8f087a69b12b17df827836'
OBSERVED_SUPPORTED=frozenset('()-.0123456789BNO事備公刈動合園場工市整文普書株殿河画第総角計谷車通運配野駐')
PROFILES={OBSERVED_PROFILE:(OBSERVED_LABEL,OBSERVED_SUPPORTED),PROFILE:(LABEL,SUPPORTED),NUMERIC_PROFILE:(NUMERIC_LABEL,NUMERIC_SUPPORTED)}


def font_file():
    root=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent))
    return root/'assets'/FILENAME


def validated_file(path=None):
    path=Path(path) if path is not None else font_file()
    if not path.is_file():return None
    if hashlib.sha256(path.read_bytes()).hexdigest()!=SHA256:
        raise ValueError('専用印字フォントの検証に失敗しました。確認用ビルドを再配置してください。')
    return path



def observed_file():return font_file().with_name(OBSERVED_FILENAME)


def validated_observed_file(path=None):
    path=Path(path) if path is not None else observed_file()
    if not path.is_file():return None
    if hashlib.sha256(path.read_bytes()).hexdigest()!=OBSERVED_SHA256:
        raise ValueError('採取46字フォントのハッシュが一致しません')
    return path


def profile_file(profile):
    return validated_observed_file() if profile==OBSERVED_PROFILE else validated_file()


def bundle_files():
    paths=[validated_file(),validated_observed_file()]
    if any(p is None for p in paths):raise ValueError('生コン専用印字フォントが不足しています')
    return [p for source in paths for p in (source,source.with_suffix('.json'))]


def input_font(template,fallback):
    profile=template.get('input_font_profile')
    if template.get('form_id')!='tomei_taiheiyo' or profile not in PROFILES:
        return fallback
    path=profile_file(profile)
    if path is None:
        raise ValueError('生コン専用印字フォントが同梱されていません。設定で標準書体を選択してください。')
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from input_fonts import InputFont
    name='TomeiObservedPrintV2' if profile==OBSERVED_PROFILE else 'TomeiSampleDigitsV1'
    if name not in pdfmetrics.getRegisteredFontNames():pdfmetrics.registerFont(TTFont(name,str(path),validate=1))
    supported=PROFILES[profile][1]
    if not all(ord(char) in pdfmetrics.getFont(name).face.charToGlyph for char in supported):
        raise ValueError('専用印字フォントに必要な文字がありません。')
    return InputFont(fallback,name,supported)
