import base64, struct, time

# Fixed-width unpack/pack operates directly on the shared byte buffers. It
# preserves overlapping register/temporary aliases without allocating a slice
# and intermediate bytes for every interpreted value.
_INTEGERS = {size: (struct.Struct(format), (1 << (size * 8)) - 1)
             for size, format in ((1, '<B'), (2, '<H'), (4, '<I'), (8, '<Q'))}

class Memory:

    def __init__(self):
        self.regions = []
        self.reads = []
        self.heap_allocations = {}

    def map(self, address, data, name, writable=True):
        data = bytearray(data)
        if any((address < a + len(d) and a < address + len(data) for a, d, _, _ in self.regions)):
            raise ValueError('Overlapping regions')
        self.regions.append((address, data, name, writable))

    def access(self, address, size, write=False):
        if type(address) is not int or type(size) is not int or address < 0 or size < 0:
            raise RuntimeError('Invalid memory address or extent')
        for a, d, n, w in self.regions:
            if a <= address and address + size <= a + len(d):
                if n == 'heap' and not any(
                    base <= address and address + size <= base + extent
                    for base, extent in self.heap_allocations.items()
                ):
                    raise RuntimeError(f'Access outside a live heap allocation: {address:x}+{size}')
                if write and (not w):
                    raise RuntimeError(f'write to immutable {n}: {address:x}')
                return (d, address - a)
        raise RuntimeError(f"unmapped {('write' if write else 'read')} {address:x}+{size}")

    def read(self, address, size, trace=True):
        d, o = self.access(address, size)
        if trace:
            self.reads.append((address, address + size))
        return bytes(d[o:o + size])

    def write(self, address, data):
        d, o = self.access(address, len(data), True)
        d[o:o + len(data)] = data

