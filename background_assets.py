"""Portable, hashed blue-print assets; never synthesize missing source ink."""
import base64
import hashlib
import io
import math
from PIL import Image, ImageDraw

MAX_BYTES = 20 * 1024 * 1024
MAX_PIXELS = 24_000_000


def missing_background():
    return {'schema_version': 1, 'status': 'missing', 'kind': 'original_blue',
            'reviewed': False, 'missing_reason': '原票の青い固定印字を保持した背景画像が未取得です'}


def validate_background(template, require_ready=False):
    config = template.get('background', missing_background())
    if config.get('schema_version') != 1 or config.get('status') not in ('missing', 'draft', 'ready'):
        raise ValueError('背景画像の定義が不正です')
    if config.get('kind') not in ('original_blue', 'corrected_blue', 'synthetic_test'):
        raise ValueError('背景画像の由来を指定してください')
    errors=config.get('unresolved_text_errors',[])
    if not isinstance(errors,list) or not all(isinstance(value,str) for value in errors):raise ValueError('背景の未解決事項は文字列のリストで指定してください')
    if config['status'] == 'missing':
        if require_ready:
            raise ValueError('背景画像が未準備です。欠けた文字を描き直さず、青い固定印字を確認できる資料が必要です')
        return config
    if require_ready and config['status']!='ready':
        raise ValueError('背景候補は未確認です。住所・選択肢・固定印字と手書き除外を確認してください')
    if config['status']=='ready' and config.get('unresolved_text_errors'):
        raise ValueError('背景の未解決の誤字があります: '+' / '.join(config['unresolved_text_errors']))
    if config['status']=='ready' and config.get('kind') in ('original_blue', 'corrected_blue') and config.get('reviewed') is not True:
        raise ValueError('背景の固定印字・手書き除外・欠けを確認してください')
    if config.get('kind') == 'synthetic_test' and config.get('diagnostic_only') is not True:
        raise ValueError('人工背景は合成基盤の診断専用です')
    for key in ('width_mm', 'height_mm'):
        if not math.isfinite(float(config[key])) or abs(float(config[key])-float(template[key])) > .01:
            raise ValueError('背景と帳票の実寸が一致しません')
    data = config.get('image_png_base64', '')
    if not isinstance(data, str) or len(data) > MAX_BYTES*4//3+8:
        raise ValueError('背景画像が大きすぎます')
    return config


def mask_blank_regions(image, template):
    """Protect value areas on every render, independent of the uploaded bitmap."""
    result = image.convert('RGB').copy()
    draw = ImageDraw.Draw(result)
    for region in template.get('background_blank_regions_mm', []):
        x, y, w, h = map(float, region)
        if not all(math.isfinite(v) for v in (x, y, w, h)) or x < 0 or y < 0 or w <= 0 or h <= 0 or x+w > template['width_mm']+.001 or y+h > template['height_mm']+.001:
            raise ValueError('背景の空欄保持範囲が不正です')
        # Matte the interior; retain the cell border at the exact boundaries.
        left = math.floor(x/template['width_mm']*result.width)+1
        top = math.floor(y/template['height_mm']*result.height)+1
        right = math.ceil((x+w)/template['width_mm']*result.width)-2
        bottom = math.ceil((y+h)/template['height_mm']*result.height)-2
        if left<=right and top<=bottom:draw.rectangle((left, top, right, bottom), fill='white')
    return result


def load_background(template):
    config = validate_background(template, require_ready=True)
    try:
        raw = base64.b64decode(config['image_png_base64'], validate=True)
        if len(raw) > MAX_BYTES or hashlib.sha256(raw).hexdigest() != config.get('sha256'):
            raise ValueError('背景画像のハッシュが一致しません')
        with Image.open(io.BytesIO(raw)) as source:
            if source.format != 'PNG' or source.width*source.height > MAX_PIXELS:
                raise ValueError('背景は上限内のPNGで指定してください')
            ratio = source.width/source.height
            if abs(ratio/(template['width_mm']/template['height_mm'])-1) > .01:
                raise ValueError('背景の縦横比が外枠と一致しません')
            source.load()
            from blue_background import blue_pixels
            return mask_blank_regions(blue_pixels(source), template)
    except (KeyError, OSError, base64.binascii.Error) as error:
        raise ValueError('背景画像を読み取れません') from error


def encode_background(image, width_mm, height_mm, *, source_sha256, reviewed=False,
                      kind='original_blue', diagnostic_only=False, processing=None):
    buffer = io.BytesIO();image.convert('RGB').save(buffer, format='PNG')
    raw = buffer.getvalue()
    status='draft' if kind=='original_blue' and not reviewed else 'ready'
    return {'schema_version': 1, 'status': status, 'kind': kind, 'reviewed': reviewed,
            'diagnostic_only': diagnostic_only, 'width_mm': width_mm, 'height_mm': height_mm,
            'source_sha256': source_sha256, 'sha256': hashlib.sha256(raw).hexdigest(),
            'image_png_base64': base64.b64encode(raw).decode('ascii'), 'processing': processing or {}}
