"""
calculations/drainage.py
--------------------------
DFU (drainage fixture unit) -> pipe diameter sizing, and minimum-slope
checking, against the real code tables loaded in Phase 2/2.5
(database/code_design_data/*.xlsx, table domain='drainage').

Column-naming differs by code (SBC 701 gives 'max_dfu_horiz_branch' /
'max_dfu_stack_le3_bi' / 'max_dfu_stack_gt3_bi' / 'max_dfu_per_branch_interval'
directly in mm; IPC/UPC give similar concepts under different names) — the
lookup below matches on a configurable substring per `context`, so a new
code just needs its column names added to CONTEXT_COLUMN_HINTS, no logic
change.
"""

from __future__ import annotations

from calculations.validation import finite

from database.design_table_api import get_table_records, get_min_slope
from calculations.hydraulics import velocity_from_flow
from models import CalculationResult, MissingCodeDataError

# context -> substrings to look for in the drainage-sizing table's column names.
# First matching column wins. Extend per-code as new column vocabularies show up.
CONTEXT_COLUMN_HINTS = {
    "horizontal_branch": ["max_dfu_horiz_branch", "horiz_branch", "drainage_max_units_horiz","drainage_max_units_horizontal"],
    "stack_le3_branch_intervals": ["max_dfu_stack_le3_bi", "drainage_max_units_vertical"],
    "stack_gt3_branch_intervals": ["max_dfu_stack_gt3_bi","max_dfu_stack_gt3_bi_total"],
    "branch_interval": ["max_dfu_per_branch_interval","max_dfu_stack_gt3_bi_per_interval"],
    "building_drain": [],"building_sewer": [],
}

PIPE_SIZE_COLUMN_HINTS = ["pipe_mm", "pipe_size_mm","pipe_in"]


def size_drainage_pipe(conn, code_id: str, total_dfu: float, context: str, calc_id: str,
                       selected_slope_pct=None) -> CalculationResult:
    """
    Selects the smallest pipe size whose max-DFU capacity (for the given
    context) is >= total_dfu. Raises MissingCodeDataError if the code's
    drainage-sizing table doesn't have a column for this context, or if
    total_dfu exceeds every size in the table (needs engineer judgement,
    not a silent largest-size guess).
    """
    finite('total_dfu',total_dfu,minimum=0)
    if context not in CONTEXT_COLUMN_HINTS:
        raise ValueError(f"Unknown context '{context}'. Valid: {list(CONTEXT_COLUMN_HINTS)}")

    records = get_table_records(conn, code_id, "drainage", "5_Drainage_Sizing")
    if not records:
        raise MissingCodeDataError(what="Drainage sizing table", where=f"code={code_id}")

    size_col = next((c for c in PIPE_SIZE_COLUMN_HINTS if any(c in rec for rec in records)), None)
    dfu_col = next((h for h in CONTEXT_COLUMN_HINTS[context] if any(h in rec for rec in records)), None)
    if context in ('building_drain','building_sewer'):
        finite('selected_slope_pct',selected_slope_pct,positive=True)
        # Column labels encode the source slope; select a column no steeper than actual slope.
        slopes={'slope_1_16':100/192,'slope_1_8':100/96,'slope_1_4':100/48,'slope_1_2':100/24,
                'slope_5mm':0.5,'slope_10mm':1.,'slope_20mm':2.,'slope_40mm':4.}
        usable=[(value,key) for key,value in slopes.items() if value<=selected_slope_pct+1e-9 and any(key in r for r in records)]
        dfu_col=max(usable)[1] if usable else None
    if size_col is None or dfu_col is None:
        raise MissingCodeDataError(
            what=f"Drainage sizing column for context='{context}'",
            where=f"code={code_id}, table=5_Drainage_Sizing (columns seen: "
                  f"{sorted(set(k for r in records for k in r if not k.startswith('_')))})",
        )

    candidates = []
    for rec in records:
        row_size_col=next((c for c in PIPE_SIZE_COLUMN_HINTS if rec.get(c,(None,None,None))[0] is not None),None)
        size_val = rec.get(row_size_col, (None, None, None))
        dfu_val = rec.get(dfu_col, (None, None, None))
        if size_val[0] is None or dfu_val[0] is None:
            continue  # non-numeric band ("per design") -> not a candidate, not a silent match
        pipe_mm=size_val[0]*25.4 if row_size_col=='pipe_in' else size_val[0]
        finite('table nominal size',pipe_mm,positive=True);finite('table DFU capacity',dfu_val[0],minimum=0)
        conf='FLAGGED' if 'FLAGGED' in (size_val[2],dfu_val[2]) else 'CONFIRMED'
        candidates.append((pipe_mm, dfu_val[0], conf, size_val[0], 'in' if row_size_col=='pipe_in' else 'mm'))
    candidates.sort(key=lambda c: c[0])

    for pipe_mm, max_dfu, confidence,source_size,source_unit in candidates:
        if total_dfu <= max_dfu:
            return CalculationResult(
                calc_id=calc_id,
                calc_type="drainage_pipe_sizing",
                formula=f"Select smallest pipe where {dfu_col} >= total_dfu",
                inputs={"total_dfu": (total_dfu, "DFU"), "context": (context, "-")},
                intermediate={"candidates_checked": len(candidates),'source_nominal_value':source_size,'source_nominal_unit':source_unit},
                result_value=pipe_mm,
                result_unit="mm",
                required_value=total_dfu,
                selected_value=pipe_mm,
                status="PASS" if confidence == "CONFIRMED" else "WARNING",
                reference=f"{code_id}:5_Drainage_Sizing [{dfu_col}]",
                notes=None if confidence == "CONFIRMED" else "Underlying table row is FLAGGED — confirm before sign-off.",
            )

    raise MissingCodeDataError(
        what=f"A pipe size covering {total_dfu} DFU in context='{context}'",
        where=f"code={code_id} — total_dfu exceeds every size in the table; needs engineer judgement "
              f"(parallel stacks, reduced venting, etc.), not an automatic largest-size selection.",
    )


