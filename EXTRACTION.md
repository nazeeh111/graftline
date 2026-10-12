# Extract and bind a feature

Closed execution and extraction have different boundaries. The shipped runner
uses only Python's standard library. Extraction explicitly **loads the selected
native library** to capture its own image's resolved relocations. Separate
oracle scripts call native functions to produce expectations. Neither operation
is a sandbox for an untrusted artifact. Use an owned or permissively licensed
library whose loading and redistribution are authorized, with exact input hash.

This recipe supports symbol-bearing ARM64 Mach-O dynamic libraries, including
the 32-bit fat-container layout used by the first target. It does not support
stripped arbitrary executables, arbitrary CPU architectures, callbacks, host I/O
or unknown environment semantics. Implementation source and algorithm/format
specifications are withheld; public ABI documentation and licensing are allowed.

## Free extraction dependency

Use an isolated environment with pinned `pypcode==4.0.1`. It is a free external
lifting dependency, not required by the exported runtime. No paid engine is used.
The implementation was tested with the task's existing isolated environment;
the following ordinary installation recipe needs network permission if the
package is not already available:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install pypcode==4.0.1
```

The authored parser reads image sections and native symbol boundaries. The
closure pass lifts selected symbol bodies, follows direct targets and
conservatively includes formed code-address candidates. It retains the complete
small import-trampoline section and all initialized non-code sections. A
100,000-instruction / 30-second extraction budget fails without exporting a
partial capsule. Unknown indirect targets remain unproved. Finishing this
bounded pass means the algorithm finished, not that all dependencies were found.

## Shipped Unicode example

The exact inspected target was:

```
/Applications/MATLAB_R2026a.app/bin/maca64/libutf8proc.2.5.0.dylib
SHA256 94943e7f1e22d774aded2038d8cf56cbe313893a1b6e36c918c8070c65b7c0e1
Native API 2.7.0, Unicode tables 14.0.0
```

Only this third-party open-source library was used; the MATLAB application was
not launched. Its shipped `utf8proc.rights` exactly matched the included upstream
notice. Both MIT and Unicode notices must travel with extracted code/tables.

From the repository root, select a new destination and caller-declared ABI:

```sh
python3 tools/snapshot.py /Applications/MATLAB_R2026a.app/bin/maca64/libutf8proc.2.5.0.dylib /tmp/unicode-graft-new --entry utf8proc_map --expected-sha256 94943e7f1e22d774aded2038d8cf56cbe313893a1b6e36c918c8070c65b7c0e1 --version 2.7.0
.venv/bin/python tools/close.py /tmp/unicode-graft-new/snapshot.json /tmp/unicode-graft-new/target-arm64.dylib /tmp/unicode-graft-new/capsule.json
```

Calculate the new capsule SHA256, then bind it using `tools/bind.py` and
`features/utf8proc/abi.json`. The binder requires that exact expected digest:

```sh
python3 tools/bind.py /tmp/unicode-graft-new/capsule.json features/utf8proc/abi.json /tmp/unicode-graft-new/feature.json --name unicode-new --expected-capsule-sha256 REPLACE_WITH_NEW_CAPSULE_SHA256
python3 -I -S run.py verify /tmp/unicode-graft-new features/utf8proc/cases.json
```

The ABI uses input address, input byte length, an owned output-pointer cell and
unsigned option flags. Return is a signed length or native negative error.
Addresses vary across native snapshot processes, so equivalent new capsules
need not have identical bytes. Their original target identity must match; their
fresh capsule identity is bound and checked. The generic runtime treats captured
addresses as virtual numeric addresses, not host-native function pointers.

## Decoder reproduction and counterexamples

The exact original universal decoder image SHA256 is
`9869966bf2a7375e739e6102e677998db7ea4a9096d31129b98120439dcfa5d0`, at
`/Library/Frameworks/Python.framework/Versions/3.14/lib/libzstd.1.5.7.dylib`.
Its selected ARM64 slice SHA256 is
`d6bf3d7bc948fb8d9dc990634cfb6c045e4200ac072ef641f86c6d1ce1d0b115`.

Run `snapshot.py` with this universal hash, `--entry ZSTD_decompress` and
`--version 1.5.7`. Run `close.py` with the new snapshot and target, adding
`--seed-capsule features/zstd/capsule.json --seed-entry ZSTD_decompress`.
This preserves the previous observed text-data ranges and code candidates.
Seed instruction addresses are rebased and freshly lifted; data ranges are
copied from the new image. Prior IR with a stale load slide is not reused.
Bind the result using `features/zstd/abi.json` and its new capsule digest.

That complete generic sequence was locally reproduced at new load addresses:
404 symbol bodies / 67,191 instruction addresses and the sample output hash
matched. `features/zstd/reproduction.json` records the result. Its prior seeds
remain conservative, not a fresh discovery proof for an unfamiliar artifact.

For a new target, freeze a candidate before generating new native-oracle inputs.
`oracle_utf8proc.py` shows the explicit separate oracle boundary. A refused
unknown path/dependency is a counterexample, not permission to guess a result.
Enlarge only from supported binary/environment evidence, freeze again and
distinguish refinement inputs from fresh comparisons. Do not translate every
symbol and call it a minimal feature. Report retained code/data, unproved paths,
environment bounds, licensing and observed outcomes with the resulting artifact.
