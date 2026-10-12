"""Separate native oracle generation; never imported by closed execution."""
import argparse,ctypes,json,pathlib
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('target',type=pathlib.Path);p.add_argument('output',type=pathlib.Path)
a=p.parse_args();lib=ctypes.CDLL(str(a.target.resolve()))
fn=lib.utf8proc_map;fn.argtypes=[ctypes.c_void_p,ctypes.c_ssize_t,ctypes.POINTER(ctypes.c_void_p),ctypes.c_uint];fn.restype=ctypes.c_ssize_t
free=ctypes.CDLL(None).free;free.argtypes=[ctypes.c_void_p]
rows=[]
for label,data,options in [('ascii',b'Hello WORLD',1070),('casefold','Straße İΣK'.encode(),1070),
 ('composition','Amélie Cafe\u0301 가'.encode(),10),('decomposition','Ångström 각'.encode(),18),
 ('compatibility','① ﬁ Ａ㎏'.encode(),14),('marks','āéç א\u05b7'.encode(),18|8192),
 ('invalid',b'\xf0\x28\x8c\xbc',1070),('nul',b'ABC\0DEF',1070),('invalid-options',b'abc',24)]:
 ptr=ctypes.c_void_p();result=fn(data,len(data),ctypes.byref(ptr),options)
 try:output=ctypes.string_at(ptr,result) if result>=0 else None
 finally:
  if ptr.value:free(ptr)
 rows.append(dict(label=label,sourceHex=data.hex(),parameters={'options':options},nativeReturn=result,
                  expectedHex=None if output is None else output.hex()))
with a.output.open('x') as f:json.dump(rows,f)
print(json.dumps(dict(cases=len(rows))))