class VM:

    def __init__(self, capsule):
        self.capsule = capsule
        if 'ops' in capsule:
            self.names = capsule['registers']
        else:
            raise RuntimeError('This portable runtime requires frozen IR; native lifting is unavailable')
        self.mem = Memory()
        for r in capsule['regions']:
            self.mem.map(r['address'], base64.b64decode(r['bytes']), r['name'], r['writable'])
        self.mem.map(268435456, bytes(4 * 1024 * 1024), 'stack')
        self.mem.map(536870912, bytes(16 * 1024 * 1024), 'heap')
        self.mem.map(805306368, bytes(2 * 1024 * 1024), 'input')
        self.mem.map(1073741824, bytes(2 * 1024 * 1024), 'output')
        self.spaces = {'register': bytearray(65536), 'unique': bytearray(16 * 1024 * 1024)}
        self.heap = 536870912
        self.allocations = {}
        self.mem.heap_allocations = self.allocations
        self.ops = {int(a): o for a, o in capsule.get('ops', {}).items()}
        self.userops = {int(a): o for a, o in capsule.get('userops', {}).items()}
        self.stats = dict(instructions=0, pcode_ops=0, external_calls={}, executed_addresses=set(), opcodes=set())
        self.pc = capsule['entry']
        self.stop = 1342177280
        self.started = False

    def read(self, n):
        space, off, size = n
        if space == 'const':
            return off & (1 << size * 8) - 1
        if space == 'ram':
            return int.from_bytes(self.mem.read(off, size), 'little')
        d = self.spaces[space]
        if off < 0 or size < 0 or off + size > len(d):
            raise RuntimeError('P-code temporary budget exceeded')
        integer = _INTEGERS.get(size)
        if integer is not None:
            return integer[0].unpack_from(d, off)[0]
        return int.from_bytes(d[off:off + size], 'little')

    def write(self, n, value):
        space, off, size = n
        if space == 'ram':
            data = (value & (1 << size * 8) - 1).to_bytes(size, 'little')
            self.mem.write(off, data)
        else:
            d = self.spaces[space]
            if off < 0 or size < 0 or off + size > len(d):
                raise RuntimeError('P-code temporary budget exceeded')
            integer = _INTEGERS.get(size)
            if integer is not None:
                integer[0].pack_into(d, off, value & integer[1])
            else:
                d[off:off + size] = (value & (1 << size * 8) - 1).to_bytes(size, 'little')

    def reg(self, name, value=None):
        n = self.names[name]
        if value is not None:
            self.write(n, value)
        return self.read(n)

    @staticmethod
    def signed(value, size):
        sign = 1 << size * 8 - 1
        return value - (sign << 1) if value & sign else value

    def external(self, name):
        stat = self.stats['external_calls']
        stat[name] = stat.get(name, 0) + 1
        a, b, c = [self.reg(f'x{i}') for i in range(3)]
        if name in ('__memcpy_chk', '__memmove_chk', '__memset_chk') and c > self.reg('x3'):
            raise RuntimeError('Fortified memory object bound exceeded')
        if name in ('malloc', 'calloc'):
            size = a * b if name == 'calloc' else a
            if size > 8 * 1024 * 1024 or self.heap + size > 553648128:
                raise RuntimeError('Heap allocation budget exceeded')
            address = self.heap
            self.heap += max(size, 1) + 15 & ~15
            self.allocations[address] = size
            self.reg('x0', address)
        elif name == 'realloc':
            if b == 0:
                raise RuntimeError('Zero-size realloc semantics are unsupported')
            if a != 0 and a not in self.allocations:
                raise RuntimeError('Realloc requires a live owned allocation')
            if b > 8 * 1024 * 1024 or self.heap + b > 553648128:
                raise RuntimeError('Heap allocation budget exceeded')
            address = self.heap
            self.heap += b + 15 & ~15
            self.allocations[address] = b
            if a:
                self.mem.write(address, self.mem.read(a, min(self.allocations[a], b)))
                del self.allocations[a]
            self.reg('x0', address)
        elif name == 'free':
            if a:
                if a not in self.allocations:
                    raise RuntimeError('Free requires a live owned allocation')
                del self.allocations[a]
        elif name in ('memcpy', 'memmove', '__memcpy_chk', '__memmove_chk'):
            if c > 2 * 1024 * 1024:
                raise RuntimeError('copy budget exceeded')
            self.mem.write(a, self.mem.read(b, c))
        elif name in ('memset', '__memset_chk'):
            if c > 2 * 1024 * 1024:
                raise RuntimeError('fill budget exceeded')
            self.mem.write(a, bytes([b & 255]) * c)
        elif name == 'bzero':
            if b > 2 * 1024 * 1024:
                raise RuntimeError('fill budget exceeded')
            self.mem.write(a, bytes(b))
        elif name == '__chkstk_darwin':
            if self.reg('x16') > 4 * 1024 * 1024:
                raise RuntimeError('stack probe budget exceeded')
        else:
            raise RuntimeError(f'Unsupported environmental dependency: {name}')
        self.pc = self.reg('x30')

    def instruction(self):
        if self.pc in self.capsule['externals']:
            self.external(self.capsule['externals'][self.pc])
            return
        if self.pc not in self.ops:
            raise RuntimeError(f'Undiscovered native branch: {self.pc:x}')
        ops = self.ops[self.pc]
        self.stats['executed_addresses'].add(self.pc)
        self.stats['instructions'] += 1
        nextpc, i = (self.pc + 4, 0)
        read = self.read
        while i < len(ops):
            op, out, ins = ops[i]
            self.stats['opcodes'].add(op)
            self.stats['pcode_ops'] += 1
            if op in ('LOAD', 'STORE'):
                vals = []
            elif op in ('BRANCH', 'CBRANCH', 'CALL') and ins[0][0] == 'ram':
                # Only a direct control-flow target denotes its address rather
                # than a memory value. Classify once per operation, not again
                # for every ordinary arithmetic operand.
                vals = [ins[0][1]] + [read(n) for n in ins[1:]]
            else:
                vals = [read(n) for n in ins]
            value = None
            if op == 'COPY':
                value = vals[0]
            elif op == 'LOAD':
                value = int.from_bytes(self.mem.read(self.read(ins[1]), out[2]), 'little')
            elif op == 'STORE':
                self.mem.write(self.read(ins[1]), self.read(ins[2]).to_bytes(ins[2][2], 'little'))
            elif op == 'INT_ADD':
                value = vals[0] + vals[1]
            elif op == 'INT_SUB':
                value = vals[0] - vals[1]
            elif op == 'INT_MULT':
                value = vals[0] * vals[1]
            elif op in ('INT_DIV', 'INT_REM'):
                if not vals[1]:
                    raise RuntimeError('Unmodeled division by zero')
                value = vals[0] // vals[1] if op == 'INT_DIV' else vals[0] % vals[1]
            elif op == 'INT_AND':
                value = vals[0] & vals[1]
            elif op == 'INT_OR':
                value = vals[0] | vals[1]
            elif op == 'INT_XOR':
                value = vals[0] ^ vals[1]
            elif op == 'INT_NEGATE':
                value = ~vals[0]
            elif op == 'INT_2COMP':
                value = -vals[0]
            elif op == 'INT_LEFT':
                value = vals[0] << vals[1] if vals[1] < out[2] * 8 else 0
            elif op == 'INT_RIGHT':
                value = vals[0] >> vals[1]
            elif op == 'INT_SRIGHT':
                value = self.signed(vals[0], ins[0][2]) >> vals[1]
            elif op == 'INT_ZEXT':
                value = vals[0]
            elif op == 'INT_SEXT':
                value = self.signed(vals[0], ins[0][2])
            elif op == 'INT_EQUAL':
                value = vals[0] == vals[1]
            elif op == 'INT_NOTEQUAL':
                value = vals[0] != vals[1]
            elif op == 'INT_LESS':
                value = vals[0] < vals[1]
            elif op == 'INT_LESSEQUAL':
                value = vals[0] <= vals[1]
            elif op == 'INT_SLESS':
                value = self.signed(vals[0], ins[0][2]) < self.signed(vals[1], ins[1][2])
            elif op == 'INT_SLESSEQUAL':
                value = self.signed(vals[0], ins[0][2]) <= self.signed(vals[1], ins[1][2])
            elif op == 'INT_CARRY':
                value = vals[0] + vals[1] >= 1 << ins[0][2] * 8
            elif op in ('INT_SCARRY', 'INT_SBORROW'):
                a, b = (self.signed(vals[0], ins[0][2]), self.signed(vals[1], ins[1][2]))
                r = a + b if op == 'INT_SCARRY' else a - b
                limit = 1 << ins[0][2] * 8 - 1
                value = not -limit <= r < limit
            elif op == 'BOOL_NEGATE':
                value = not vals[0]
            elif op == 'BOOL_AND':
                value = bool(vals[0] and vals[1])
            elif op == 'BOOL_OR':
                value = bool(vals[0] or vals[1])
            elif op == 'BOOL_XOR':
                value = bool(vals[0]) != bool(vals[1])
            elif op == 'PIECE':
                value = vals[0] << ins[1][2] * 8 | vals[1]
            elif op == 'SUBPIECE':
                value = vals[0] >> vals[1] * 8
            elif op == 'POPCOUNT':
                value = vals[0].bit_count()
            elif op == 'LZCOUNT':
                value = ins[0][2] * 8 - vals[0].bit_length()
            elif op == 'CALLOTHER' and self.userops.get(ins[0][1]) == 'Hint_Prefetch':
                pass
            elif op in ('BRANCH', 'CBRANCH', 'BRANCHIND', 'CALL', 'CALLIND', 'RETURN'):
                take = op != 'CBRANCH' or vals[1] != 0
                if take:
                    if ins[0][0] == 'const' and op in ('BRANCH', 'CBRANCH'):
                        i += self.signed(vals[0], ins[0][2])
                        continue
                    nextpc = vals[0]
                    break
            else:
                raise RuntimeError(f'Unsupported p-code {op} at {self.pc:x}: {ops[i]}')
            if value is not None:
                self.write(out, value)
            i += 1
        self.pc = nextpc

    def invoke(self, arguments, writes, max_instructions=2000000, max_seconds=15):
        if self.started:
            raise RuntimeError('VM instances are single-use; create a fresh VM for each call')
        if len(arguments) > 8 or any((not isinstance(v, int) or not 0 <= v < 1 << 64 for v in arguments)):
            raise ValueError('ABI requires up to eight unsigned 64-bit register values')
        self.started = True
        for address, data in writes:
            self.mem.write(address, data)
        for i, v in enumerate(arguments):
            self.reg(f'x{i}', v)
        self.reg('sp', 272629760 - 16)
        self.reg('x30', self.stop)
        started = time.monotonic()
        while self.pc != self.stop:
            if self.stats['instructions'] >= max_instructions:
                raise RuntimeError('instruction budget exceeded')
            if self.stats['instructions'] % 1024 == 0 and time.monotonic() - started > max_seconds:
                raise RuntimeError('time budget exceeded')
            self.instruction()
        return self.reg('x0')
