"""
database/load_confirmed_additions.py
----------------------------------------
Loads engineering data Ahmed independently verified (fetched primary
sources, recalculated coefficients, or confirmed/rejected candidate
values) that did NOT come from the Code_Data.zip workbooks. Kept as a
separate, explicit script — not folded into load_design_tables.py —
because its provenance (research paper, manufacturer course) differs
from the code-workbook ETL and deserves its own audit trail.

Each insertion below is traceable to Ahmed's own verification, dated
in the notes field, not to anything invented here. All SQL here is
parameterized (no string-built SQL literals) to avoid quoting bugs.
"""

from __future__ import annotations

from database.db import get_connection


def _upsert_design_table(conn, code_id, domain, table_name, description, reference, status):
    cur = conn.execute(
        """INSERT INTO design_tables (code_id, domain, table_name, description, reference, status)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(code_id, domain, table_name) DO UPDATE SET
             description=excluded.description, reference=excluded.reference, status=excluded.status
           RETURNING table_id""",
        (code_id, domain, table_name, description, reference, status),
    )
    table_id = cur.fetchone()["table_id"]
    conn.execute("DELETE FROM design_table_values WHERE table_id = ?", (table_id,))
    return table_id


def load_riyadh_rainfall_depth(conn) -> int:
    """
    Riyadh 24-hour design rainfall depth by return period.
    Source: Al-Saleh (1997) — Ahmed fetched the primary paper and
    independently recalculated the Gumbel-distribution predictions from
    its raw coefficients; his recalculation matched the paper exactly.

    The previously-circulated "DAR/CIBSE 2017" table was explicitly
    REJECTED: the report number traces to a real Riyadh Municipality
    document, but Ahmed found zero connection to CIBSE and no way to
    verify those specific depth numbers came from it. Not loaded.

    Resolves the single open item flagged in Section 0b(1) of
    docs/ARCHITECTURE.md.
    """
    description = (
        "Independently verified by Ahmed: fetched the primary paper and recalculated the "
        "Gumbel predictions from its raw coefficients, matching exactly. Resolves the base "
        "depth input that the SBC701 workbook's depth-duration ratios (Tab 8) needed. "
        "The candidate \"DAR/CIBSE 2017\" table was checked and explicitly rejected -- no "
        "verifiable link to CIBSE despite a real Riyadh Municipality report number."
    )
    table_id = _upsert_design_table(
        conn, "SAUDI_SBC_701", "storm", "Riyadh 24hr Design Rainfall Depth (Al-Saleh 1997)",
        description, "Al-Saleh (1997)", "POPULATED",
    )

    rows = [
        (2, 16.7, 18.3),
        (5, 23.9, 28.5),
        (10, 28.7, 35.2),
        (25, 34.8, 43.8),
        (50, 39.2, 50.1),
        (100, 43.7, 56.4),
    ]
    n = 0
    note = "Al-Saleh (1997), independently recalculated and verified by Ahmed (2026-09)."
    for return_period_yr, riyadh_station_mm, riyadh_old_airport_mm in rows:
        row_key = f"row_{return_period_yr:03d}"
        for col_key, val in [
            ("return_period_yr", return_period_yr),
            ("riyadh_station_mm", riyadh_station_mm),
            ("riyadh_old_airport_mm", riyadh_old_airport_mm),
        ]:
            conn.execute(
                """INSERT INTO design_table_values
                   (table_id, row_key, col_key, value_num, unit, source_classification, confidence, notes)
                   VALUES (?, ?, ?, ?, 'mm', 'PROJECT', 'CONFIRMED', ?)""",
                (table_id, row_key, col_key, val, note),
            )
            n += 1
    conn.commit()
    return n


