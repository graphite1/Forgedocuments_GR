"""Create release-bound publish proofs; never export the private key."""
import argparse,base64,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from build_windows import signing_key

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('manifest');p.add_argument('output');a=p.parse_args()
    m=json.loads(Path(a.manifest).read_text(encoding='utf-8'));key,key_id,_=signing_key()
    if m['key_id']!=key_id:raise ValueError('Signing key ID mismatch')
    proofs={method:base64.b64encode(key.sign(f"gr-release-agent-v1\n{method}\n{m['app_id']}\n{m['sequence']}\n{m['sha256']}".encode())).decode() for method in ('PUT','POST')}
    Path(a.output).write_text(json.dumps(proofs),encoding='utf-8');print('Release-bound agent proofs prepared')
