"""DWG intake: provenance, optional local ODA conversion, or reviewed companion DXF."""
from hashlib import sha256
import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory

VERSIONS = {'AC1009': 'R12', 'AC1012': 'R13', 'AC1014': 'R14', 'AC1015': '2000',
    'AC1018': '2004', 'AC1021': '2007', 'AC1024': '2010', 'AC1027': '2013', 'AC1032': '2018+'}
MAX_BYTES = 20 * 1024 * 1024


def converter_path():
    """Executable comes only from deployment configuration or installed tools, never an upload."""
    configured = os.environ.get('PLUMBING_ODA_CONVERTER')
    if configured:
        candidate = Path(configured)
        return str(candidate) if candidate.is_absolute() and candidate.is_file() else None
    discovered = shutil.which('ODAFileConverter')
    if discovered:
        return discovered
    if os.name == 'nt':
        root = Path(os.environ.get('ProgramFiles', r'C:\Program Files')) / 'ODA'
        if root.is_dir():
            return next((str(p) for p in sorted(root.glob('ODAFileConverter*/ODAFileConverter.exe')) if p.is_file()), None)
    return None


def convert_dwg(data, executable):
    with TemporaryDirectory(prefix='plumbing-dwg-') as folder:
        root = Path(folder); source = root / 'input'; target = root / 'output'
        source.mkdir(); target.mkdir()
        (source / 'model.dwg').write_bytes(data)
        options = {}
        if os.name == 'nt':
            info = subprocess.STARTUPINFO()
            info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            info.wShowWindow = subprocess.SW_HIDE
            options.update(startupinfo=info, creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            result = subprocess.run([executable, str(source), str(target), 'ACAD2018', 'DXF', '0', '1', 'model.dwg'],
                shell=False, capture_output=True, timeout=60, **options)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise ValueError('Local DWG conversion failed or exceeded 60 seconds. Export a DXF and attach it instead.') from error
        files = [p for p in target.iterdir() if p.is_file() and p.suffix.lower() == '.dxf']
        if result.returncode or len(files) != 1:
            raise ValueError('Local converter did not produce exactly one DXF. Attach an exported DXF instead.')
        if not 0 < files[0].stat().st_size <= MAX_BYTES:
            raise ValueError('Converted DXF exceeds the 20 MB intake limit or is empty.')
        return files[0].read_bytes()


def read_dwg(data, *, companion_dxf=None, pair_confirmed=False, dxf_unit=None):
    signature = data[:6].decode('ascii', errors='replace')
    if signature not in VERSIONS or len(data) < 128:
        raise ValueError('DWG header is missing, unsupported or truncated. Supply an actual DWG file.')
    result = dict(format='DWG', schema=signature, model_id=None, geometry_ready=False,
        intake_status='CONVERSION_REQUIRED', objects=[], connections=[],
        unit_evidence=dict(length_scale_to_m=None, source='DWG header only; drawing units not yet decoded'),
        dwg_version=VERSIONS[signature], content_validation='HEADER_ONLY',
        limitations=['DWG header inspection does not validate drawing contents or establish pipe geometry.',
            'Geometry checks need local ODA conversion or a reviewed companion DXF export.',
            'Conversion and exported handles require review; no automatic whole-drawing compliance claim is made.'])
    converted = companion_dxf
    method = 'REVIEWED_COMPANION_DXF'
    if converted is not None:
        if not isinstance(converted, bytes) or not 0 < len(converted) <= MAX_BYTES:
            raise ValueError('Companion DXF must be nonempty and no larger than 20 MB.')
        if pair_confirmed is not True:
            raise ValueError('Confirm that the companion DXF was exported from this DWG revision.')
    else:
        executable = converter_path()
        if executable:
            try:
                converted = convert_dwg(data, executable)
            except ValueError as error:
                result['conversion_error'] = str(error)
                return result
            method = 'LOCAL_ODA_CONVERSION'
    if converted is None:
        return result
    from bim.dxf_intake import read_dxf
    geometry = read_dxf(converted, dxf_unit)
    result.update(objects=geometry['objects'], connections=geometry['connections'],
        unit_evidence=geometry['unit_evidence'], geometry_ready=True, intake_status='CONVERTED_GEOMETRY_REVIEW',
        conversion=dict(method=method, dxf_sha256=sha256(converted).hexdigest(), dxf_schema=geometry['schema'],
                        correspondence='USER_CONFIRMED' if companion_dxf is not None else 'CONVERTER_OUTPUT'),
        ignored_entities=geometry['ignored_entities'])
    result['limitations'] += geometry['limitations']
    return result
