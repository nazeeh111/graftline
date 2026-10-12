# Third-party material and modification notice

`features/zstd/capsule.json` contains instructions and data extracted from the
Python-distributed libzstd 1.5.7 ARM64 library. The original BSD notice is in
`features/zstd/LICENSE-Zstandard.txt`. Preserve it with the capsule.

`features/utf8proc/capsule.json` contains instructions and Unicode data extracted
from MATLAB's shipped third-party utf8proc library. The native API reports 2.7.0
and Unicode 14.0.0. Its installed `utf8proc.rights` notice is reproduced exactly
in `features/utf8proc/LICENSE.md`; it also matches upstream v2.7.0's notice.
It covers the MIT-licensed library and Unicode-derived tables. The MATLAB
application itself and proprietary components are not included or required by
closed execution.

Modification notice: the extracted software is changed in representation and
environment. Selected machine instructions are translated to generic p-code,
code/table bytes are serialized, original-loaded relocation addresses become
virtual addresses, and native memory dependencies use bounded authored models.
This is a modified export, not an upstream library release. Preserve this notice
and the original copyrights with redistributed code/data and documentation.

Generic lifting during extraction uses pypcode 4.0.1's instruction descriptions.
pypcode is not included or imported during closed execution. Its own package
licenses apply when installing or redistributing that separate dependency.
