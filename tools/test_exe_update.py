"""Isolated signed exe update exercise. Never touches the user's records."""
import json,os,shutil,sys
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
import updates
from core import Store,blank,load_template,atomic_json

if __name__=='__main__':
    archive,manifest,destination=sys.argv[1:];target=Path(destination).resolve();target.mkdir(parents=True,exist_ok=False)
    root=target/'app';root.mkdir();data=target/'records'
    m=json.loads(Path(manifest).read_text(encoding='utf-8'))
    # The package is the genuine new release; only the test's current-version check is lowered.
    old={'app_id':m['app_id'],'version':'1.2.0','sequence':0,'data_schema':1,'updater_version':'1.0.0'}
    with patch.object(updates,'metadata',return_value=old):directory=updates.stage_archive(archive,m,root)
    shutil.copy2(directory/updates.EXE,root/updates.EXE)
    s=Store(data);t=load_template();d=blank(t);d['number']='00007-KEEP';s.save(d,t);s.set_template(t);s.close()
    profile=target/'profile'/'ForgedocumentsGR';profile.mkdir(parents=True)
    atomic_json(profile/'profiles.json',{'ac_toyoake':str(data)})
    os.environ['APPDATA']=str(profile.parent);os.environ['FORGEDOCUMENTS_INSTALL_ROOT']=str(root)
    os.environ['FORGEDOCUMENTS_SKIP_ROUTE']='1'
    with patch.object(sys,'frozen',True,create=True),patch.object(sys,'executable',str(root/updates.EXE)):
        updates.request_apply(directory,[str(data)])
    print(json.dumps({'root':str(root),'data':str(data),'stage':str(directory)}))
