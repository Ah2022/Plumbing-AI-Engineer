"""Code and runtime fingerprints for saved calculations and review exports."""
from functools import lru_cache
import hashlib
from importlib.metadata import version, PackageNotFoundError
import json
from pathlib import Path
import platform

ROOT = Path(__file__).resolve().parents[1]


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


@lru_cache(maxsize=4)
def _manifest(signature):
    files = {name: hashlib.sha256((ROOT/name).read_text(encoding='utf-8').encode()).hexdigest() for name, _, _ in signature}
    dependencies = {}
    for package in ('streamlit', 'numpy', 'pandas', 'openpyxl', 'ifcopenshell', 'ezdxf', 'pypdfium2'):
        try:
            dependencies[package] = version(package)
        except PackageNotFoundError:
            dependencies[package] = 'not installed'
    runtime = dict(python=platform.python_version(), dependencies=dependencies)
    return dict(files=files, source_sha256=digest(files), runtime_sha256=digest(runtime), **runtime)


def engine_manifest():
    paths = sorted(p for folder in ('app', 'calculations', 'database', 'compliance', 'models', 'reports', 'bim', 'units', 'workbooks')
                   for p in (ROOT/folder).rglob('*.py') if '__pycache__' not in p.parts)
    signature = tuple((p.relative_to(ROOT).as_posix(), p.stat().st_mtime_ns, p.stat().st_size) for p in paths)
    # Return a copy so callers cannot mutate the cached manifest.
    return json.loads(json.dumps(_manifest(signature)))
