"""Explicit image-specific geometry; never migrate a user's custom coordinates."""
import copy
import json
from pathlib import Path
from input_coordinates import apply_coordinates

PROFILE = 'generated-20261014'
COORDINATES = 'tomei_taiheiyo.generated-20261014.coordinates.json'
CROP = [26, 33, 1044, 1450]


def image_profile(template):
    """Return an opt-in profile for the supplied 1070 x 1470 corrected image.

    Pixel geometry is measured. The 118.3 mm outer width remains provisional;
    height follows the bitmap's aspect ratio, without stretching the image.
    Existing defaults/candidates stay in the copy; the caller retains history.
    """
    t = copy.deepcopy(template)
    t.update(layout_profile=PROFILE, width_mm=118.3, height_mm=1417*118.3/1018,
             content_height_mm=1477*118.3/1018,
             coordinate_width=1018, coordinate_height=1417)
    t.pop('coordinate_definition', None)
    t['coordinate_source'] = COORDINATES
    def box(x, y, w, h):
        return [x-26, y-33, w, h]
    fields = {f['id']: f for f in t['fields']}
    for key, rect in {
        'arrival_time': (679, 506, 361, 59),
        'recipient_sign_status': (294, 1341, 250, 61),
        'shipping_staff_status': (804, 1341, 235, 61),
    }.items():
        fields[key]['box'] = box(*rect)
    headings = {
        'recipient_sign_heading': box(29, 1342, 260, 56),
        'shipping_sign_heading': box(550, 1342, 248, 56),
        'original_title': box(180, 45, 710, 52),
        'copy_notice': [620, 1435, 390, 36],
    }
    t['fixed_texts'] = [i for i in t['fixed_texts'] if i.get('id') in headings]
    for item in t['fixed_texts']:
        item['box'] = headings[item['id']]
        if item['id'] == 'copy_notice':
            item.update(font=27, min_font=27, align='right', wrap=False)
    t['lines'] = []  # All blue rules are supplied by the bitmap.
    scale = 118.3/1018
    t['background_blank_regions_mm'] = [
        [v*scale for v in box(*r)] for r in (
            (680, 505, 213, 61), (934, 505, 68, 61),
            (294, 1341, 250, 61), (804, 1341, 235, 61))]
    definition = json.loads((Path(__file__).parent/'templates'/COORDINATES).read_text(encoding='utf-8'))
    t = apply_coordinates(t, definition)
    for option in next(f for f in t['fields'] if f['id']=='mix_basis')['options']:
        x, y, w, h = option['box']
        option['label_box'] = [x+w+5, y, min(100, 1018-x-w-6), h]
    t['source_confirmation'].update(
        new_background_library_id='libfile_bec939d82fa48191940458f8cd81af4e',
        new_background_pixels_checked=True, local_explanation_bytes_available=True,
        geometry_and_font='image-specific measured cells; provisional physical width; Windows font unverified')
    return t
