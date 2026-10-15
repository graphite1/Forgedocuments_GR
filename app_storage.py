"""Automatic per-form storage and conservative import of legacy user folders.

Legacy files are read/copied only. Never merge two forms or reset an existing
automatic destination. Backups include the DB/WAL and original portable settings.
"""
import hashlib,json,os,re,shutil,sqlite3,tempfile,uuid
from datetime import datetime,timezone
from pathlib import Path

FILES=('records.sqlite3','records.sqlite3-wal','records.sqlite3-shm','records.sqlite3-journal','template.json')
MARKER='.form-storage.json'


class StorageError(ValueError):pass


def _remove_temporary(path,parent):
    path=Path(path);parent=Path(parent).resolve()
    if path.resolve()==parent or not path.resolve().is_relative_to(parent):raise StorageError('一時フォルダーの範囲を確認できません')
    shutil.rmtree(path)


def _write_json(path,value):
    from core import atomic_json
    atomic_json(path,value)


def _probe(directory):
    directory.mkdir(parents=True,exist_ok=True)
    name=directory/('.write-check-'+uuid.uuid4().hex)
    try:
        with name.open('xb') as f:f.write(b'check');f.flush();os.fsync(f.fileno())
    finally:
        if name.exists():name.unlink()


def _snapshot(source,target):
    """Copy a stable set; retain WAL and never open the original database."""
    source=Path(source);target=Path(target);target.mkdir(parents=True,exist_ok=False)
    for attempt in range(3):
        before={name:(source/name).read_bytes() for name in FILES if (source/name).is_file()}
        stable={name:raw for name,raw in before.items() if name!='records.sqlite3-shm'}
        after={name:(source/name).read_bytes() for name in FILES if name!='records.sqlite3-shm' and (source/name).is_file()}
        if stable!=after:continue
        for name,raw in before.items():(target/name).write_bytes(raw)
        return {name:hashlib.sha256(raw).hexdigest() for name,raw in before.items()}
    raise StorageError('旧保存先が更新中のため、安全なコピーを作成できません。旧版を閉じてから起動し直してください。')


def _settings(directory):
    """DB settings are authoritative; only use template.json if DB has none."""
    db=directory/'records.sqlite3';has_records=False
    if db.exists():
        con=sqlite3.connect(db)
        try:
            if con.execute('pragma integrity_check').fetchone()[0]!='ok':raise StorageError('保存データの整合性を確認できません')
            tables={r[0] for r in con.execute("select name from sqlite_master where type='table'")}
            has_records='records' in tables and bool(con.execute('select count(*) from records').fetchone()[0])
            if 'settings' in tables:
                row=con.execute('select after_json from settings order by seq desc limit 1').fetchone()
                if row:
                    template=json.loads(row[0])
                    if not isinstance(template,dict):raise StorageError('保存された設定の形式を確認できません。元データを上書きせず停止しました。')
                    return template
        finally:con.close()
    path=directory/'template.json'
    if path.is_file():return json.loads(path.read_text(encoding='utf-8-sig'))
    if has_records:raise StorageError('記録はありますが帳票種別を確認する設定がありません。元データをバックアップして保全し、取り込みを停止しました。')
    return None


def _belongs(template,expected):
    if not template:return False
    if 'form_id' in template:return template['form_id']==expected['form_id']
    # Only identified legacy field definitions can be imported without a form id.
    fields={f['id'] for f in template.get('fields',[])}
    return bool(fields) and {f['id'] for f in expected['fields']}<=fields


