import struct

def macho(data):
    if data[:4] == bytes.fromhex('cafebabe'):
        count = struct.unpack_from('>I', data, 4)[0]
        choices = [struct.unpack_from('>IIIII', data, 8 + i * 20) for i in range(count)]
        arm = next((x for x in choices if x[0] == 16777228))
        data = data[arm[2]:arm[2] + arm[3]]
    if struct.unpack_from('<I', data)[0] != 4277009103:
        raise ValueError('Expected little-endian 64-bit Mach-O')
    if struct.unpack_from('<I', data, 4)[0] != 0x100000c or struct.unpack_from('<I', data, 12)[0] != 6:
        raise ValueError('Only ARM64 Mach-O dynamic libraries are supported')
    ncmds = struct.unpack_from('<I', data, 16)[0]
    off, segments, sections, sym = (32, [], [], None)
    for _ in range(ncmds):
        cmd, size = struct.unpack_from('<II', data, off)
        if cmd == 25:
            name, va, vs, fo, fs, _, prot, ns, _ = struct.unpack_from('<16sQQQQIIII', data, off + 8)
            segments.append(dict(name=name.rstrip(b'\x00').decode(), va=va, size=vs, fileoff=fo, filesize=fs, prot=prot))
            for i in range(ns):
                a = off + 72 + i * 80
                sn, sg, sa, ss, sf = struct.unpack_from('<16s16sQQI', data, a)
                sections.append(dict(name=sn.rstrip(b'\x00').decode(), segment=sg.rstrip(b'\x00').decode(), va=sa, size=ss, fileoff=sf))
        elif cmd == 2:
            sym = struct.unpack_from('<IIII', data, off + 8)
        off += size
    symbols = {}
    if sym:
        so, nc, st, _ = sym
        for i in range(nc):
            ni, typ, sect, desc, val = struct.unpack_from('<IBBHQ', data, so + i * 16)
            name = data[st + ni:data.index(b'\x00', st + ni)].decode(errors='replace')
            if val and typ & 14 == 14:
                symbols[name] = val
    return (data, segments, sections, symbols)
