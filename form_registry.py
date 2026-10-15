"""A form is a screen module plus metadata; each form owns its data and logic."""
import importlib,json,re
from pathlib import Path

BASE=Path(__file__).resolve().parent

def catalog(path=None):
    rows=json.loads(Path(path or BASE/'forms.json').read_text(encoding='utf-8'))
    ids=set()
    for row in rows:
        if not re.fullmatch(r'[a-z][a-z0-9_]*',row['id']) or row['id'] in ids:raise ValueError('帳票IDが不正または重複しています')
        if not re.fullmatch(r'[a-z][a-z0-9_.]*',row['module']):raise ValueError('帳票画面の指定が不正です')
        if row.get('template'):
            path=(BASE/row['template']).resolve()
            if not path.is_relative_to(BASE.resolve()) or path.suffix!='.json' or not path.is_file():raise ValueError('帳票定義のパスが不正です')
        ids.add(row['id'])
    return rows

def open_screen(row,root,directory):
    factory=getattr(importlib.import_module(row['module']),'App')
    return factory(root,directory)


def default_definition(row):
    from core import load_template
    return load_template(BASE/row.get('template','template.json'))
