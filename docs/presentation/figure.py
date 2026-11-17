"""Source-bound ABI and virtual-memory explanation, not a product screenshot.
Address rows are schematic; box area does not encode region or output byte count.
"""
from pathlib import Path
import json,html
P=Path(__file__).resolve().parent;d=json.loads((P/'journey.json').read_text());z=d['zstd'];u=d['unicode'];assert z['inputBytes']==336 and z['outputBytes']==139363 and u['outputBytes']==18

def draw(mobile):
 W,H=(420,1440) if mobile else (1200,890);m=28 if mobile else 44;s=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-labelledby="title desc">','<title id="title">Graftline: a native feature without its original library</title>','<desc id="desc">Actual isolated execution expands a 336-byte Zstandard input to 139,363 matching bytes using an explicit four-register ABI and generic interpreter. A second frozen Unicode feature produces 18 bytes through the same interpreter. Virtual memory regions are schematic, not drawn to byte scale.</desc>','<style>text{font-family:Arial,Helvetica,sans-serif;fill:#242228}.muted{fill:#55545e}.accent{fill:#733f63}.mono{font-family:"Courier New",Courier,monospace}</style>',f'<rect width="{W}" height="{H}" fill="#f2f1f3"/>']
 def t(x,y,v,size=20,cls='',weight=400):s.append(f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" class="{cls}">{html.escape(v)}</text>')
 t(m,48,'graftline',30,weight=700)
 if mobile:t(m,105,'Keep the feature.',36,weight=700);t(m,148,'Leave the library.',36,weight=700)
 else:t(m,118,'Keep the feature. Leave the library.',50,weight=700)
 t(m,190 if mobile else 166,'Actual closed execution; declared ABI.',18,'muted')
 t(m,245 if mobile else 228,'Zstandard 1.5.7 decoder',26,'accent',700)
 t(m,282 if mobile else 266,'336 input bytes → 139,363 output bytes',19,weight=700)
 if mobile:
  y=333
  for line in ['x0  output = 0x40000000','x1  capacity = 150000','x2  input = 0x30000000','x3  input length = 336']:t(m,y,line,18,'mono');y+=35
  t(m,505,'Return x0 = 139363',22,'accent',700);t(m,547,'Output SHA256',16,'muted');t(m,576,z['outputSHA256'][:32],15,'mono');t(m,601,z['outputSHA256'][32:],15,'mono')
 else:
  for i,line in enumerate(['x0  output = 0x40000000','x1  capacity = 150000','x2  input = 0x30000000','x3  input length = 336']):t(m,320+i*38,line,21,'mono')
  t(m,502,'Return x0 = 139363',25,'accent',700);t(m,543,'Output SHA256',17,'muted');t(m,574,z['outputSHA256'][:32],18,'mono');t(m,603,z['outputSHA256'][32:],18,'mono')
 x=m if mobile else 650;y=665 if mobile else 228
 t(x,y,'Owned virtual regions',26,weight=700)
 rows=[('0x10000000','4 MiB stack'),('0x20000000','16 MiB heap arena'),('0x30000000','2 MiB input region'),('0x40000000','2 MiB output region')]
 for i,(address,label) in enumerate(rows):t(x,y+51+i*60,address,19,'mono');t(x+155 if not mobile else x,y+51+i*60+(23 if mobile else 0),label,17,'muted')
 t(x,y+299 if mobile else y+273,'Region map is schematic, not to scale.',15,'muted')
 if not mobile:t(x,y+308,'150000 is the caller-supplied capacity.',16,'muted');t(x,y+337,'Signature is supplied, not inferred.',16,'muted')
 y=1035 if mobile else 691
 t(m,y,'Same interpreter.' if mobile else 'Same interpreter. Another feature.',25,weight=700)
 if mobile:t(m,y+34,'Another feature.',25,weight=700)
 t(m,y+(73 if mobile else 39),'utf8proc API 2.7.0 / Unicode 14.0.0',18,'accent',700)
 t(m,y+(109 if mobile else 79),'options 1070; 22 → 18 bytes' if mobile else 'options = 1070; 22 input → 18 output bytes',16,'mono')
 t(m,y+(153 if mobile else 117),'strasse fi a café',27,'mono')
 if mobile:t(m,1252,'Retained cases: 47 Zstd / 16 Unicode.',16,'muted');t(m,1293,'Finite comparisons, not complete correctness.',16,'muted');t(m,1340,'Frozen code and tables; original libraries absent.',16,'muted');t(m,1380,'Original licenses and modified-export notice kept.',16,'muted')
 else:t(650,y+39,'Original libraries absent from execution.',20,'muted');t(650,y+79,'47 Zstd and 16 Unicode retained cases match.',18,'muted');t(650,y+117,'Finite evidence; source notices remain explicit.',18,'muted')
 s.append('</svg>');return'\n'.join(s)+'\n'
for n,m in [('declared-feature',False),('declared-feature-mobile',True)]:(P/(n+'.svg')).write_text(draw(m))
