"""Run or verify a frozen feature with an explicit, bounded calling contract."""
import argparse, hashlib, json, pathlib, sys

def audit(event,args):
    if event in ('ctypes.dlopen','ctypes.dlsym'):
        raise RuntimeError('Native loading forbidden during closed execution')
    if event=='import' and args[0] in ('ctypes','pypcode','capstone'):
        raise RuntimeError('Native/lifting dependencies forbidden during closed execution')
    if event=='open' and isinstance(args[0],str) and args[0].endswith(('.dylib','.so')):
        raise RuntimeError('Native target binary access forbidden during closed execution')

def main():
    sys.addaudithook(audit)
    from .api import Feature,Refusal
    p=argparse.ArgumentParser(description=__doc__)
    s=p.add_subparsers(dest='action',required=True)
    run=s.add_parser('run');run.add_argument('feature',type=pathlib.Path)
    run.add_argument('input',type=pathlib.Path);run.add_argument('output',type=pathlib.Path)
    run.add_argument('--param',action='append',default=[],metavar='NAME=INTEGER')
    verify=s.add_parser('verify');verify.add_argument('feature',type=pathlib.Path)
    verify.add_argument('cases',type=pathlib.Path)
    a=p.parse_args()
    try:
        f=Feature(a.feature)
        if a.action=='run':
            if a.output.exists():raise Refusal('Output path already exists')
            if a.input.stat().st_size>2097152:raise Refusal('Input byte bound exceeded')
            parameters={}
            for item in a.param:
                key,value=item.split('=',1)
                if key in parameters:raise Refusal('Duplicate scalar parameter')
                parameters[key]=int(value,0)
            result=f.call(a.input.read_bytes(),**parameters)
            ret=result['returnValue']
            if ret<0 or ret!=len(result['output']):
                raise Refusal('Native feature returned error '+str(ret))
            with a.output.open('xb') as stream:stream.write(result.pop('output'))
            print(json.dumps(result));return 0
        results=[]
        for row in json.loads(a.cases.read_text()):
            try:
                result=f.call(bytes.fromhex(row['sourceHex']),**row['parameters'])
                matched=result['returnValue']==row['nativeReturn'] and (row.get('expectedHex') is None or result['output'].hex()==row['expectedHex'])
                result.pop('output');result.update(label=row['label'],matched=matched)
            except Refusal as e:result=dict(label=row['label'],matched=False,refused=True,error=str(e))
            results.append(result);print(json.dumps(result),flush=True)
        summary=dict(completed=len(results),matched=sum(r['matched'] for r in results),
                     refused=sum(r.get('refused',False) for r in results))
        print(json.dumps(summary));return 0 if results and all(r['matched'] for r in results) else 1
    except (Refusal,ValueError,OSError) as e:
        print('Refused: '+str(e),file=sys.stderr);return 1

if __name__=='__main__':sys.exit(main())
