"""Bounded conservative symbol/direct/formed-address closure for an ARM64 image.

Uses only binary sections, symbol boundaries and generic instruction semantics.
Unknown indirect targets remain unknown and refuse at execution if absent.
"""
import argparse, base64, bisect, collections, hashlib, json, pathlib, time
import pypcode
from macho import macho

def node(v):
    return None if v is None else [v.space.name, v.offset, v.size]

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('snapshot',type=pathlib.Path)
p.add_argument('target',type=pathlib.Path)
p.add_argument('output',type=pathlib.Path)
p.add_argument('--seed-capsule',type=pathlib.Path,help='Optional previously observed/frozen IR and data ranges')
p.add_argument('--seed-entry',help='Required caller declaration if an older seed has no entry-symbol metadata')
args=p.parse_args()
base=json.loads(args.snapshot.read_text())
thin,segments,sections,symbols=macho(args.target.read_bytes())
if hashlib.sha256(thin).hexdigest()!=base['target']['thinSha256']:
    raise SystemExit('Frozen target identity mismatch')
entry=base['target']['entrySymbol']
slide=base['entry']-symbols['_'+entry]
text=next(s for s in sections if s['name']=='__text')
start,end=slide+text['va'],slide+text['va']+text['size']
stubs=next((s for s in sections if s['name']=='__stubs'),None)
stubstart=slide+stubs['va'] if stubs else 0
stubend=stubstart+stubs['size'] if stubs else 0
addresses=sorted(set(slide+a for a in symbols.values() if text['va']<=a<text['va']+text['size']))+[end]
names={slide+a:n for n,a in symbols.items()}
ctx=pypcode.Context('AARCH64:LE:64:v8A')
registers={name:node(v) for v,name in ctx.getAllRegisters().items()}
seed=json.loads(args.seed_capsule.read_text()) if args.seed_capsule else {}
if seed and seed['target']['thinSha256']!=base['target']['thinSha256']:
    raise SystemExit('Seed target identity mismatch')
# Re-lift seed addresses against this image rather than reusing IR containing a
# prior load slide. The native entry is caller-selected and must match the seed.
if seed and seed['target'].get('entrySymbol',args.seed_entry)!=entry:
    raise SystemExit('Seed entry must match selected root; older seeds require --seed-entry')
delta=base['entry']-seed['entry'] if seed else 0
ops={};userops={}
queue=collections.deque([base['entry'],*[int(a)+delta for a in seed.get('ops',{})],*range(stubstart,stubend,12)])
done=set();stubdone=set();notes=[];began=time.monotonic()
def raw(address,n):
    sec=stubs if stubstart<=address<stubend else text
    offset=sec['fileoff']+address-(slide+sec['va'])
    return thin[offset:offset+n]
while queue:
    if len(ops)>=100000 or time.monotonic()-began>30:
        raise RuntimeError('Closure budget exceeded; no partial capsule exported')
    a=queue.popleft()
    if stubstart<=a<stubend:
        s=stubstart+(a-stubstart)//12*12;e=s+12
        if s in stubdone:continue
        stubdone.add(s)
    elif start<=a<end:
        i=bisect.bisect_right(addresses,a)-1;s,e=addresses[i],addresses[i+1]
        if s in done:continue
        done.add(s)
    else:continue
    known={}
    for pc in range(s,e,4):
        translated=[]
        for op in ctx.translate(raw(pc,4),pc,max_instructions=1).ops:
            name=op.opcode.name
            if name=='IMARK':continue
            if name=='CALLOTHER':userops[str(op.inputs[0].offset)]=op.inputs[0].getUserDefinedOpName()
            translated.append((name,node(op.output),[node(v) for v in op.inputs]))
            def key(v):return(v.space.name,v.offset,v.size)
            values=[v.offset if v.space.name=='const' else known.get(key(v)) for v in op.inputs]
            value=None
            if name=='COPY' and values[0] is not None:value=values[0]
            elif name in ('INT_ADD','INT_SUB') and all(v is not None for v in values):
                value=values[0]+values[1] if name=='INT_ADD' else values[0]-values[1]
            if op.output is not None:
                known.pop(key(op.output),None)
                if value is not None:
                    value&=(1<<(op.output.size*8))-1;known[key(op.output)]=value
                    if start<=value<end and value%4==0:queue.append(value)
            if name in ('CALL','BRANCH','CBRANCH') and op.inputs[0].space.name=='ram':queue.append(op.inputs[0].offset)
            if name in ('CALLIND','BRANCHIND'):notes.append(dict(address=hex(pc),indirect=True))
            if name in ('CALL','CALLIND','BRANCH','CBRANCH','BRANCHIND','RETURN'):known.clear()
        ops[str(pc)]=translated
regions=[]
for sec in sections:
    if sec['name'] in ('__text','__stubs','__stub_helper','__unwind_info'):continue
    a=slide+sec['va']
    for r in base['regions']:
        data=base64.b64decode(r['bytes'])
        if r['address']<=a and a+sec['size']<=r['address']+len(data):
            regions.append(dict(address=a,name=sec['segment']+':'+sec['name'],writable=r['writable'],
                                bytes=base64.b64encode(data[a-r['address']:a-r['address']+sec['size']]).decode()));break
regions.extend(r for r in base['regions'] if r['name']=='explicit-stack-guard')
for r in seed.get('regions',[]):
    a=r['address']+delta;n=len(base64.b64decode(r['bytes']))
    if not start<=a<a+n<=end:continue
    for current in base['regions']:
        data=base64.b64decode(current['bytes'])
        if current['address']<=a and a+n<=current['address']+len(data):
            regions.append(dict(address=a,name='observed-text-data',writable=False,
              bytes=base64.b64encode(data[a-current['address']:a-current['address']+n]).decode()));break
base.update(regions=regions,ops=ops,registers=registers,userops=userops,
    closure=dict(strategy='conservative-symbol-direct-formed-address-and-import-closure',functions=len(done),
                 symbolNames=[names.get(a,hex(a)) for a in sorted(done)],instructions=len(ops),
                 importTrampolines=len(stubdone),truncated=False,unprocessedTargets=0,notes=notes,
                 textAddresses=sum(start<=int(a)<end for a in ops),wholeTextBytes=text['size'],
                 totalTextSymbolBodies=len(addresses)-1),
    limitations=['conservative incomplete closure; unknown paths/dependencies refuse; minimality not proved',
                 'all initialized non-code sections retained; no source/specification consumed',
                 'no target binary or lifter used by closed runtime'])
with args.output.open('x') as f:json.dump(base,f)
print(json.dumps(dict(functions=len(done),instructions=len(ops),dataBytes=sum(len(base64.b64decode(r['bytes'])) for r in regions))))