def load_ppr_pn16_velocity(conn) -> int:
    """
    PPR-PN16 velocity limits -- manufacturer-confirmed (Aquatherm CE course),
    not code-text. Two DISTINCT limits, both confirmed real and NOT
    conflated: a general design velocity ceiling, and a separate (lower)
    circulation/return-loop limit.

    Explicitly NOT added, per Ahmed's verification: the "1.5-2.0 m/s best
    practice" and "4.57-6.10 m/s absolute limit" figures some sources cite
    -- Ahmed could not verify these and asked that they not be included.
    """
    description = (
        "Manufacturer-confirmed by Ahmed via Aquatherm's CE course material -- not code text. "
        "Two distinct, non-conflated limits: general design ceiling and a separate, lower "
        "circulation/return-loop limit. Unverified alternative figures (1.5-2.0 m/s "
        "\"best practice\", 4.57-6.10 m/s \"absolute limit\") were checked and deliberately "
        "NOT included."
    )
    table_id = _upsert_design_table(
        conn, "SAUDI_SBC_701", "water", "PPR-PN16 Velocity Limits (Aquatherm, manufacturer)",
        description, "Aquatherm CE course (manufacturer-published)", "POPULATED",
    )

    entries = [
        ("row_000", "General design velocity ceiling - PPR-PN16", 3.05, "m/s"),
        ("row_001", "Circulation/return-loop velocity limit - PPR-PN16", 0.5, "m/s"),
    ]
    n = 0
    for row_key, parameter, value, unit in entries:
        conn.execute(
            """INSERT INTO design_table_values (table_id, row_key, col_key, value_text, source_classification, confidence)
               VALUES (?, ?, 'parameter', ?, 'MANUFACTURER', 'CONFIRMED')""",
            (table_id, row_key, parameter),
        )
        conn.execute(
            """INSERT INTO design_table_values (table_id, row_key, col_key, value_num, unit, source_classification, confidence)
               VALUES (?, ?, 'value', ?, ?, 'MANUFACTURER', 'CONFIRMED')""",
            (table_id, row_key, value, unit),
        )
        n += 2
    conn.commit()
    return n


def record_confirmed_decisions(conn) -> None:
    """
    Documentation-only records for the three items where Ahmed's answer was
    "confirmed absent / keep the existing fallback" rather than new data:

    - SBC 701 velocity ceiling: confirmed absent from SBC's text (water-hammer
      control is qualitative there). Decision: keep the IPC fallback already
      supported by design_table_api.get_velocity_limit(allow_fallback_code=...).
    - SBC 701 Table 906 (vent stack sizing): not independently re-extractable
      (every mirror renders it as an image). Decision: use IPC's confirmed
      Table 906.1 (already loaded) via the same explicit-fallback pattern once
      calculations/vent.py is built (Phase 3) -- flagged "via code lineage,
      not independently verified for SBC".
    - SBC 701 / Egypt hot-water demand factors: not found for either code.
      Decision: IPC's ASPE/ASHRAE hospital figures (Tab 9) are final.

    No new numeric rows needed here -- decisions are recorded as their own
    design_tables marker rows so the rationale travels with the data instead
    of living only in chat history.
    """
    _upsert_design_table(
        conn, "SAUDI_SBC_701", "water", "3_Velocity_Limits [decision-record]",
        "DECISION (2026-09, Ahmed): SBC 701 text confirmed to have NO numeric velocity "
        "ceiling -- water-hammer control (Sec. 604.9) is qualitative only. Use the IPC "
        "fallback via get_velocity_limit(allow_fallback_code=\"IPC\"). No new data to load.",
        "SBC 701-2007 Sec. 604.9 (confirmed qualitative)", "CODE_DATA_REQUIRED",
    )
    _upsert_design_table(
        conn, "SAUDI_SBC_701", "vent", "7_Vent_Sizing [Table 906 decision-record]",
        "DECISION (2026-09, Ahmed): SBC 701 Table 906 not independently re-extractable "
        "(every available mirror renders it as an image, incl. 7 state-adopted IPC sites "
        "checked). Use IPC's confirmed Table 906.1 (already loaded, code_id=IPC) via an "
        "explicit fallback once calculations/vent.py is built (Phase 3) -- must be tagged "
        "\"via code lineage, not independently verified for SBC\", same pattern as the "
        "velocity-limit fallback.",
        "IPC Table 906.1 (fallback pending, not SBC-verified)", "CODE_DATA_REQUIRED",
    )

    row = conn.execute(
        """SELECT table_id, description FROM design_tables
           WHERE domain='hot_water' AND table_name LIKE '%9_Hot_Water_Basis%' AND code_id='IPC'
           LIMIT 1"""
    ).fetchone()
    if row:
        new_desc = (row["description"] or "") + (
            " | DECISION (2026-09, Ahmed): confirmed not found for SBC 701 or Egypt. "
            "IPC's ASPE/ASHRAE hospital figures (demand factor 0.25, storage factor 0.6) are final."
        )
        conn.execute("UPDATE design_tables SET description = ? WHERE table_id = ?", (new_desc, row["table_id"]))
    conn.commit()


def load_all_confirmed_additions(conn) -> dict:
    n_rain = load_riyadh_rainfall_depth(conn)
    n_ppr = load_ppr_pn16_velocity(conn)
    record_confirmed_decisions(conn)
    return {"riyadh_rainfall_values": n_rain, "ppr_pn16_values": n_ppr}


if __name__ == "__main__":
    conn = get_connection()
    summary = load_all_confirmed_additions(conn)
    print("Loaded confirmed additions:")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    conn.close()
