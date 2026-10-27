"""Auditable first-stage model checks. Partial coverage never certifies a model."""
from hashlib import sha256
import json
import math
from calculations.validation import finite, checked_numeric
from database.design_table_api import get_min_slope


def initial_mapping(inventory):
    return [dict(source_id=row['source_id'], source_name=row['name'], source_system=row['system'],
        include=row['kind'] == 'pipe', service='UNMAPPED',
        nominal_mm=None, internal_mm=None, design_flow_lps=None,
        invert_start_m=None, invert_end_m=None, direction_confirmed=False, input_reference='',
        exclusion_reason='') for row in inventory['objects']]


@checked_numeric
def review_model(conn, code, inventory, mapping, *, mapping_reference, reviewed,
                 velocity_limit_m_s=None, velocity_reference=''):
    if reviewed is not True or not isinstance(mapping_reference, str) or not mapping_reference.strip():
        raise ValueError('Confirm the mapping and provide its reviewer/evidence reference before checking.')
    source = {row['source_id']: row for row in inventory['objects']}
    if len(mapping) != len(source) or {r.get('source_id') for r in mapping} != set(source):
        raise ValueError('Mapping must contain every source object exactly once, without foreign IDs.')
    findings = []

    def issue(obj, check, status, detail, *, actual=None, required=None, unit=None, reference=None):
        findings.append(dict(source_id=obj['source_id'], source_class=obj['source_class'], check_id=check,
            status=status, actual=actual, required=required, unit=unit, reference=reference,
            detail=detail, review_status='REVIEW_REQUIRED'))

    for row in mapping:
        obj = source[row['source_id']]
        if not isinstance(row.get('include'), bool):
            raise ValueError('Include must be a Boolean for every mapped object.')
        if not row['include']:
            reason = row.get('exclusion_reason')
            issue(obj, 'scope', 'EXCLUDED' if reason else 'NOT_EVALUATED', reason or 'Object has no reviewed scope/exclusion decision.')
            continue
        if obj['kind'] not in ('pipe', 'pipe_candidate'):
            issue(obj, 'object_type', 'UNSUPPORTED', 'Fixture, fitting and equipment checks are outside this first pilot.')
            continue
        if obj.get('length_m') is None:
            issue(obj, 'centreline_geometry', 'MISSING_DATA', 'No supported measured centreline; no length was approximated.')
        else:
            issue(obj, 'centreline_geometry', 'MEASURED', 'Extracted centreline length; this does not establish code compliance.',
                actual=obj['length_m'], unit='m', reference=obj.get('length_reference'))
        service = row.get('service')
        if service not in ('cold_water', 'hot_water', 'drainage'):
            issue(obj, 'service_mapping', 'MISSING_DATA', 'Map the element to cold water, hot water or drainage.')
            continue
        if not isinstance(row.get('input_reference'), str) or not row['input_reference'].strip():
            issue(obj, 'engineering_input_evidence', 'MISSING_DATA', 'Reference the bore/flow or nominal/invert inputs for this element.')
            continue
        if service in ('cold_water', 'hot_water'):
            diameter, flow = row.get('internal_mm'), row.get('design_flow_lps')
            if diameter is None or flow is None or velocity_limit_m_s is None or not velocity_reference.strip():
                issue(obj, 'water_velocity', 'MISSING_DATA', 'Actual internal bore, design flow and a referenced velocity criterion are required. Nominal size is not a bore.')
            else:
                finite('internal_mm', diameter, positive=True)
                finite('design_flow_lps', flow, minimum=0)
                finite('velocity_limit_m_s', velocity_limit_m_s, positive=True)
                velocity = (flow / 1000) / (math.pi * (diameter / 1000) ** 2 / 4)
                finite('calculated velocity', velocity, minimum=0)
                issue(obj, 'water_velocity', 'PASS' if velocity <= velocity_limit_m_s else 'FAIL',
                    'Q / internal flow area against the supplied criterion; pressure adequacy is not checked.',
                    actual=velocity, required=velocity_limit_m_s, unit='m/s', reference=velocity_reference)
            issue(obj, 'water_pressure_and_network', 'NOT_EVALUATED',
                'Source head, reviewed connectivity, fitting/equipment losses, fixture loads and terminal pressure criteria require a complete Network Review.')
        else:
            start, end, nominal = row.get('invert_start_m'), row.get('invert_end_m'), row.get('nominal_mm')
            run = obj.get('horizontal_run_m')
            if obj.get('axis_segment_count') != 1:
                issue(obj, 'drainage_slope', 'UNSUPPORTED', 'Slope pilot requires an individual straight segment; split polylines to avoid concealing adverse intermediate grades.')
            elif row.get('direction_confirmed') is not True or any(v is None for v in (start, end, nominal, run)):
                issue(obj, 'drainage_slope', 'MISSING_DATA', 'Confirm upstream-to-downstream direction and provide invert levels and nominal size; centreline Z is not used as invert.')
            elif run <= 0:
                issue(obj, 'drainage_slope', 'UNSUPPORTED', 'Vertical segments need stack checks, not horizontal minimum-slope checks.')
            else:
                finite('invert_start_m', start); finite('invert_end_m', end)
                finite('nominal_mm', nominal, positive=True); finite('horizontal_run_m', run, positive=True)
                if obj.get('start_xyz_m') is not None and obj.get('end_xyz_m') is not None:
                    centreline_fall = obj['start_xyz_m'][2] - obj['end_xyz_m'][2]
                    if abs((start - end) - centreline_fall) > 1e-6:
                        issue(obj, 'invert_geometry_consistency', 'WARNING',
                            'Reviewed invert fall differs from source centreline fall. Confirm the override, datum, endpoint definitions and diameters.',
                            actual=start-end, required=centreline_fall, unit='m', reference=row['input_reference'])
                slope = 100 * (start - end) / run
                finite('calculated slope', slope)
                limit = get_min_slope(conn, code, nominal)
                if limit is None:
                    issue(obj, 'drainage_slope', 'MISSING_DATA', 'No matching selected-code minimum slope; no fallback code was substituted.',
                          actual=slope, unit='%')
                else:
                    finite('source minimum slope', limit.value, positive=True)
                    status = 'FAIL' if slope < limit.value else ('WARNING' if limit.confidence != 'CONFIRMED' else 'PASS')
                    issue(obj, 'drainage_slope', status, 'Slope from reviewed invert fall / extracted plan run. Flagged table sources retain a warning.',
                        actual=slope, required=limit.value, unit='%', reference=f'{limit.code_id}: {limit.table_reference}')
            issue(obj, 'drainage_capacity_and_vents', 'NOT_EVALUATED',
                'Connected DFU, pipe context, branch intervals and vent/trap arrangements require complete network mapping.')
    failures = sum(f['status'] == 'FAIL' for f in findings)
    return dict(source_sha256=inventory['source_sha256'], source_model_id=inventory.get('model_id'),
        filename=inventory['filename'], code_id=code, adapter_revision=inventory['adapter_revision'],
        mapping_sha256=sha256(json.dumps(mapping, sort_keys=True, allow_nan=False).encode()).hexdigest(),
        mapping_reference=mapping_reference, technical_status='FAIL' if failures else 'PARTIAL',
        coverage_status='PARTIAL', review_status='REVIEW_REQUIRED', failure_count=failures,
        findings=findings, limitations=inventory['limitations'] + [
            'Pilot checks selected pipe velocity and straight-segment drainage slope only.',
            'Scope exclusions, missing data and unevaluated checks remain visible. A passing individual check does not certify the model.'])
