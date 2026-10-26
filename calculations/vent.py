"""
calculations/vent.py
-----------------------
Vent diameter sizing (by connected DFU load) and trap-arm distance
checking, against the real code tables loaded in Phase 2/2.5.

SAUDI_SBC_701's own Table 906 (vent stack sizing) was confirmed
not-independently-re-extractable (docs/ARCHITECTURE.md Section 0b item 2).
The decision Ahmed recorded was: fall back to IPC's confirmed Table 906.1
via the same explicit, logged fallback pattern used for velocity limits —
implemented below in size_vent_pipe(). Never silent.
"""

from __future__ import annotations

from calculations.validation import finite

from database.design_table_api import get_table_records
from models import CalculationResult, MissingCodeDataError

VENT_DFU_COLUMN_HINTS = ["dfu_load", "fu", "vent_max_units"]
VENT_SIZE_COLUMN_HINTS = ["pipe_size_mm", "vent_in", "vent_mm","pipe_in"]


def _find_vent_table(conn, code_id: str):
    """Prefer a SIMPLE 2-column (DFU-load -> vent-size) table. Codes whose
    only vent table is a multi-dimensional lookup (e.g. IPC's Table 906.1:
    stack_in + fu + vent_in + max_len_ft, where vent_in is in INCHES and
    depends on stack size AND developed length, not on FU alone) are
    deliberately NOT matched here — applying the simple algorithm to that
    table would silently pick the wrong column and the wrong unit. Use
    size_vent_pipe_multidim() for those instead."""
    records = get_table_records(conn, code_id, "vent", "7_Vent_Sizing")
    simple_records = [r for r in records if "stack_in" not in r and "max_len_ft" not in r
                      and "trap_arm_in" not in r and "max_dist_trap_to_vent_ft" not in r
                      and "waste_size_in" not in r and 'stack_size_mm' not in r
                      and 'trap_size_mm' not in r and 'max_distance_m_truncated' not in r]
    dfu_col = next((h for h in VENT_DFU_COLUMN_HINTS if any(h in r for r in simple_records)), None)
    size_col = next((h for h in VENT_SIZE_COLUMN_HINTS if any(h in r for r in simple_records)), None)
    return simple_records, dfu_col, size_col


def size_vent_pipe(conn, code_id: str, total_dfu: float, calc_id: str,
                    allow_fallback_code: str = None, developed_length_m=None) -> CalculationResult:
    """Selects the smallest vent diameter whose DFU-load capacity covers total_dfu."""
    finite('total_dfu',total_dfu,minimum=0)
    records, dfu_col, size_col = _find_vent_table(conn, code_id)

    if not records or dfu_col is None or size_col is None:
        if allow_fallback_code and allow_fallback_code!=code_id:
            fallback=size_vent_pipe(conn,allow_fallback_code,total_dfu,calc_id,developed_length_m=developed_length_m)
            fallback.status='WARNING';fallback.reference+=f' (fallback from {allow_fallback_code} for {code_id})'
            fallback.notes=(fallback.notes or '')+' Explicit substitute; project applicability requires approval.'
            return fallback
        hint = (" IPC only has the multi-dimensional Table 906.1 for vent sizing — "
                "use size_vent_pipe_multidim() instead (needs stack size and developed "
                "length, not just total DFU)." if code_id == "IPC" or allow_fallback_code == "IPC" else "")
        raise MissingCodeDataError(
            what="Vent diameter-vs-DFU-load table (simple 1D form)",
            where=f"code={code_id} — no simple DFU-load-to-vent-size table found.{hint}",
        )

    candidates = []
    for rec in records:
        size_val = rec.get(size_col, (None, None, None))
        dfu_val = rec.get(dfu_col, (None, None, None))
        if size_val[0] is None or dfu_val[0] is None:
            continue
        max_length=rec.get('vent_max_length_ft',(None,None,None))[0]
        if max_length is not None:
            if developed_length_m is None: raise MissingCodeDataError('Vent developed length','Length is required by the selected source table')
            finite('developed_length_m',developed_length_m,minimum=0)
            if developed_length_m>max_length*0.3048+1e-9: continue
        mm=size_val[0]*25.4 if size_col in ('pipe_in','vent_in') else size_val[0]
        finite('table vent size',mm,positive=True);finite('table DFU capacity',dfu_val[0],minimum=0)
        candidates.append((mm, dfu_val[0], 'FLAGGED' if 'FLAGGED' in (size_val[2],dfu_val[2]) else 'CONFIRMED'))
    candidates.sort(key=lambda c: c[0])

    for vent_mm, max_dfu, confidence in candidates:
        if total_dfu <= max_dfu:
            return CalculationResult(
                calc_id=calc_id,
                calc_type="vent_pipe_sizing",
                formula=f"Select smallest vent where {dfu_col} >= total_dfu",
                inputs={"total_dfu": (total_dfu, "DFU")},
                intermediate={"candidates_checked": len(candidates)},
                result_value=vent_mm,
                result_unit="mm",
                required_value=total_dfu,
                selected_value=vent_mm,
                status="PASS" if confidence == "CONFIRMED" else "WARNING",
                reference=f"{code_id}:7_Vent_Sizing [{dfu_col}]",
                notes=None if confidence == "CONFIRMED" else "Underlying table row is FLAGGED — confirm before sign-off.",
            )

    if allow_fallback_code:
        fallback=size_vent_pipe(conn, allow_fallback_code, total_dfu, calc_id, developed_length_m=developed_length_m)
        fallback.status='WARNING'
        fallback.reference+=f' (fallback from {allow_fallback_code} for {code_id})'
        fallback.notes=(fallback.notes or '')+' Explicit cross-code substitute; applicability requires approval.'
        return fallback
    raise MissingCodeDataError(
        what=f"A vent size covering {total_dfu} DFU",
        where=f"code={code_id} — total_dfu exceeds every size in the table.",
    )