class AppStorage:
    def __init__(self,root,legacy_profiles=None,legacy_profile_file=None):
        self.root=Path(root).resolve();self.data=self.root/'data'
        self.legacy=dict(legacy_profiles or {});self.legacy_profile_file=legacy_profile_file
        self.notices={}

    def path(self,form_id):
        if not re.fullmatch(r'[a-z][a-z0-9_]*',form_id):raise StorageError('帳票IDが不正です')
        target=self.data/form_id
        if not self.data.resolve().is_relative_to(self.root):raise StorageError('自動保存フォルダーがアプリの外を指しています')
        if not target.resolve().is_relative_to(self.data.resolve()):raise StorageError('保存先がアプリのデータフォルダー外を指しています')
        return target

    def prepare(self,expected):
        fid=expected['form_id'];target=self.path(fid)
        try:
            _probe(self.data)
            if target.exists():
                _probe(target)
                marker=target/MARKER
                if marker.exists() and json.loads(marker.read_text(encoding='utf8')).get('form_id')!=fid:
                    raise StorageError('自動保存先に別の帳票の識別情報があります。元データを上書きせず停止しました。')
                # Inspect copies even for existing destinations: no schema changes
                # or migration before the stored form identity is verified.
                with tempfile.TemporaryDirectory(prefix='.inspect-',dir=self.data) as temp:
                    snapshot=Path(temp)/'snapshot';_snapshot(target,snapshot)
                    template=_settings(snapshot)
                    if template and not _belongs(template,expected):raise StorageError('自動保存先に別の帳票の設定があります。元データを上書きせず停止しました。')
                if not marker.exists():_write_json(marker,{'layout_version':1,'form_id':fid})
                return target
            stage=self.data/('.new-'+fid+'-'+uuid.uuid4().hex);stage.mkdir()
            try:
                source_value=self.legacy.get(fid)
                source=Path(source_value).resolve() if source_value else None
                if source and source.is_dir() and any((source/name).is_file() for name in FILES):
                    backup=self.data/'backups'/('import-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'-'+uuid.uuid4().hex[:6])/fid
                    backup.parent.mkdir(parents=True,exist_ok=True)
                    hashes=_snapshot(source,backup)
                    if self.legacy_profile_file and Path(self.legacy_profile_file).is_file():
                        shutil.copyfile(self.legacy_profile_file,backup/'legacy-profiles.json')
                    _write_json(backup/'source.json',{'source':str(source),'requested_form':fid,'sha256':hashes})
                    # Never open the immutable backup itself with SQLite.
                    work=stage/'inspection';shutil.copytree(backup,work)
                    try:
                        template=_settings(work)
                        if template and _belongs(template,expected):
                            if (work/'records.sqlite3').exists():
                                con=sqlite3.connect(work/'records.sqlite3');out=sqlite3.connect(stage/'records.sqlite3')
                                try:con.backup(out)
                                finally:out.close();con.close()
                            _write_json(stage/'template.json',template)
                            self.notices[fid]='旧保存先のデータ・色設定をバックアップし、帳票専用の自動保存先へコピーしました。'
                        else:
                            self.notices[fid]='旧保存先は別帳票の設定でした。元データをバックアップして保全し、この帳票専用の保存先を作成しました。'
                    finally:_remove_temporary(work,stage)
                _write_json(stage/MARKER,{'layout_version':1,'form_id':fid})
                # rename fails if another process has created target; never replace it.
                stage.rename(target)
            finally:
                if stage.exists():_remove_temporary(stage,self.data)
            return target
        except StorageError:raise
        except json.JSONDecodeError as error:
            raise StorageError('保存先の設定ファイルを読めません。元データを上書きせず停止しました。\n'+str(target)) from error
        except sqlite3.Error as error:
            raise StorageError('保存データを読み込めません。元データを上書きせず停止しました。\n'+str(target)+'\n'+str(error)) from error
        except OSError as error:
            raise StorageError('アプリのフォルダー内の保存先を使用できません。\n'+str(target)+
                '\nZIPを「ドキュメント」など書き込み可能なフォルダーへ展開し、その中のexeを起動してください。保存先の指定は不要です。\n旧保存先のデータは変更していません。\n'+str(error)) from error


def open_folder(directory):
    path=Path(directory)
    if not path.is_dir():raise StorageError('保存フォルダーがまだありません。帳票を開いてから実行してください。')
    if hasattr(os,'startfile'):os.startfile(str(path))
    else:raise StorageError('保存フォルダー: '+str(path))
