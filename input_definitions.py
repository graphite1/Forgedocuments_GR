"""Per-form candidate/default/fixed values; no company or form-specific text."""


def default_values(template):
    return {f['id']: str(f['fixed_value'] if f.get('fixed_value') is not None else f.get('default', '')) for f in template['fields']}


def validate_definitions(fields,validate_values):
    for f in fields:
        suggestions=f.get('suggestions',[])
        if not isinstance(suggestions,list) or not all(isinstance(v,str) for v in suggestions):raise ValueError('入力候補は文字列のリストで指定')
        if f.get('fixed_value') is not None and f['type'] not in ('text','decimal','integer','choice'):
            raise ValueError('固定値は文字・数値・選択項目に指定してください。日付・時刻・画像は個別入力です')
        for key in ('default','fixed_value'):
            if key in f and f[key] is not None:
                if not isinstance(f[key],str):raise ValueError('既定値・固定値は文字列で指定')
                if f[key]:
                    errors=validate_values({f['id']:f[key]},{'fields':[f]})
                    if errors:raise ValueError('既定値・固定値: '+' / '.join(errors))
