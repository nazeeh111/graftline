# Graftline

Run a selected native feature without loading its original library. Graftline
freezes extracted instructions, tables and a declared memory environment into
a callable artifact. This can preserve a specific native implementation inside
offline tools, compatibility tests or legacy migrations.

The local research repository includes two real shipped features: a Zstandard
decoder and a Unicode text transform. Both execute through the same generic
interpreter and caller-declared argument convention. Python 3.10 or later and
its standard library are sufficient for the shipped artifacts. No package
installation, native decoder, target application, API key or service is needed.

From this directory, decode the genuine sample:

```sh
python3 -I -S run.py run features/zstd features/zstd/example.zst recovered.bin --param capacity=150000
```

It produces 139,363 bytes with SHA256
`9a644990a6ac1dc43c41bee4423e59744aebb81adbe55fe9b757e29999a40d99`.
Output files are created exclusively; existing output paths are refused.

Normalize compatibility characters and fold case:

```sh
python3 -I -S run.py run features/utf8proc features/utf8proc/example.txt normalized.txt --param options=1070
```

The supplied `Straße ﬁ Ａ Café` becomes `strasse fi a café`. Option value 1070
combines the native library's stable, compatibility, composition, ignore and
case-fold flags. Options are explicit integers, not inferred user intent.
The frozen transform is **utf8proc API 2.7.0 / Unicode 14.0.0**, even though the
installed library basename was `libutf8proc.2.5.0.dylib`. It is not current or
complete Unicode compatibility by assertion.

## Calling another extracted feature

`feature.json` binds an exact capsule SHA256 and entry address to a declared ABI,
the argument and return convention. Supported declarations are one input byte
buffer, input length, bounded unsigned scalars, and one owned output buffer or
allocated-output pointer cell. Arguments occupy x0–x7 and the return uses x0.
Exactly one input and one input length are required. Unknown ABI/argument/return fields, signed scalar declarations, unsupported widths and duplicate kinds refuse. Scalars use unsigned 64-bit register values; returns use unsigned 64-bit buffer lengths/errors or signed 64-bit allocated lengths/errors. Optional explicit width markers must be 64. Signatures are supplied by the caller, not inferred from machine code.

```python
from graftline import Feature
feature = Feature("features/utf8proc")
result = feature.call("Straße".encode(), options=1070)
assert result["output"] == b"strasse"
```

The API constructs fresh state for each call. `runtime.py` contains generic
integer instruction and memory semantics, not decoder or Unicode algorithms.
The capsules contain extracted programs and tables. The runner denies native
loading and lifting imports; it never falls back to the original library.

## Evidence and limits

| Frozen feature | Actual native source | Retained original code | Current comparisons |
| --- | --- | --- | --- |
| Zstandard decode | Python-distributed libzstd 1.5.7 ARM64 slice | 404/1,438 text symbol bodies; 268,428 text bytes (14.55%), plus 336 import bytes | 47/47 native return/output comparisons |
| Unicode mapping | MATLAB-distributed utf8proc API 2.7.0 ARM64 library | 9/31 text symbol bodies; 4,248 text bytes (69.19%), plus 36 import bytes | 16/16 cases generated after the first Unicode runtime/extractor freeze |

Original implementation source and decoder/normalization specifications were
withheld. Public ABI declarations and copyright notices were allowed. Native
libraries were loaded only during explicit extraction and separate oracle
generation, which creates comparison cases. They are absent from this repository.

The Zstandard corpus contains the original eleven and 36 independently
generated reviewer cases. Review exposed four checksum paths missing an import
trampoline, then guided refinement; this corpus is now regression evidence.
The Unicode discovery corpus first refused `realloc`; the bounded allocation
model was added before generating sixteen new cases. Later manifest-validation
changes did not change the successful transformation semantics. Retained case
bytes, native expectations, results, provenance and freeze identities live in
each feature directory. Results are finite observations, not complete correctness
or security claims.

Each call allows at most 2 MiB input/output, a 16 MiB heap arena, a 4 MiB stack,
2,000,000 interpreted instruction steps and 15 seconds. Unknown code, operations,
memory, environmental dependencies or invalid declarations refuse. Fortified
memory helpers enforce their destination object bound. Every heap read/write, including interpreted LOAD/STORE and modeled memory helpers, must lie inside one live allocation's requested extent. Reallocation copies the
owned prefix into fresh storage and revokes old access; freed bytes and allocation padding are inaccessible. A zero-size allocation admits only zero-byte access, and one-past pointers admit only zero-byte access. Zero-size realloc refuses without changing the live allocation. Allocation failure, thread scheduling, host I/O and physical CPU/cache
behavior are not reconstructed. The allocation ledger is not a proof of all
native memory safety.

Code selection and tables are conservative: all initialized non-code sections
are retained; unused paths and indirect targets remain unproved. The Zstandard
capsule is larger than its native machine code in uncompressed JSON. Extraction
depends on available ARM64 Mach-O symbols and captured relocations. It is not a
general arbitrary-binary system, minimal transplant, new decoder, new Unicode
algorithm or first-invention claim. New targets require an authorized artifact,
an explicit ABI/environment and fresh witnesses. See [EXTRACTION.md](EXTRACTION.md).

## Verify

```sh
python3 -I -S run.py verify features/zstd features/zstd/cases.json
python3 -I -S run.py verify features/utf8proc features/utf8proc/cases.json
python3 -I -S tests/test_boundaries.py
```

The verifier exits nonzero for a mismatch, refusal or empty corpus. Thirteen focused
boundary tests cover live heap bounds across guest/helper access, zero extents, ownership/reallocation, checked memory, repeated state,
identity/ABI validation, unknown paths/dependencies, verifier status and output
preservation, overlapping register values and direct/indirect control flow.
The included GitHub workflow runs these standard-library commands with a
five-minute job bound. See the [latest hosted CI status](https://github.com/nazeeh111/graftline/actions/workflows/verify.yml).
The first hosted run refused the longest Unicode witness at the 15-second
execution limit. The runtime update removes repeated buffer conversions and
operand classification; the limits, capsules and witnesses remain unchanged.

Project runtime/tools are MIT-licensed. Extracted Zstandard code/data remains
BSD-licensed; utf8proc code and Unicode data retain their included notices.
See [NOTICE.md](NOTICE.md). No upstream endorsement or name availability is claimed.

## Corrected local freeze

Independent review of the first local freeze found that allocation bookkeeping
did not protect mapped heap bytes and ABI validation accepted ignored width/sign
fields or repeated inputs. Both were corrected before delivery: memory access
now enforces live object extents and declarations accept only the supported
structure. Frozen-v1 source/archive and review counterexamples remain preserved
in task-local evidence. The two retained native corpora pass with the corrected
model; they are regression observations, not a new blind discovery count.
