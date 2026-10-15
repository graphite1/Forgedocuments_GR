"""Offline raw and explicitly scoped Fontspector reports; no automatic fixes."""
import argparse, hashlib, json, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
EXCLUSIONS={
 'opentype':['opentype/code_pages','opentype/xavgcharwidth'],
 'universal':['opentype/code_pages','opentype/xavgcharwidth','case_mapping','mandatory_glyphs','whitespace_glyphs'],
}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--exe',type=Path,default=ROOT/'.dev-tools/fontspector/1.9.0/fontspector.exe')
    parser.add_argument('--output',type=Path,default=ROOT/'test-results/fontspector-release')
    args=parser.parse_args()
    lock=json.loads((ROOT/'tools/fontspector.lock.json').read_text(encoding='utf8'))
    if hashlib.sha256(args.exe.read_bytes()).hexdigest()!=lock['executable_sha256']:raise ValueError('Unexpected Fontspector executable')
    sys.path.insert(0,str(ROOT))
    from tomei_print_font import validated_file
    font=validated_file();before=hashlib.sha256(font.read_bytes()).hexdigest()
    args.output.mkdir(parents=True,exist_ok=True);results=[]
    for profile in EXCLUSIONS:
        for scope in ['raw','subset']:
            stem=args.output/f'{profile}-{scope}'
            cmd=[str(args.exe),'--profile',profile,'--skip-network','--json',str(stem.with_suffix('.json')),'--ghmarkdown',str(stem.with_suffix('.md'))]
            if scope=='subset':
                for check in EXCLUSIONS[profile]:cmd+=['--exclude-checkid',check]
            cmd+=[str(font)]
            proc=subprocess.run(cmd,capture_output=True,text=True,encoding='utf8',errors='replace')
            stem.with_suffix('.stdout.txt').write_text(proc.stdout,encoding='utf8')
            stem.with_suffix('.stderr.txt').write_text(proc.stderr,encoding='utf8')
            report=json.loads(stem.with_suffix('.json').read_text(encoding='utf8'))
            results.append({'profile':profile,'scope':scope,'exit_code':proc.returncode,'summary':report['summary'],'argv':cmd})
    assert hashlib.sha256(font.read_bytes()).hexdigest()==before
    (args.output/'commands.json').write_text(json.dumps({'font_sha256':before,'font_unchanged':True,'runs':results},indent=2),encoding='utf8')
    print(json.dumps([{k:v for k,v in row.items() if k!='argv'} for row in results]))
    if any(row['exit_code'] or row['summary'].get('FAIL',0) or row['summary'].get('ERROR',0) for row in results if row['scope']=='subset'):raise SystemExit(1)

if __name__=='__main__':main()