def check_min_slope(conn, code_id: str, pipe_size_mm: float, selected_slope_pct: float, calc_id: str,
                     allow_fallback_code: str = None) -> CalculationResult:
    """Checks a selected slope against the code's minimum-slope table for this pipe size."""
    finite('pipe_size_mm',pipe_size_mm,positive=True)
    finite('selected_slope_pct',selected_slope_pct,minimum=0)
    limit = get_min_slope(conn, code_id, pipe_size_mm, allow_fallback_code=allow_fallback_code)
    if limit is None:
        raise MissingCodeDataError(
            what=f"Minimum slope for {pipe_size_mm}mm pipe",
            where=f"code={code_id} — no matching band in 6_Min_Slope",
        )

    status = "PASS" if selected_slope_pct >= limit.value else "FAIL"
    if limit.confidence == "FLAGGED" and status == "PASS":
        status = "WARNING"

    return CalculationResult(
        calc_id=calc_id,
        calc_type="drainage_min_slope_check",
        formula="selected_slope_pct >= min_slope_pct (code table, by pipe-size band)",
        inputs={"pipe_size_mm": (pipe_size_mm, "mm"), "selected_slope_pct": (selected_slope_pct, "%")},
        intermediate={},
        result_value=selected_slope_pct,
        result_unit="%",
        required_value=limit.value,
        selected_value=selected_slope_pct,
        status=status,
        reference=f"{limit.code_id}:{limit.table_reference}" + (
            f" (fallback from {limit.fallback_from})" if limit.fallback_from else ""
        ),
        notes=limit.notes,
    )


def check_drainage_velocity(flow_lps: float, internal_diameter_mm: float, calc_id: str,
                             min_self_cleansing_m_s=None,
                             max_velocity_m_s=None, *, criteria_reference=None) -> CalculationResult:
    """
    Self-cleansing / erosion-limit check for gravity drainage. Defaults are
    IPC's own confirmed general-guidance values (0.61 m/s min self-cleansing;
    IPC's table 3_Velocity_Limits also gives a general 3.0 m/s max) — pass
    explicit values if a different code's confirmed figures should be used.
    """
    if min_self_cleansing_m_s is None or max_velocity_m_s is None or not criteria_reference:
        raise MissingCodeDataError('Drainage velocity criteria','Supply reviewed limits/reference; pipe bore alone does not establish gravity-flow area')
    finite('minimum velocity',min_self_cleansing_m_s,minimum=0)
    finite('maximum velocity',max_velocity_m_s,positive=True)
    if min_self_cleansing_m_s>max_velocity_m_s: raise ValueError('Inverted velocity limits')
    v = velocity_from_flow(flow_lps, internal_diameter_mm, calc_id)
    v.calc_type = "drainage_velocity_check"
    if v.result_value < min_self_cleansing_m_s:
        v.status, v.notes = "WARNING", f"Below self-cleansing velocity ({min_self_cleansing_m_s} m/s) — risk of solids deposition."
    elif v.result_value > max_velocity_m_s:
        v.status, v.notes = "FAIL", f"Above general erosion/noise limit ({max_velocity_m_s} m/s)."
    else:
        v.status = "WARNING"
    v.required_value = max_velocity_m_s
    v.selected_value = v.result_value
    v.reference = criteria_reference
    v.notes=(v.notes or '')+' Full-bore velocity proxy only; partially full gravity hydraulics and self-cleansing require separate verification.'
    return v
