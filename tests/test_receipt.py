import json, pathlib, shutil, subprocess, sys, tempfile, unittest
from unittest.mock import patch
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from graftline.receipt import publish

class ReceiptTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.d=pathlib.Path(self.tmp.name)
  self.feature=self.d/'feature';shutil.copytree(ROOT/'features/utf8proc',self.feature)
  self.cases=self.d/'cases.json'; self.cases.write_text(json.dumps([{'label':'A','sourceHex':'41','parameters':{'options':1070},'nativeReturn':1,'expectedHex':'61'}]))
  self.receipt=self.d/'receipt.json'
 def call(self,*options):
  return subprocess.run([sys.executable,'-I','-S',str(ROOT/'run.py'),'verify',str(self.feature),str(self.cases),*map(str,options)],capture_output=True,text=True)
 def test_receipt_reruns_and_source_case_tamper_refuse(self):
  result=self.call('--receipt',self.receipt);self.assertEqual(result.returncode,0);self.assertIn('Receipt written:',result.stderr)
  saved=json.loads(self.receipt.read_text());self.assertTrue(saved['validation']['rerun']);self.assertEqual(saved['validation']['summary']['matched'],1)
  result=self.call('--check-receipt',self.receipt);self.assertEqual(result.returncode,0);self.assertIn('Receipt matches',result.stderr)
  self.cases.write_text(self.cases.read_text()+' ')
  self.assertEqual(self.call('--check-receipt',self.receipt).returncode,1)
  self.cases.write_text(self.cases.read_text().rstrip());p=self.feature/'feature.json';p.write_text(p.read_text()+' ')
  self.assertEqual(self.call('--check-receipt',self.receipt).returncode,1)
  p=self.feature/'capsule.json';p.write_bytes(p.read_bytes()+b' ')
  self.assertEqual(self.call('--check-receipt',self.receipt).returncode,1)
 def test_refusal_is_observed_not_pass(self):
  row=json.loads(self.cases.read_text())[0];row['parameters']={};self.cases.write_text(json.dumps([row]))
  p=self.call('--receipt',self.receipt);self.assertEqual(p.returncode,1)
  r=json.loads(self.receipt.read_text());self.assertEqual(r['validation']['summary']['refused'],1);self.assertFalse(r['validation']['cases'][0]['matched'])
 def test_collision_and_failed_link_preserve_previous_output(self):
  self.receipt.write_bytes(b'foreign')
  with self.assertRaises(FileExistsError):publish(self.receipt,{'a':1})
  self.assertEqual(self.receipt.read_bytes(),b'foreign')
  target=self.d/'new'
  with patch('graftline.receipt.os.link',side_effect=OSError('injected')):
   with self.assertRaises(OSError):publish(target,{'a':1})
  self.assertFalse(target.exists());self.assertFalse(list(self.d.glob('*.pending')))
  with patch('graftline.receipt.os.fsync',side_effect=OSError('injected write flush failure')):
   with self.assertRaises(OSError):publish(target,{'a':1})
  self.assertFalse(target.exists());self.assertFalse(list(self.d.glob('*.pending')))
  publish(target,{'a':1});self.assertEqual(json.loads(target.read_text()),{'a':1})

class ReceiptReviewRegression(ReceiptTests):
 def test_license_named_receipt_is_refused_without_creating_file(self):
  target=self.feature/'LICENSE-receipt.json'
  p=self.call('--receipt',target)
  self.assertEqual(p.returncode,1);self.assertIn('license identity',p.stderr);self.assertFalse(target.exists())
  self.assertEqual(self.call('--receipt',self.receipt).returncode,0)
  self.assertEqual(self.call('--check-receipt',self.receipt).returncode,0)
 def test_boolean_and_float_cannot_masquerade_as_integer_claims(self):
  self.assertEqual(self.call('--receipt',self.receipt).returncode,0)
  original=json.loads(self.receipt.read_text())
  for name,value in [('matched',True),('completed',1.0),('refused',False)]:
   data=json.loads(json.dumps(original));data['validation']['summary'][name]=value;self.receipt.write_text(json.dumps(data))
   self.assertEqual(self.call('--check-receipt',self.receipt).returncode,1,name)

if __name__=='__main__':
 unittest.main()
