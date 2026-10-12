"""Freeze a caller-selected owned/permissively licensed ARM64 library image.

This extraction operation loads the exact native library. Closed execution does
not. Loading arbitrary libraries is not a sandbox or a safe inspection operation.
"""
import argparse, base64, ctypes, hashlib, json, pathlib, re
from macho import macho

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('target', type=pathlib.Path)
p.add_argument('destination', type=pathlib.Path)
p.add_argument('--entry', required=True)
p.add_argument('--expected-sha256', required=True)
p.add_argument('--version', required=True, help='Caller-provided observed native version')
args = p.parse_args()
raw = args.target.read_bytes()
digest = hashlib.sha256(raw).hexdigest()
if digest != args.expected_sha256:
    raise SystemExit('Target SHA256 mismatch')
if not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*', args.entry):
    raise SystemExit('Entry must be a native symbol identifier')
thin, segments, sections, symbols = macho(raw)
if '_' + args.entry not in symbols:
    raise SystemExit('Entry symbol is absent')
args.destination.mkdir()
frozen = args.destination / 'target-arm64.dylib'
frozen.write_bytes(thin)
lib = ctypes.CDLL(str(frozen.resolve()))
entry = ctypes.cast(getattr(lib, args.entry), ctypes.c_void_p).value
slide = entry - symbols['_' + args.entry]
libc = ctypes.CDLL(None)
externals = {}
for name in ('malloc', 'calloc', 'realloc', 'free', 'memcpy', 'memmove',
             'memset', 'bzero', '__memcpy_chk', '__memmove_chk', '__memset_chk',
             '__chkstk_darwin', '__stack_chk_fail'):
    try:
        externals[ctypes.cast(getattr(libc, name), ctypes.c_void_p).value] = name
    except AttributeError:
        pass
regions = []
for s in segments:
    if s['name'] == '__LINKEDIT' or not s['size']:
        continue
    if s['size'] > 8 * 1024 * 1024:
        raise RuntimeError('Snapshot segment budget exceeded')
    data = ctypes.string_at(slide + s['va'], s['size'])
    regions.append(dict(address=slide+s['va'], name=s['name'],
                        writable=bool(s['prot'] & 2), bytes=base64.b64encode(data).decode()))
canary = ctypes.c_uint64.in_dll(libc, '__stack_chk_guard')
regions.append(dict(address=ctypes.addressof(canary), name='explicit-stack-guard',
                    writable=False, bytes=base64.b64encode(bytes(canary)).decode()))
capsule = dict(version=1, entry=entry, architecture='AARCH64:LE:64:v8A', regions=regions,
               externals=externals, target=dict(original=str(args.target.resolve()),
               originalSha256=digest, thinSha256=hashlib.sha256(thin).hexdigest(),
               version=args.version, entrySymbol=args.entry, bytes=len(thin)),
               limitations=['native-loaded relocations become virtual numeric addresses',
                            'closed extraction not yet performed; original source withheld'])
(args.destination/'snapshot.json').write_text(json.dumps(capsule))
print(json.dumps(dict(entry=args.entry, originalSha256=digest, thinSha256=capsule['target']['thinSha256'])))
