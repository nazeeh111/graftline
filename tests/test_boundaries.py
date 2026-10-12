import copy,hashlib,json,pathlib,subprocess,sys,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from graftline import Feature,Refusal
from graftline.runtime import VM

class Boundaries(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.feature=Feature(ROOT/'features/utf8proc')

    def external(self,vm,name,args):
        for i,v in enumerate(args):vm.reg('x'+str(i),v)
        vm.reg('x30',vm.stop);vm.external(name);return vm.reg('x0')

    def test_realloc_preserves_prefix_and_ownership(self):
        v=VM(self.feature.capsule);old=self.external(v,'malloc',[8,0,0])
        v.mem.write(old,b'abcdefgh');new=self.external(v,'realloc',[old,12,0])
        self.assertEqual(v.mem.read(new,8),b'abcdefgh');self.assertNotIn(old,v.allocations)
        smaller=self.external(v,'realloc',[new,4,0])
        self.assertEqual(v.mem.read(smaller,4),b'abcd');self.assertEqual(v.allocations[smaller],4)
        with self.assertRaisesRegex(RuntimeError,'live owned'):self.external(v,'realloc',[new,8,0])

    def test_allocation_refusals(self):
        for name,args,why in [('realloc',[0,0,0],'Zero-size'),('realloc',[123,8,0],'live owned'),
          ('free',[123,0,0],'live owned'),('calloc',[1<<63,8,0],'budget')]:
            with self.subTest(name=name,args=args):
                v=VM(self.feature.capsule)
                with self.assertRaisesRegex(RuntimeError,why):self.external(v,name,args)

    def test_heap_lifetime_and_extent_on_all_access_paths(self):
        v=VM(self.feature.capsule);old=self.external(v,'malloc',[8,0,0])
        v.mem.write(old,b'ABCDEFGH');new=self.external(v,'realloc',[old,12,0])
        smaller=self.external(v,'realloc',[new,4,0])
        for pointer in (old,new):
            with self.assertRaisesRegex(RuntimeError,'live heap allocation'):v.mem.read(pointer,1)
            with self.assertRaisesRegex(RuntimeError,'live heap allocation'):v.mem.write(pointer,b'X')
            with self.assertRaisesRegex(RuntimeError,'live heap allocation'):self.external(v,'memcpy',[0x40000000,pointer,8])
        self.assertEqual(v.mem.read(0x40000000,8),bytes(8))
        with self.assertRaisesRegex(RuntimeError,'live heap allocation'):self.external(v,'memset',[smaller,90,8])
        self.assertEqual(v.mem.read(smaller,4),b'ABCD')
        with self.assertRaisesRegex(RuntimeError,'live heap allocation'):v.mem.read(smaller+3,2)
        # Guest LOAD/STORE use the same access gate, not only external helpers.
        v.reg('x1',old);v.ops[v.pc]=[('LOAD',['register',0,1],[['const',0,8],v.names['x1']])]
        with self.assertRaisesRegex(RuntimeError,'live heap allocation'):v.instruction()
        v.reg('x1',smaller);v.ops[v.pc]=[('STORE',None,[['const',0,8],v.names['x1'],['const',0x5858585858585858,8]])]
        with self.assertRaisesRegex(RuntimeError,'live heap allocation'):v.instruction()
        self.assertEqual(v.mem.read(smaller,4),b'ABCD')
        self.external(v,'free',[smaller,0,0])
        with self.assertRaisesRegex(RuntimeError,'live heap allocation'):v.mem.read(smaller,4)

    def test_zero_extent_and_one_past_semantics(self):
        v=VM(self.feature.capsule);zero=self.external(v,'malloc',[0,0,0])
        self.assertEqual(v.mem.read(zero,0),b'');v.mem.write(zero,b'')
        with self.assertRaisesRegex(RuntimeError,'live heap allocation'):v.mem.read(zero,1)
        self.external(v,'free',[zero,0,0])
        with self.assertRaisesRegex(RuntimeError,'live heap allocation'):v.mem.read(zero,0)
        p=self.external(v,'malloc',[4,0,0]);self.assertEqual(v.mem.read(p+4,0),b'')
        with self.assertRaisesRegex(RuntimeError,'live heap allocation'):v.mem.read(p+4,1)
        with self.assertRaisesRegex(RuntimeError,'Zero-size'):self.external(v,'realloc',[p,0,0])
        self.assertIn(p,v.allocations)

    def test_checked_memory_refuses_before_write(self):
        for name in ('__memcpy_chk','__memmove_chk','__memset_chk'):
            v=VM(self.feature.capsule);v.mem.write(0x30000000,b'ABCDEFGH')
            source=65 if 'set' in name else 0x30000000
            with self.assertRaisesRegex(RuntimeError,'object bound'):self.external(v,name,[0x40000000,source,8,4])
            self.assertEqual(v.mem.read(0x40000000,8),bytes(8))
            self.external(v,name,[0x40000000,source,4,4])
            self.assertEqual(v.mem.read(0x40000000,4),b'AAAA' if 'set' in name else b'ABCD')

    def test_single_use(self):
        v=VM(self.feature.capsule);v.invoke([0x30000000,1,0x40000000,1070],[(0x30000000,b'X')])
        count=v.stats['instructions']
        with self.assertRaisesRegex(RuntimeError,'single-use'):v.invoke([0,0,0,0],[])
        self.assertEqual(v.stats['instructions'],count)

    def test_parameter_boundaries(self):
        for parameters in ({},{'options':True},{'options':-1},{'options':32768},{'options':1070,'extra':0}):
            with self.subTest(parameters=parameters):
                with self.assertRaises(Refusal):self.feature.call(b'ABC',**parameters)
        with self.assertRaises(Refusal):self.feature.call(b'x'*2097153,options=1070)

    def test_unknown_dependency_and_branch(self):
        v=VM(self.feature.capsule)
        with self.assertRaisesRegex(RuntimeError,'dependency'):v.external('network_magic')
        v.ops.pop(v.pc)
        with self.assertRaisesRegex(RuntimeError,'Undiscovered'):v.instruction()

    def test_manifest_identity_and_abi(self):
        original=self.feature.manifest
        with tempfile.TemporaryDirectory() as directory:
            d=pathlib.Path(directory)
            (d/'capsule.json').write_bytes((self.feature.directory/'capsule.json').read_bytes())
            for mode in ('bad-hash','unknown-kind','missing-return','wrong-cell-kind',
              'return-width32','signed-scalar','scalar-width32','duplicate-input','missing-input',
              'duplicate-length','abi-extra','argument-extra','return-extra'):
                m=copy.deepcopy(original)
                if mode=='bad-hash':m['capsuleSha256']='0'*64
                elif mode=='unknown-kind':m['abi']['arguments'][0]['kind']='execute-python'
                elif mode=='missing-return':del m['abi']['return']
                elif mode=='wrong-cell-kind':m['abi']['arguments'][2]['kind']='output'
                elif mode=='return-width32':m['abi']['return']['bits']=32
                elif mode=='signed-scalar':m['abi']['arguments'][3]['signed']=True
                elif mode=='scalar-width32':m['abi']['arguments'][3]['bits']=32
                elif mode=='duplicate-input':m['abi']['arguments'].append({'kind':'input'})
                elif mode=='missing-input':m['abi']['arguments'][0]={'kind':'input-length'}
                elif mode=='duplicate-length':m['abi']['arguments'].append({'kind':'input-length'})
                elif mode=='abi-extra':m['abi']['unknown']=True
                elif mode=='argument-extra':m['abi']['arguments'][0]['unknown']=True
                else:m['abi']['return']['unknown']=True
                (d/'feature.json').write_text(json.dumps(m))
                with self.subTest(mode=mode):
                    with self.assertRaises(Refusal):Feature(d)
            m=copy.deepcopy(original);m['abi']['return']['bits']=64
            m['abi']['arguments'][3].update(bits=64,signed=False)
            (d/'feature.json').write_text(json.dumps(m))
            self.assertEqual(Feature(d).call(b'ABC',options=1070)['output'],b'abc')

    def test_verifier_mismatch_nonzero(self):
        row=dict(label='wrong-oracle',sourceHex='41',parameters={'options':1070},nativeReturn=999,expectedHex='61')
        with tempfile.TemporaryDirectory() as directory:
            p=pathlib.Path(directory)/'cases.json';p.write_text(json.dumps([row]))
            result=subprocess.run([sys.executable,'-I','-S',str(ROOT/'run.py'),'verify',str(self.feature.directory),str(p)],capture_output=True,text=True)
            self.assertEqual(result.returncode,1);self.assertIn('"matched": false',result.stdout)

    def test_cli_preserves_existing_output(self):
        with tempfile.TemporaryDirectory() as directory:
            d=pathlib.Path(directory);(d/'input').write_bytes(b'ABC');(d/'output').write_bytes(b'KEEP')
            result=subprocess.run([sys.executable,'-I','-S',str(ROOT/'run.py'),'run',str(self.feature.directory),str(d/'input'),str(d/'output'),'--param','options=1070'],capture_output=True,text=True)
            self.assertEqual(result.returncode,1);self.assertEqual((d/'output').read_bytes(),b'KEEP')

if __name__=='__main__':unittest.main()
