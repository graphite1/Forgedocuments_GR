"""Compile millimetre coordinates separately from an input schema."""
import copy
import math


def apply_coordinates(template, definition):
    if definition.get('schema_version') != 1 or definition.get('unit') != 'mm':
        raise ValueError('未対応の入力座標定義です')
    result = copy.deepcopy(template)
    sx = float(result.get('coordinate_width', 1000)) / float(result['width_mm'])
    sy = float(result.get('coordinate_height', 1300)) / float(result['height_mm'])
    fields = {f['id']: f for f in result['fields']}
    entries = definition['fields']
    ids = [item['id'] for item in entries]
    if len(ids) != len(set(ids)):
        raise ValueError('入力座標IDが重複しています')

    def box(values):
        if len(values) != 4 or not all(math.isfinite(float(v)) for v in values):
            raise ValueError('入力座標が不正です')
        x, y, w, h = map(float, values)
        if x < 0 or y < 0 or w <= 0 or h <= 0:
            raise ValueError('入力座標と印字範囲は正数で指定してください')
        return [x*sx, y*sy, w*sx, h*sy]

    for item in entries:
        field = fields.get(item['id'])
        if field is None or not field.get('input', True) or field['type'] == 'layout_only':
            raise ValueError('入力可能な項目の座標だけを指定してください')
        if set(item) - {'id', 'box_mm', 'parts_mm', 'font_mm', 'min_font_mm', 'align', 'options'}:
            raise ValueError('座標定義から項目の型・入力可否・値は変更できません')
        field['box'] = box(item['box_mm'])
        if 'parts_mm' in item:
            if field['type'] not in ('date', 'time'):
                raise ValueError('年月日・時分だけを分割配置できます')
            field['parts'] = [box(b) for b in item['parts_mm']]
            if len(field['parts']) != (3 if field['type'] == 'date' else 2):
                raise ValueError('年月日・時分の座標数が不正です')
        for key in ('font', 'min_font'):
            if key+'_mm' in item:
                size = float(item[key+'_mm'])
                if not math.isfinite(size) or size <= 0:
                    raise ValueError('文字サイズは正数です')
                field[key] = size*sy
        if 'align' in item:
            if item['align'] not in ('left', 'center', 'right'):
                raise ValueError('文字配置が不正です')
            field['align'] = item['align']
        if 'options' in item:
            if field['type'] != 'multi_choice':
                raise ValueError('選択記号の座標は選択項目だけに指定できます')
            options = {o['key']: o for o in field['options']}
            if set(o['key'] for o in item['options']) != set(options):
                raise ValueError('選択肢を変更せず位置だけを指定してください')
            for option in item['options']:
                if set(option) != {'key', 'box_mm'}:
                    raise ValueError('背景の選択肢を描き直しません')
                options[option['key']]['box'] = box(option['box_mm'])
    return result