def size_vent_pipe_multidim(conn, code_id: str, stack_size_in: float, total_fu: float,
                             developed_length_ft: float, calc_id: str) -> CalculationResult:
    """
    For codes whose vent table is multi-dimensional (stack size x FU x vent
    size x max developed length) — IPC's confirmed Table 906.1 is the only
    one currently loaded in this shape. Units are INCHES/FEET here (the
    table's own units), unlike the rest of this module which works in mm —
    convert at the call site via units/convert.py.

    Picks the smallest vent_in where: the row's stack_in matches, fu >=
    total_fu, and max_len_ft >= developed_length_ft.
    """
    finite('stack_size_in',stack_size_in,positive=True)
    finite('total_fu',total_fu,minimum=0)
    finite('developed_length_ft',developed_length_ft,minimum=0)
    records = get_table_records(conn, code_id, "vent", "7_Vent_Sizing")
    multidim = [r for r in records if "stack_in" in r and "max_len_ft" in r]
    if not multidim:
        raise MissingCodeDataError(
            what="Multi-dimensional vent table (stack_in/fu/vent_in/max_len_ft)",
            where=f"code={code_id}",
        )

    candidates = []
    for rec in multidim:
        stack = rec.get("stack_in", (None, None, None))[0]
        fu = rec.get("fu", (None, None, None))[0]
        vent_in = rec.get("vent_in", (None, None, None))
        max_len = rec.get("max_len_ft", (None, None, None))[0]
        if None in (stack, fu, vent_in[0], max_len):
            continue
        finite('source stack nominal size',stack,positive=True)
        finite('source vent nominal size',vent_in[0],positive=True)
        finite('source fixture-unit capacity',fu,minimum=0)
        finite('source maximum vent length',max_len,minimum=0)
        if stack == stack_size_in and fu >= total_fu and max_len >= developed_length_ft:
            candidates.append((vent_in[0], vent_in[2]))
    if not candidates:
        raise MissingCodeDataError(
            what=f"Vent size for stack={stack_size_in}in, FU={total_fu}, length={developed_length_ft}ft",
            where=f"code={code_id} — no row in Table 906.1 satisfies all three constraints "
                  f"simultaneously; may need a larger stack size or shorter run.",
        )
    candidates.sort(key=lambda c: c[0])
    vent_in, confidence = candidates[0]

    return CalculationResult(
        calc_id=calc_id,
        calc_type="vent_pipe_sizing",
        formula="Smallest vent_in where stack_in matches AND fu>=total_fu AND max_len_ft>=developed_length_ft",
        inputs={"stack_size_in": (stack_size_in, "in"), "total_fu": (total_fu, "FU"),
                "developed_length_ft": (developed_length_ft, "ft")},
        intermediate={"candidates_found": len(candidates)},
        result_value=vent_in,
        result_unit="in",
        required_value=total_fu,
        selected_value=vent_in,
        status="PASS" if confidence == "CONFIRMED" else "WARNING",
        reference=f"{code_id}:7_Vent_Sizing Table 906.1",
        notes="Result is in INCHES (source table's own units) — convert via units/convert.py before "
              "combining with mm-based pipe schedules." + (
                  "" if confidence == "CONFIRMED" else " Underlying row is FLAGGED."),
    )


