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

from database.design_table_api import get_table_records, get_min_slope
from calculations.hydraulics import velocity_from_flow
from models import CalculationResult, MissingCodeDataError

# context -> substrings to look for in the drainage-sizing table's column names.
# First matching column wins. Extend per-code as new column vocabularies show up.
CONTEXT_COLUMN_HINTS = {
    "horizontal_branch": ["max_dfu_horiz_branch", "horiz_branch", "drainage_max_units_horiz"],
    "stack_le3_branch_intervals": ["max_dfu_stack_le3_bi", "drainage_max_units_vertical"],
    "stack_gt3_branch_intervals": ["max_dfu_stack_gt3_bi"],
    "branch_interval": ["max_dfu_per_branch_interval"],
}

PIPE_SIZE_COLUMN_HINTS = ["pipe_mm", "pipe_size_mm"]


def size_drainage_pipe(conn, code_id: str, total_dfu: float, context: str, calc_id: str) -> CalculationResult:
    """
    Selects the smallest pipe size whose max-DFU capacity (for the given
    context) is >= total_dfu. Raises MissingCodeDataError if the code's
    drainage-sizing table doesn't have a column for this context, or if
    total_dfu exceeds every size in the table (needs engineer judgement,
    not a silent largest-size guess).
    """
    if context not in CONTEXT_COLUMN_HINTS:
        raise ValueError(f"Unknown context '{context}'. Valid: {list(CONTEXT_COLUMN_HINTS)}")

    records = get_table_records(conn, code_id, "drainage", "5_Drainage_Sizing")
    if not records:
        raise MissingCodeDataError(what="Drainage sizing table", where=f"code={code_id}")

    size_col = next((c for c in PIPE_SIZE_COLUMN_HINTS if any(c in rec for rec in records)), None)
    dfu_col = next((h for h in CONTEXT_COLUMN_HINTS[context] if any(h in rec for rec in records)), None)
    if size_col is None or dfu_col is None:
        raise MissingCodeDataError(
            what=f"Drainage sizing column for context='{context}'",
            where=f"code={code_id}, table=5_Drainage_Sizing (columns seen: "
                  f"{sorted(set(k for r in records for k in r if not k.startswith('_')))})",
        )

    candidates = []
    for rec in records:
        size_val = rec.get(size_col, (None, None, None))
        dfu_val = rec.get(dfu_col, (None, None, None))
        if size_val[0] is None or dfu_val[0] is None:
            continue  # non-numeric band ("per design") -> not a candidate, not a silent match
        candidates.append((size_val[0], dfu_val[0], dfu_val[2]))
    candidates.sort(key=lambda c: c[0])

    for pipe_mm, max_dfu, confidence in candidates:
        if total_dfu <= max_dfu:
            return CalculationResult(
                calc_id=calc_id,
                calc_type="drainage_pipe_sizing",
                formula=f"Select smallest pipe where {dfu_col} >= total_dfu",
                inputs={"total_dfu": (total_dfu, "DFU"), "context": (context, "-")},
                intermediate={"candidates_checked": len(candidates)},
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
                             min_self_cleansing_m_s: float = 0.61,
                             max_velocity_m_s: float = 3.0) -> CalculationResult:
    """
    Self-cleansing / erosion-limit check for gravity drainage. Defaults are
    IPC's own confirmed general-guidance values (0.61 m/s min self-cleansing;
    IPC's table 3_Velocity_Limits also gives a general 3.0 m/s max) — pass
    explicit values if a different code's confirmed figures should be used.
    """
    v = velocity_from_flow(flow_lps, internal_diameter_mm, calc_id)
    v.calc_type = "drainage_velocity_check"
    if v.result_value < min_self_cleansing_m_s:
        v.status, v.notes = "WARNING", f"Below self-cleansing velocity ({min_self_cleansing_m_s} m/s) — risk of solids deposition."
    elif v.result_value > max_velocity_m_s:
        v.status, v.notes = "FAIL", f"Above general erosion/noise limit ({max_velocity_m_s} m/s)."
    else:
        v.status = "PASS"
    v.required_value = max_velocity_m_s
    v.selected_value = v.result_value
    v.reference = "IPC:3_Velocity_Limits general guidance (self-cleansing min / erosion max)"
    return v
