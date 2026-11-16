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
    p=argparse.ArgumentParser(description='Run or compare a frozen feature using its declared ABI. Extraction is separate: see EXTRACTION.md; it loads an authorized ARM64 Mach-O library.')
    s=p.add_subparsers(dest='action',required=True)
    run=s.add_parser('run',help='Run a feature on bytes; create a new output file',description='Run the closed interpreter; existing output files are refused.');run.add_argument('feature',type=pathlib.Path,help='Directory with feature.json and capsule.json')
    run.add_argument('input',type=pathlib.Path,help='Input byte file');run.add_argument('output',type=pathlib.Path,help='New output byte file')
    run.add_argument('--param',action='append',default=[],metavar='NAME=INTEGER')
    verify=s.add_parser('verify',help='Rerun retained cases and compare their expected results',description='Exit 0 only when every nonempty case matches; mismatches, refusals and invalid input exit 1.');verify.add_argument('feature',type=pathlib.Path,help='Directory with feature.json and capsule.json')
    verify.add_argument('cases',type=pathlib.Path,help='JSON case list containing inputs and retained expectations')
    verify.add_argument('--receipt',type=pathlib.Path,help='Write a fresh current-validation receipt at a new path')
    verify.add_argument('--check-receipt',type=pathlib.Path,help='Rerun and compare against this saved receipt')
    a=p.parse_args()
    try:
        if a.action=='verify' and (a.receipt or a.check_receipt):
            if a.receipt and a.receipt.parent.resolve()==a.feature.resolve() and a.receipt.name.startswith('LICENSE'):
                raise Refusal('Receipt path would alter the specimen license identity')
            from .receipt import identity, make, publish, check
            observed=identity(a.feature)
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
        case_bytes=a.cases.read_bytes()
        results=[];receipt_results=[]
        for row in json.loads(case_bytes):
            try:
                result=f.call(bytes.fromhex(row['sourceHex']),**row['parameters'])
                matched=result['returnValue']==row['nativeReturn'] and (row.get('expectedHex') is None or result['output'].hex()==row['expectedHex'])
                output_hash=hashlib.sha256(result.pop('output')).hexdigest();result.update(label=row['label'],matched=matched)
            except Refusal as e:result=dict(label=row['label'],matched=False,refused=True,error=str(e));output_hash=None
            results.append(result);receipt_results.append({**result,'outputSha256':output_hash});print(json.dumps(result),flush=True)
        summary=dict(completed=len(results),matched=sum(r['matched'] for r in results),
                     refused=sum(r.get('refused',False) for r in results))
        print(json.dumps(summary))
        if a.receipt or a.check_receipt:
            if (identity(a.feature)!=observed or (a.feature/'feature.json').read_bytes()!=f.manifest_bytes
                    or (a.feature/'capsule.json').read_bytes()!=f.capsule_bytes or a.cases.read_bytes()!=case_bytes):
                raise Refusal('Inputs or engine sources changed during verification')
            receipt=make(f,case_bytes,receipt_results,summary,observed)
            if a.check_receipt:
                check(a.check_receipt,receipt)
                print('Receipt matches the current rerun; hashes are not authentication.',file=sys.stderr)
            if a.receipt:
                publish(a.receipt,receipt)
                print('Receipt written: '+str(a.receipt),file=sys.stderr)
        return 0 if results and all(r['matched'] for r in results) else 1
    except (Refusal,ValueError,OSError) as e:
        print('Refused: '+str(e),file=sys.stderr);return 1

if __name__=='__main__':sys.exit(main())
