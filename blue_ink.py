"""Independent blue artwork density; never edits source images or black input ink."""
import math

KEY='blue_ink_density'
MINIMUM=.35
MAXIMUM=1.5
NOTICE_MINIMUM=.65


def density(template):
    if isinstance(template.get(KEY),bool):raise ValueError('青印字の濃さは数値で指定してください')
    value=float(template.get(KEY,1))
    if not math.isfinite(value) or not MINIMUM<=value<=MAXIMUM:
        raise ValueError('青印字の濃さは35～150%で指定してください')
    return value


def color(rgb,value,notice=False):
    if not (rgb[2]>rgb[0] and rgb[2]>rgb[1]):return rgb
    if notice:value=max(NOTICE_MINIMUM,value)
    if value==1:return rgb
    return [max(0,min(1,1+(channel-1)*value)) for channel in rgb]


def image(source,value):
    """White-paper color scaling on blue pixels only, using a separate bitmap."""
    if value==1:return source
    from PIL import Image,ImageChops
    rgb=source.convert('RGB')
    red,green,blue=rgb.split()
    positive=lambda v:255 if v>0 else 0
    mask=ImageChops.multiply(ImageChops.subtract(blue,red).point(positive),
                            ImageChops.subtract(blue,green).point(positive))
    lut=[round(max(0,min(255,255+(v-255)*value))) for v in range(256)]
    adjusted=rgb.point(lut*3)
    return Image.composite(adjusted,rgb,mask)
