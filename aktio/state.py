"""Form-scoped persistence. Validate copies before replacing live screen state."""
import copy
from core import Store,load_template
from pathlib import Path
from . import receipt
from .planning import validate_plan

FORM_ID='aktio_receipt'
DEFINITION=Path(__file__).resolve().parent.parent/'templates/aktio_receipt.json'


def checked_document(data):
    if not isinstance(data,dict) or data.get('form_id',FORM_ID)!=FORM_ID:
        raise ValueError('AKTIO以外の保存データは読み込めません')
    if data.get('schema_version',1)!=1:raise ValueError('未対応のAKTIO保存バージョンです')
    if not any(k in data for k in ('settings','config')):raise ValueError('AKTIOの設定がありません')
    result=copy.deepcopy(data)
    if not isinstance(result.get('settings',{}),dict):raise ValueError('設定の形式が不正です')
    if result.get('measurement_mode','count') not in ('fixed','count'):raise ValueError('作成方法が不正です')
    vehicles=result.get('vehicles',[])
    if not isinstance(vehicles,list):raise ValueError('車両条件の形式が不正です')
    for vehicle in vehicles:
        if not isinstance(vehicle,dict) or not isinstance(vehicle.get('vehicle'),str):raise ValueError('車両名がありません')
        if any(type(vehicle.get(k)) is not int for k in ('runs','tare_kg','max_payload_kg','max_gross_kg','target_payload_kg','weight_jitter_kg')):
            raise ValueError('車両の重量条件がありません')
        fixed=vehicle.get('fixed_measurements',[])
        if not isinstance(fixed,list) or any(not isinstance(m,dict) or 'time' not in m or 'sn' not in m for m in fixed):
            raise ValueError('指定計量の形式が不正です')
    rests=result.get('extra_breaks',[])
    if not isinstance(rests,list) or any(not isinstance(r,(list,tuple)) or len(r)!=2 for r in rests):raise ValueError('休憩の形式が不正です')
    plan=result.get('records',[])
    if not isinstance(plan,list) or any(r.get('mode')!='simulation' for r in plan):
        raise ValueError('計画に実測記録が混在しています')
    if plan:
        config=result.get('generated_config') or result.get('config')
        vehicles=result.get('generated_vehicles') or result.get('vehicles')
        # Legacy plans lack the initial tare: retain settings, require regeneration.
        first={}
        for r in sorted(plan,key=lambda r:r['time']):first.setdefault(r['vehicle'],r)
        if any(r.get('category')!='空車' or 'haul_trip' not in r for r in first.values()):
            result['records']=[];result['generated_config']=None;result['generated_vehicles']=None
        else:
            if not config or not vehicles:raise ValueError('計画の生成条件がありません')
            validate_plan(plan,config,vehicles)
            result['generated_config']=copy.deepcopy(config);result['generated_vehicles']=copy.deepcopy(vehicles)
    items=result.get('measured_records',[])
    if not isinstance(items,list):raise ValueError('計量記録の形式が不正です')
    seen=set()
    for item in items:
        if not isinstance(item,dict) or not isinstance(item.get('raw'),dict) or not isinstance(item.get('mapping'),dict):
            raise ValueError('計量記録の入力と見出しがありません')
        if not isinstance(item.get('changes',[]),list):raise ValueError('訂正履歴の形式が不正です')
        row=item.get('row')
        if type(row) is not int or row<1 or row in seen:raise ValueError('計量記録の行番号が不正または重複しています')
        seen.add(row)
        record=item.get('record')
        if record is not None:
            if record.get('mode','measured')!='measured':raise ValueError('実測欄に計画を読み込めません')
            prepared=receipt.prepare_record(row,item['raw'],item['mapping'],item.get('default_tare'))
            old=dict(record);old.setdefault('mode','measured')
            if old!=prepared:raise ValueError('計量入力と保存された計量値が一致しません')
            item['record']=prepared
    result.update(form_id=FORM_ID,schema_version=1)
    return result


class SessionStore(Store):
    def __init__(self,directory):
        super().__init__(directory,default_template=load_template(DEFINITION),form_id=FORM_ID)
        try:
            self.template()  # Keep the shared form-identity checks and settings history.
            self.db.execute('CREATE TABLE IF NOT EXISTS aktio_session (id INTEGER PRIMARY KEY CHECK(id=1), document TEXT NOT NULL)')
            self.db.commit();self._session_text=None
        except Exception:self.close();raise

    def load_session(self):
        import json
        row=self.db.execute('SELECT document FROM aktio_session WHERE id=1').fetchone()
        result=checked_document(json.loads(row[0])) if row else None
        self._session_text=row[0] if row else None
        return result

    def save_session(self,data):
        import json
        payload=json.dumps(checked_document(data),ensure_ascii=False)
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            current=self.db.execute('SELECT document FROM aktio_session WHERE id=1').fetchone()
            if (current[0] if current else None)!=self._session_text:
                raise ValueError('別の画面で保存データが変更されました。現在の入力をJSONへ退避して再読込してください')
            self.db.execute('INSERT INTO aktio_session VALUES(1,?) ON CONFLICT(id) DO UPDATE SET document=excluded.document',(payload,))
        self._session_text=payload
