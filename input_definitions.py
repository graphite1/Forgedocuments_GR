"""Per-form candidate/default/fixed values; no company or form-specific text."""


def default_values(template):
    return {f['id']: '' if f.get('input',True) is False or f['type']=='layout_only' else str(f['fixed_value'] if f.get('fixed_value') is not None else f.get('default', '')) for f in template['fields']}


def validate_definitions(fields,validate_values):
    for f in fields:
        if f['type']=='layout_only' and (f.get('input',False) or f.get('print',False) or f.get('default','') or f.get('fixed_value')):
            raise ValueError('空欄保持欄は入力・描画・既定値を設定できません')
        suggestions=f.get('suggestions',[])
        if not isinstance(suggestions,list) or not all(isinstance(v,str) for v in suggestions):raise ValueError('入力候補は文字列のリストで指定')
        if f.get('fixed_value') is not None and f['type'] not in ('text','decimal','integer','choice'):
            raise ValueError('固定値は文字・数値・選択項目に指定してください。日付・時刻・画像は個別入力です')
        for key in ('default','fixed_value'):
            if key in f and f[key] is not None:
                if not isinstance(f[key],str):raise ValueError('既定値・固定値は文字列で指定')
                if f[key]:
                    definition=dict(f,input=True) if f.get('input',True) is False else f
                    errors=validate_values({f['id']:f[key]},{'fields':[definition]})
                    if errors:raise ValueError('既定値・固定値: '+' / '.join(errors))
