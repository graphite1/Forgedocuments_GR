"""AC-only defaults and additive migration, selected by the stable form ID."""
from copy import deepcopy
import re
from ac_footer import migrate_footer

FORM_ID = 'ac_toyoake'
ADDRESS = '愛知県豊明市栄町神田182'
COMPANY = 'エーシートヨアケ'
VERSION = 1


def empty(value):
    return value is None or not str(value).strip()

SLOTS = {
    'company_name': ([210, 1138, 585, 60], 44),
    'company_address': ([210, 1104, 580, 34], 24),
    'company_contact': ([62, 1220, 900, 46], 26),
}


def migrate_template(template, form_id):
    """Never key migration on a display name, and never replace custom values.

    Old AC files lack form_id. Only the AC screen may identify those as AC.
    An explicit different form_id takes precedence over that screen context.
    """
    t = deepcopy(template)
    if form_id != FORM_ID or t.get('form_id', FORM_ID) != FORM_ID:
        return t
    t.setdefault('form_id', FORM_ID)
    first = t.get('ac_defaults_version', 0) < VERSION
    defaults = {'company_name': COMPANY, 'company_address': ADDRESS, 'company_contact': ''}
    for key, (box, size) in SLOTS.items():
        # Preserve legacy fixed text, including geometry, print=False and custom
        # addresses. Recognize untagged legacy footer text without company-name
        # equality or a particular template title.
        aliases = {key, key.removeprefix('company_')}
        fixed = next((i for i in t['fixed_texts'] if i.get('id') in aliases or i.get('value_key') == key), None)
        field = next((f for f in t['fields'] if f['id'] in aliases), None)
        if fixed is None and key == 'company_address':
            fixed = next((i for i in t['fixed_texts'] if i['box'][1] >= 1090 and re.search(r'(?:都|道|府|県).+(?:市|区|町|村)', i.get('text', ''))), None)
        if fixed is None and key == 'company_name':
            fixed = next((i for i in t['fixed_texts'] if i['box'][1] >= 1090 and re.search(r'エーシー|株式会社|有限会社|共同企業体', i.get('text', ''))), None)
        if fixed is None and key == 'company_contact':
            fixed = next((i for i in t['fixed_texts'] if i['box'][1] >= 1090 and re.search(r'TEL|FAX|電話|\d{2,4}[-−]\d{2,4}[-−]\d{3,4}', i.get('text', ''), re.I)), None)
        old = fixed.get('text', '') if fixed else field.get('default', '') if field else ''
        if key not in t:
            t[key] = old or defaults[key]
        elif first and key == 'company_address' and empty(t[key]):
            t[key] = old or ADDRESS
        if field is not None:
            if first and key == 'company_address' and empty(field.get('default', '')):
                field['default'] = t[key]
        elif fixed is not None:
            if first and key == 'company_address' and empty(old):
                if fixed.get('value_key') != key:
                    fixed['text'] = t[key]
            # Contradictory legacy scalar/fixed-text settings are ambiguous.
            # Keep both settings and the actually printed literal unchanged.
            if (fixed.get('value_key')==key or empty(old) or (first and str(t[key])==str(old))) and not (key=='company_address' and t.get('ac_footer_revision')):
                fixed.setdefault('value_key',key)
        else:
            t['fixed_texts'].append({'id': key, 'value_key': key, 'text': '', 'box': box, 'font': size, 'align': 'left', 'print': True})
    t.setdefault('random_print_enabled', False)
    t.setdefault('random_print_x_mm', 0.3)
    t.setdefault('random_print_y_mm', 0.3)
    # Legacy AC-only coordinates belong in the AC definition, not core.py.
    method=next((f for f in t['fields'] if f['id']=='method'),None)
    if method is not None:
        method.setdefault('choice_marks',{'1 持込':[808,927,38,38],'2 P渡':[808,981,38,38]})
        method.setdefault('mark_bounds',[802,920,198,110])
    receipt=next((f for f in t['fields'] if f['id']=='receipt_text'),None)
    if receipt is not None:receipt.setdefault('suppressed_by','receipt_image')
    if first:
        for item in t['fixed_texts']:
            if item.get('text') == '毎度 ありがとうございます。':
                item['text'] = '毎度 ありがとうございます'
    t['ac_defaults_version'] = VERSION
    return migrate_footer(t)
