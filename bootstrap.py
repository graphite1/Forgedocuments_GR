"""Create an isolated virtual environment. Never change system packages."""
import importlib.util, os, subprocess, sys, venv
from pathlib import Path

base=Path(__file__).resolve().parent
target=base/'.venv'
python=target/'Scripts/python.exe'
try:
    if not python.exists():venv.EnvBuilder(with_pip=True).create(target)
    probe=subprocess.run([str(python),'-c',"import tkinter, reportlab, fitz;from PIL import Image,ImageTk,ImageWin"],capture_output=True)
    if probe.returncode:
        subprocess.check_call([str(python),'-m','pip','install','--disable-pip-version-check','-r',str(base/'requirements.txt')])
    subprocess.check_call([str(python),'-c','import tkinter,reportlab,fitz;from PIL import Image,ImageTk,ImageWin'])
    print('Setup completed. Run start.bat. / setup OK')
except Exception as e:
    print('Setup failed:',e)
    print('Use Python 3.11 or newer with tkinter, and check your internet connection.')
    sys.exit(1)
