"""Explicit source setup and launch using an isolated venv and data root."""
import argparse,os,struct,subprocess,sys,venv
from pathlib import Path
BASE=Path(__file__).resolve().parent
VENV=BASE/'.source-venv'
RUNTIME=BASE/'source-runtime'


def check_python():
    if sys.version_info[:2]!=(3,14) or struct.calcsize('P')!=8:
        raise RuntimeError('Python 3.14 x64が必要です。PythonやPATHを自動変更しません。')
    import tkinter,ensurepip  # Import checks only; never create a GUI during setup.


def environment(base=BASE):
    root=(Path(base)/'source-runtime').resolve()
    return dict(os.environ,FORGEDOCUMENTS_INSTALL_ROOT=str(root),FORGEDOCUMENTS_SKIP_ROUTE='1',
                APPDATA=str(root/'profile'),LOCALAPPDATA=str(root/'local'),PYTHONUTF8='1')


def venv_python():return VENV/('Scripts/python.exe' if os.name=='nt' else 'bin/python')


def verify_venv():
    if VENV.is_symlink() or not VENV.resolve().is_relative_to(BASE):raise RuntimeError('ソース版venvの保存先を確認できません')
    python=venv_python()
    if not python.is_file():raise RuntimeError('初回はsetup_source.batを実行してください')
    code="import json,sys,struct;print(json.dumps([sys.prefix,list(sys.version_info[:2]),struct.calcsize('P')]))"
    import json
    prefix,version,bits=json.loads(subprocess.check_output([str(python),'-c',code],text=True))
    if Path(prefix).resolve()!=VENV.resolve() or version!=[3,14] or bits!=8:raise RuntimeError('ソース専用Python環境を確認できません。システム環境へは導入しません。')
    return python


def setup():
    check_python()
    if VENV.is_symlink() or not VENV.resolve().is_relative_to(BASE):raise RuntimeError('ソース版venvの保存先を確認できません')
    if not VENV.exists():venv.EnvBuilder(with_pip=True).create(VENV)
    python=verify_venv()
    subprocess.run([str(python),'-m','pip','install','--no-cache-dir','--disable-pip-version-check','-r',str(BASE/'requirements.txt')],check=True,cwd=BASE)
    subprocess.run([str(python),'-c','import tkinter,reportlab,pymupdf,cryptography,charset_normalizer;from PIL import Image,ImageTk,ImageWin'],check=True)
    print('Source setup complete. Run start_source.bat.')


def run(arguments):
    python=verify_venv()
    return subprocess.run([str(python),'-B',str(BASE/'app.py'),*arguments],cwd=BASE,env=environment()).returncode


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('operation',choices=['setup','run']);parser.add_argument('arguments',nargs=argparse.REMAINDER)
    args=parser.parse_args()
    try:
        if args.operation=='setup':setup()
        else:raise SystemExit(run(args.arguments))
    except Exception as error:
        print('Source startup/setup failed: '+str(error));raise SystemExit(1)
