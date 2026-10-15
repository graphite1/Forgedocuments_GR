"""Archive exactly one clean commit as source, never as a signed EXE release."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parent.parent


def package(output):
    if subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip():
        raise RuntimeError('変更を確認してコミットしてからソースZIPを作成してください')
    sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    version=json.loads(subprocess.check_output(['git','show',sha+':version.json'],cwd=ROOT))
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    archive=output/f"Forgedocuments_GR-{version['version']}-source.zip"
    if archive.exists():raise FileExistsError(archive)
    subprocess.run(['git','archive','--format=zip','--prefix=Forgedocuments_GR/','--output',str(archive),sha],cwd=ROOT,check=True)
    manifest={'artifact_type':'source_archive','source_commit':sha,'version':version['version'],'sequence':version['sequence'],
              'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'size_bytes':archive.stat().st_size,'windows_exe_built':False,'signed':False}
    assets=subprocess.check_output(['git','ls-tree','-r','--name-only',sha,'--','assets','aktio/assets'],cwd=ROOT,text=True).splitlines()
    manifest['bundled_public_assets']=[{'path':name,'sha256':hashlib.sha256(subprocess.check_output(['git','show',sha+':'+name],cwd=ROOT)).hexdigest()} for name in assets]
    (output/f"Forgedocuments_GR-{version['version']}-source.manifest.json").write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(dict(manifest,archive=str(archive))))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True)
    package(parser.parse_args().output)
