"""Caller-declared buffer/scalar ABI for closed native feature programs."""
import hashlib, json, pathlib
from .runtime import VM

class Refusal(RuntimeError):
    """An input, closed dependency or declared boundary cannot be supported."""

class Feature:
    def __init__(self, directory):
        self.directory = pathlib.Path(directory)
        self.manifest = json.loads((self.directory/'feature.json').read_text())
        if self.manifest.get('schema') != 1:
            raise Refusal('Unsupported feature manifest schema')
        try:
            abi=self.manifest['abi'];arguments=abi['arguments'];ret=abi['return']
            if set(abi) != {'arguments','return'}:
                raise Refusal('Unsupported ABI declaration fields')
            if not isinstance(arguments,list) or not 1<=len(arguments)<=8:
                raise Refusal('ABI requires one to eight declared register arguments')
            names=set();scalars=set();outputs=set();counts={}
            for a in arguments:
                kind=a['kind']
                if kind not in ('input','input-length','scalar','output','pointer-cell'):
                    raise Refusal('Unsupported declared argument kind')
                counts[kind]=counts.get(kind,0)+1
                fields={'kind'} if kind in ('input','input-length') else {'kind','name'}
                if kind=='scalar':fields|={'minimum','maximum','bits','signed'}
                if set(a)-fields:
                    raise Refusal('Unsupported argument declaration fields')
                if kind in ('scalar','output','pointer-cell'):
                    name=a['name']
                    if not isinstance(name,str) or name in names:
                        raise Refusal('ABI names must be unique strings')
                    names.add(name)
                    if kind=='scalar':
                        if type(a.get('bits',64)) is not int or a.get('bits',64)!=64 or a.get('signed',False) is not False:
                            raise Refusal('Only unsigned 64-bit scalar arguments are supported')
                        if type(a['minimum']) is not int or type(a['maximum']) is not int or not 0<=a['minimum']<=a['maximum']<1<<64:
                            raise Refusal('Invalid scalar bounds')
                        scalars.add(name)
                    else:outputs.add(name)
            if counts.get('input')!=1 or counts.get('input-length')!=1:
                raise Refusal('ABI requires exactly one input buffer and one input length')
            if len(outputs)!=1 or type(ret['signed']) is not bool:
                raise Refusal('ABI requires exactly one result buffer/cell and signedness')
            if ret['kind']=='buffer':
                if set(ret)-{'kind','signed','bits','address','capacity'} or ret['signed'] is not False:
                    raise Refusal('Buffer return requires unsigned 64-bit length/error declaration')
                if ret['address'] not in outputs or ret['capacity'] not in scalars:
                    raise Refusal('Return buffer must refer to declared output/capacity')
                cap=next(a for a in arguments if a.get('name')==ret['capacity'])
                if cap['maximum']>2097152:raise Refusal('Output capacity bound exceeds owned buffer')
                if next(a for a in arguments if a.get('name')==ret['address'])['kind']!='output':
                    raise Refusal('Buffer return requires an output argument')
            elif ret['kind']=='allocated-buffer':
                if set(ret)-{'kind','signed','bits','pointerCell'}:
                    raise Refusal('Unsupported allocated return declaration fields')
                if ret['pointerCell'] not in outputs or not ret['signed']:
                    raise Refusal('Allocated return requires declared pointer cell and signed length')
                if next(a for a in arguments if a.get('name')==ret['pointerCell'])['kind']!='pointer-cell':
                    raise Refusal('Allocated return requires a pointer-cell argument')
            else:raise Refusal('Unsupported declared return kind')
            if type(ret.get('bits',64)) is not int or ret.get('bits',64)!=64:
                raise Refusal('Only 64-bit return values are supported')
        except (KeyError,TypeError) as e:
            raise Refusal('Malformed caller-declared ABI') from e
        data = (self.directory/'capsule.json').read_bytes()
        if hashlib.sha256(data).hexdigest() != self.manifest['capsuleSha256']:
            raise Refusal('Closed capsule identity mismatch')
        self.capsule = json.loads(data)
        self.capsule['externals'] = {int(a): n for a,n in self.capsule['externals'].items()}
        if self.capsule['entry'] != self.manifest['entry']:
            raise Refusal('Declared feature entry mismatch')
        if self.capsule.get('architecture') != 'AARCH64:LE:64:v8A':
            raise Refusal('Unsupported instruction architecture')

    def call(self, source, **parameters):
        if not isinstance(source, bytes) or len(source) > 2*1024*1024:
            raise Refusal('Source must be bytes within the 2 MiB input bound')
        abi = self.manifest['abi']
        allowed = {a['name']:a for a in abi['arguments'] if a['kind']=='scalar'}
        if set(parameters) != set(allowed):
            raise Refusal('Parameters must exactly match declared scalar arguments')
        for name,a in allowed.items():
            v=parameters[name]
            if type(v) is not int or not a['minimum'] <= v <= a['maximum']:
                raise Refusal('Scalar argument outside declared bound: '+name)
        try:vm=VM(self.capsule)
        except (RuntimeError,ValueError,KeyError,TypeError) as e:raise Refusal('Unsupported capsule state: '+str(e)) from e
        arguments=[]
        addresses={}
        writes=[(0x30000000, source)]
        for a in abi['arguments']:
            kind=a['kind']
            if kind=='input':
                value=0x30000000
            elif kind=='input-length':
                value=len(source)
            elif kind=='scalar':
                value=parameters[a['name']]
            elif kind in ('output','pointer-cell'):
                value=0x40000000
                if addresses:
                    raise Refusal('Only one owned output or pointer cell is supported')
                addresses[a['name']]=value
            else:
                raise Refusal('Unsupported declared argument kind: '+kind)
            arguments.append(value)
        try:
            unsigned=vm.invoke(arguments,writes)
            result=unsigned-(1<<64) if abi['return']['signed'] and unsigned>>63 else unsigned
            ret=abi['return']
            if result<0:
                output=b''
            elif ret['kind']=='buffer':
                capacity=parameters[ret['capacity']]
                output=vm.mem.read(addresses[ret['address']],result) if result<=capacity else b''
            elif ret['kind']=='allocated-buffer':
                if result>2*1024*1024:
                    raise Refusal('Allocated result exceeds output bound')
                pointer=int.from_bytes(vm.mem.read(addresses[ret['pointerCell']],8),'little')
                if pointer not in vm.allocations or result>vm.allocations[pointer]:
                    raise Refusal('Allocated result is outside declared heap ownership')
                output=vm.mem.read(pointer,result)
            else:
                raise Refusal('Unsupported declared return kind')
        except (RuntimeError,ValueError,KeyError) as e:
            raise Refusal(str(e)) from e
        return dict(returnValue=result,output=output,instructions=vm.stats['instructions'],
                    pcodeOps=vm.stats['pcode_ops'],externalCalls=vm.stats['external_calls'])