def check_trap_arm(conn,code_id,nominal_mm,developed_length_m,calc_id):
    """Distance-table check only, not approval of trap/vent arrangement."""
    finite('nominal_mm',nominal_mm,positive=True)
    finite('developed_length_m',developed_length_m,minimum=0)
    records=get_table_records(conn,code_id,'vent','7_Vent_Sizing')
    matches=[]
    for row in records:
        size=row.get('trap_arm_in',(None,None,None))[0]
        length=row.get('max_dist_trap_to_vent_ft',(None,None,None))
        if size is not None and length[0] is not None and abs(size*25.4-nominal_mm)<1e-6:
            matches.append((length[0]*0.3048,length[2],row.get('_table_reference')))
    if not matches: raise MissingCodeDataError('Complete trap-arm distance table',f'code={code_id}, nominal={nominal_mm}mm')
    limits={r[0] for r in matches}
    if len(limits)!=1: raise MissingCodeDataError('Unambiguous trap-arm criterion','Multiple source rows require applicability review')
    limit,confidence,reference=matches[0]
    status='FAIL' if developed_length_m>limit+1e-9 else 'WARNING' if any(r[1]=='FLAGGED' for r in matches) else 'PASS'
    return CalculationResult(calc_id,'trap_arm_distance_check','developed_length_m <= source table maximum',
        {'nominal_mm':(nominal_mm,'mm'),'developed_length_m':(developed_length_m,'m')},{},developed_length_m,'m',
        required_value=limit,selected_value=developed_length_m,status=status,reference=f'{code_id}:{reference}',
        notes='Distance only; trap weir, fall, vent connection, fixture exceptions and arrangement require separate review.')


def check_vent_arrangement(conn,code_id,vent,dfu_load):
    if not isinstance(vent,dict): raise ValueError('Vent must be a structured object')
    vid=vent.get('id')
    if not isinstance(vid,str) or not vid: raise ValueError('Vent ID required')
    arrangement=vent.get('arrangement')
    if arrangement!='dry':
        return dict(vent_id=vid,technical_status='NOT_EVALUATED',reason='Wet/circuit/AAV/unspecified arrangements need dedicated applicability rules')
    nominal=finite('selected vent nominal_mm',vent.get('selected_nominal_mm'),positive=True)
    length=finite('developed_length_m',vent.get('developed_length_m'),minimum=0)
    try:
        if code_id=='IPC':
            stack=finite('stack_source_nominal_in',vent.get('stack_source_nominal_in'),positive=True)
            selected_in=finite('selected_source_nominal_in',vent.get('selected_source_nominal_in'),positive=True)
            r=size_vent_pipe_multidim(conn,code_id,stack,dfu_load,length/0.3048,'V-'+vid)
            required=r.result_value*25.4
            nominal_ok=selected_in>=r.result_value
        else:
            r=size_vent_pipe(conn,code_id,dfu_load,'V-'+vid,developed_length_m=length)
            required=r.result_value
            nominal_ok=nominal+1e-9>=required
        status='FAIL' if not nominal_ok else 'WARNING' if r.status=='WARNING' else 'PASS'
        result=dict(vent_id=vid,technical_status=status,load_dfu=dfu_load,required_nominal_mm=required,
                    selected_nominal_mm=nominal,reference=r.reference,coverage_status='PARTIAL')
        if 'trap_arm' in vent:
            arm=vent['trap_arm']
            a=check_trap_arm(conn,code_id,arm['nominal_mm'],arm['developed_length_m'],'TA-'+vid)
            result['trap_arm']={'technical_status':a.status,'required_maximum_m':a.required_value,'reference':a.reference}
            if a.status=='FAIL': result['technical_status']='FAIL'
            elif a.status=='WARNING' and status=='PASS': result['technical_status']='WARNING'
        else:
            result['technical_status']='WARNING' if status=='PASS' else status
            result['reason']='Trap-arm/connection geometry not supplied; sizing alone is not vent-arrangement compliance'
        return result
    except MissingCodeDataError as e:
        return dict(vent_id=vid,technical_status='MISSING_DATA',reason=str(e))
