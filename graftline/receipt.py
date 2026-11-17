"""Current local verification receipt; hashes do not authenticate their producer."""
import hashlib
import json
from pathlib import Path
import platform
from ._output import publish_bytes


def digest(data):
    return hashlib.sha256(data).hexdigest()


def identity(feature):
    package = Path(__file__).resolve().parent
    sources = {name: digest((package / name).read_bytes()) for name in ('__init__.py', '__main__.py', 'api.py', 'runtime.py', 'receipt.py', '_output.py')}
    licenses = {p.name: digest(p.read_bytes()) for p in sorted(feature.iterdir()) if p.name.startswith('LICENSE') and p.is_file() and not p.is_symlink()}
    return {'engine_source_sha256': sources, 'license_sha256': licenses}


def make(feature, case_bytes, results, summary, observed):
    return {
        'schema': 'graftline-current-validation-v1',
        'engine': {**observed, 'python_implementation': platform.python_implementation(), 'python_version': platform.python_version()},
        'inputs': {'feature_sha256': digest(feature.manifest_bytes), 'capsule_sha256': digest(feature.capsule_bytes), 'cases_sha256': digest(case_bytes)},
        'specimen': {'name': feature.manifest.get('name'), 'source_boundary': feature.manifest.get('sourceBoundary'), 'refusal_model': feature.manifest.get('refusalModel')},
        'validation': {'rerun': True, 'summary': summary, 'cases': results},
        'scope': 'Observed local rerun against supplied case expectations; hashes are not authentication, native parity proof, or complete refusal coverage.'
    }


def publish(path, receipt):
    path = Path(path)
    data = (json.dumps(receipt, indent=2, sort_keys=True) + '\n').encode()
    publish_bytes(path, data)


def check(path, current):
    path = Path(path)
    if path.stat().st_size > 10_000_000:
        raise ValueError('Receipt exceeds 10 MB')
    saved = json.loads(path.read_bytes())
    canonical = lambda value: json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)
    if canonical(saved) != canonical(current):
        raise ValueError('Receipt differs from current inputs or rerun results')
