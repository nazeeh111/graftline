"""Bind a frozen extracted program to a caller-declared register/buffer ABI."""
import argparse,hashlib,json,pathlib
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('capsule',type=pathlib.Path);p.add_argument('abi',type=pathlib.Path)
p.add_argument('output',type=pathlib.Path);p.add_argument('--name',required=True)
p.add_argument('--expected-capsule-sha256',required=True)
a=p.parse_args();data=a.capsule.read_bytes();digest=hashlib.sha256(data).hexdigest()
if digest!=a.expected_capsule_sha256:raise SystemExit('Capsule SHA256 mismatch')
c=json.loads(data);closure=c.get('closure',{})
if closure.get('truncated',True) or closure.get('unprocessedTargets',1) or str(c['entry']) not in c.get('ops',{}):
 raise SystemExit('Capsule lacks a finished bounded closure')
abi=json.loads(a.abi.read_text())
manifest=dict(schema=1,name=a.name,entrySymbol=c['target']['entrySymbol'],entry=c['entry'],
 capsuleSha256=digest,target=c['target'],abi=abi,
 sourceBoundary='implementation source/specification withheld; public ABI declarations and license permitted',
 refusalModel='unknown branch/opcode/dependency, memory/budget error or undeclared boundary refuses')
with a.output.open('x') as f:json.dump(manifest,f,indent=2)
print(json.dumps(dict(name=a.name,capsuleSha256=digest)))
