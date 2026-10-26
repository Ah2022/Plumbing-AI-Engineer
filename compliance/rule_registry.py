"""
compliance/rule_registry.py
-----------------------------
The supplied rule JSON gives each rule a *prose* condition
("Static pressure ... is above the code pressure threshold"), not
executable logic. This module is where prose becomes code: each
rule_id that CAN be evaluated with data the engine actually has is
registered here with a predicate function.

Design principle (per project spec section 2 & 34):
A rule with no registered predicate is NEVER silently passed. The
compliance engine reports it as NOT_EVALUATED — never PASS, never FAIL.

Three predicate classes are implemented so far:

1. NUMERIC THRESHOLD  — rule carries a `parameters_json` value the
   project value can be compared against directly (e.g. IPC-W-002).
2. DATA-PRESENCE       — rule requires a design-basis input to exist
   and be APPROVED before sizing can proceed (e.g. rainfall intensity
   for storm sizing, present in all four codes as *-S-001/002).
3. SIZING-JUSTIFICATION — rule requires that a calculation for the
   relevant domain exists and was NOT produced from an ASSUMED value
   (e.g. drainage/water sizing "not justified by tables" rules).

Everything else (cross-connection detection, trap-venting adequacy,
S-trap detection, AAV permissibility, secondary-drain presence, etc.)
needs actual pipe/fixture TOPOLOGY from the Revit model — that's Phase
7 (BIM extraction). Those rules stay unregistered on purpose until
that data source exists; do not add fake predicates for them.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable, Optional


@dataclass
class CheckResult:
    status: str            # 'PASS' | 'FAIL' | 'WARNING' | 'NOT_EVALUATED'
    actual_value: Optional[str] = None
    required_value: Optional[str] = None
    reason: Optional[str] = None


# --- Predicate implementations -----------------------------------------

def check_static_pressure_threshold(conn, project_id: int, rule) -> CheckResult:
    """IPC-W-002: static pressure must not exceed the rule's threshold
    unless an approved pressure-reducing arrangement is on record."""
    params = json.loads(rule["parameters_json"]) if rule["parameters_json"] else {}
    threshold_psi = params.get("static_pressure_threshold_psi")
    if threshold_psi is None:
        return CheckResult("NOT_EVALUATED", reason="Rule has no numeric threshold.")

    row = conn.execute(
        """SELECT item_value, status FROM design_basis_items
           WHERE project_id = ? AND item_key = 'static_pressure_psi'""",
        (project_id,),
    ).fetchone()
    if row is None:
        return CheckResult("NOT_EVALUATED", required_value=f"<= {threshold_psi} psi",
                            reason="Project static pressure not entered yet.")

    actual = float(row["item_value"])
    if actual <= threshold_psi:
        return CheckResult("PASS", actual_value=f"{actual} psi", required_value=f"<= {threshold_psi} psi")

    # Above threshold — check whether a PRV arrangement is on record.
    prv_row = conn.execute(
        """SELECT item_value FROM design_basis_items
           WHERE project_id = ? AND item_key = 'pressure_reducing_valve_provided'""",
        (project_id,),
    ).fetchone()
    if prv_row and prv_row["item_value"].strip().lower() in ("yes", "true", "1"):
        return CheckResult("PASS", actual_value=f"{actual} psi", required_value=f"<= {threshold_psi} psi",
                            reason="Above threshold but PRV arrangement is on record.")
    return CheckResult("FAIL", actual_value=f"{actual} psi", required_value=f"<= {threshold_psi} psi",
                        reason="Static pressure exceeds threshold and no PRV arrangement is recorded.")


def _check_design_basis_present(conn, project_id: int, item_key: str, label: str) -> CheckResult:
    row = conn.execute(
        """SELECT item_value, status FROM design_basis_items
           WHERE project_id = ? AND item_key = ?""",
        (project_id, item_key),
    ).fetchone()
    if row is None:
        return CheckResult("FAIL", reason=f"{label} has not been entered for this project.")
    if row["status"] != "APPROVED":
        return CheckResult("WARNING", actual_value=row["item_value"],
                            reason=f"{label} is entered but not yet APPROVED by the engineer.")
    return CheckResult("PASS", actual_value=row["item_value"])


def check_rainfall_design_data_present(conn, project_id: int, rule) -> CheckResult:
    """*-S-001/002: storm sizing must not proceed without an approved rainfall/design-intensity input."""
    return _check_design_basis_present(conn, project_id, "rainfall_intensity_mm_hr", "Rainfall design intensity")


def _check_sizing_justified(conn, project_id: int, calc_type: str, label: str) -> CheckResult:
    rows = conn.execute(
        """SELECT status FROM calculations WHERE project_id = ? AND calc_type = ?""",
        (project_id, calc_type),
    ).fetchall()
    if not rows:
        return CheckResult("FAIL", reason=f"No {label} calculation exists for this project yet.")
    if any(r["status"] == "ASSUMED" for r in rows):
        return CheckResult("WARNING", reason=f"{label} sizing relies on an unapproved ASSUMED input.")
    if any(r["status"] == "MISSING_DATA" for r in rows):
        return CheckResult("FAIL", reason=f"{label} sizing is blocked on missing code/design-table data.")
    return CheckResult("PASS", reason=f"{label} sizing is backed by recorded, non-assumed calculations.")


def check_drainage_sizing_justified(conn, project_id: int, rule) -> CheckResult:
    """*-D-001 family: drainage sizing must be backed by DFU/load calculations, not asserted."""
    return _check_sizing_justified(conn, project_id, "drainage_pipe_sizing", "Drainage pipe")


def check_water_sizing_justified(conn, project_id: int, rule) -> CheckResult:
    """UPC-W-002 / SBC701-W-002: water distribution sizing must be backed by demand/pressure calcs."""
    return _check_sizing_justified(conn, project_id, "cold_water_pipe_sizing", "Cold water pipe")


# --- Registry -------------------------------------------------------------

PredicateFn = Callable[[object, int, "sqlite3.Row"], CheckResult]

RULE_PREDICATES: dict[str, PredicateFn] = {
    "IPC-W-002": check_static_pressure_threshold,

    "IPC-S-001": check_rainfall_design_data_present,
    "UPC-S-002": check_rainfall_design_data_present,
    "EGY-S-001": check_rainfall_design_data_present,
    "SBC701-S-001": check_rainfall_design_data_present,

    "IPC-D-001": check_drainage_sizing_justified,
    "UPC-D-001": check_drainage_sizing_justified,
    "EGY-D-002": check_drainage_sizing_justified,
    "SBC701-D-001": check_drainage_sizing_justified,

    "UPC-W-002": check_water_sizing_justified,
    "SBC701-W-002": check_water_sizing_justified,
}


def sync_predicate_flags(conn) -> int:
    """Set has_predicate=1 in code_rules for every rule_id registered above. Returns count updated."""
    updated = 0
    for rule_id in RULE_PREDICATES:
        cur = conn.execute("UPDATE code_rules SET has_predicate = 1 WHERE rule_id = ?", (rule_id,))
        updated += cur.rowcount
    conn.execute(
        "UPDATE code_rules SET has_predicate = 0 WHERE rule_id NOT IN ({})".format(
            ",".join("?" * len(RULE_PREDICATES))
        ),
        list(RULE_PREDICATES.keys()),
    )
    conn.commit()
    return updated


if __name__ == "__main__":
    from database.db import get_connection

    conn = get_connection()
    n = sync_predicate_flags(conn)
    total = conn.execute("SELECT COUNT(*) FROM code_rules").fetchone()[0]
    print(f"{n} of {total} rules have an executable predicate registered.")
    unregistered = conn.execute(
        "SELECT rule_id, severity, reference FROM code_rules WHERE has_predicate = 0 ORDER BY rule_id"
    ).fetchall()
    print(f"\n{len(unregistered)} rules require BIM topology data or design-table data not yet modeled "
          f"(will report NOT_EVALUATED, never a false PASS):")
    for r in unregistered:
        print(f"  {r['rule_id']:14s} [{r['severity']:7s}] {r['reference']}")
    conn.close()
