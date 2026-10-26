"""
database/load_design_tables.py
---------------------------------
Loads the numeric design-table workbooks (fixture units, demand
conversion, velocity limits, min pipe size, drainage sizing, min slope,
vent sizing, rainfall intensity, hot-water basis, material roughness)
into `design_tables` / `design_table_values`.

Each workbook sheet (except README) is split into one or more BLOCKS,
separated by fully-blank rows. A block is recognized as a TABLE if it
contains a header row (>=2 short, non-prose cells); otherwise it is
treated as a caveat/GAP note attached to the domain's `design_tables`
description (no fabricated table is created for a documented gap).

Row-level CONFIDENCE is read directly from the workbook's own cell
fill color — the source files use light amber (FFF2CC family) to mean
"flagged: confirm before final sign-off", matching each workbook's own
README color-code legend. This is Ahmed's own annotation, preserved
as-is, not re-derived.
"""

from __future__ import annotations

import re
from pathlib import Path

import openpyxl

from database.db import get_connection

DATA_DIR = Path(__file__).parent / "code_design_data"  # xlsx files copied here

FILE_TO_CODE = {
    "IPC_Plumbing_Design_Data.xlsx": "IPC",
    "UPC_Plumbing_Design_Data.xlsx": "UPC",
    "BS_EN_Plumbing_Design_Data.xlsx": "BS_EN",
    "Egyptian_Plumbing_Design_Data.xlsx": "EGYPT_LOCAL",
    "SBC701_Saudi_Plumbing_Design_Data.xlsx": "SAUDI_SBC_701",
}

SHEET_TO_DOMAIN = {
    "1_Fixture_Units": "water",
    "2_Demand_Conversion": "water",
    "3_Velocity_Limits": "water",
    "4_Min_Pipe_Size": "water",
    "5_Drainage_Sizing": "drainage",
    "6_Min_Slope": "drainage",
    "7_Vent_Sizing": "vent",
    "8_Rainfall_Intensity": "storm",
    "9_Hot_Water_Basis": "hot_water",
    "10_Material_Roughness": "water",
}

FLAGGED_FILL_PREFIXES = ("00FFF2CC", "FFFFF2CC", "00FFFF00", "FFFFFF00")  # amber / yellow family


def _is_blank_row(row) -> bool:
    return all(c.value is None for c in row)


def _is_header_row(row) -> bool:
    """A header row: >=2 non-null cells, all short strings, none look like prose."""
    vals = [c.value for c in row if c.value is not None]
    if len(vals) < 2:
        return False
    for v in vals:
        if not isinstance(v, str):
            return False
        if len(v) > 40 or v.rstrip().endswith((".", ":")) or "  " in v:
            return False
    return True


def _row_confidence(row) -> str:
    for cell in row:
        if cell.value is None:
            continue
        fill = cell.fill
        rgb = fill.fgColor.rgb if fill and fill.fgColor else None
        if isinstance(rgb, str) and rgb.upper() in [p.upper() for p in FLAGGED_FILL_PREFIXES]:
            return "FLAGGED"
    return "CONFIRMED"


def _split_blocks(ws):
    """Yield lists of openpyxl Cell rows, split on fully-blank rows."""
    block = []
    for row in ws.iter_rows():
        if _is_blank_row(row):
            if block:
                yield block
                block = []
        else:
            block.append(row)
    if block:
        yield block


def _parse_value(raw):
    """Return (value_num, value_text) — numeric if it parses cleanly, else text."""
    if raw is None:
        return None, None
    if isinstance(raw, (int, float)):
        return float(raw), None
    s = str(raw).strip()
    # Reject ranges like "1.2-2.4" and non-numeric labels as value_num
    if re.fullmatch(r"-?\d+(\.\d+)?", s):
        return float(s), None
    return None, s


def parse_workbook(path: Path, code_id: str) -> dict:
    """
    Returns {domain: {sheet_name: {"tables": [...], "gap_notes": [...]}}}
    where each table dict = {name, reference, notes, rows: [ {row_key, cells: {col: (val_num,val_text,unit,confidence)} } ]}
    """
    wb = openpyxl.load_workbook(path, data_only=True)
    result = {}

    for sheet_name in wb.sheetnames:
        if sheet_name == "README":
            continue
        domain = SHEET_TO_DOMAIN.get(sheet_name, "water")
        ws = wb[sheet_name]
        blocks = list(_split_blocks(ws))

        tables = []
        gap_notes = []

        for block in blocks:
            header_idx = None
            for i, row in enumerate(block):
                if _is_header_row(row):
                    header_idx = i
                    break

            if header_idx is None:
                # No table found in this block -> caveat/GAP note only.
                text = " ".join(
                    str(c.value) for c in block[0] if isinstance(c.value, str)
                )
                if text:
                    gap_notes.append(text)
                continue

            # (real GAP filtering happens in load_workbook_into_db / __main__ reporting,
            #  not here — every note is kept so nothing is silently discarded)

            header_row = block[header_idx]
            headers = [c.value for c in header_row if c.value is not None]

            # Table title/reference = last prose line immediately before the header
            # (skip the very first line of the sheet if it's the sheet's own title).
            # Disambiguated with the header signature so multiple tables in one
            # sheet (e.g. Table 909/911/912/913 all in 7_Vent_Sizing) never collide.
            prelude = block[:header_idx]
            title_candidates = [
                " ".join(str(c.value) for c in r if c.value is not None)
                for r in prelude
                if any(c.value is not None for c in r)
            ]
            header_sig = "+".join(str(h) for h in headers if h is not None)[:60]
            base_ref = title_candidates[-1] if title_candidates else sheet_name
            table_ref = f"{base_ref} [{header_sig}]"
            notes = " | ".join(title_candidates[:-1]) if len(title_candidates) > 1 else None

            data_rows = block[header_idx + 1:]
            rows_out = []
            for r_i, row in enumerate(data_rows):
                cells = {col: c for col, c in zip(headers, row)}
                if all(c.value is None for c in cells.values()):
                    continue
                confidence = _row_confidence(row)
                row_key = f"row_{r_i:03d}"
                cell_out = {}
                for col_name, cell in cells.items():
                    val_num, val_text = _parse_value(cell.value)
                    if val_num is None and val_text is None:
                        continue
                    cell_out[col_name] = (val_num, val_text, confidence)
                if cell_out:
                    rows_out.append({"row_key": row_key, "cells": cell_out})

            tables.append({
                "name": table_ref,
                "reference": table_ref,
                "notes": notes,
                "headers": headers,
                "rows": rows_out,
            })

        result.setdefault(domain, {})[sheet_name] = {"tables": tables, "gap_notes": gap_notes}

    return result


def load_workbook_into_db(conn, path: Path, code_id: str) -> dict:
    """Parse one workbook and write it into design_tables / design_table_values. Returns a summary."""
    parsed = parse_workbook(path, code_id)
    summary = {"tables_loaded": 0, "rows_loaded": 0, "flagged_rows": 0, "gaps": []}

    for domain, sheets in parsed.items():
        for sheet_name, sheet_data in sheets.items():
            for gap in sheet_data["gap_notes"]:
                summary["gaps"].append({"domain": domain, "sheet": sheet_name, "note": gap})

            for table in sheet_data["tables"]:
                any_flagged = any(
                    conf == "FLAGGED"
                    for row in table["rows"]
                    for (_, _, conf) in row["cells"].values()
                )
                status = "PARTIAL" if any_flagged else "POPULATED"

                cur = conn.execute(
                    """INSERT INTO design_tables (code_id, domain, table_name, description, reference, status)
                       VALUES (?, ?, ?, ?, ?, ?)
                       ON CONFLICT(code_id, domain, table_name) DO UPDATE SET
                         description=excluded.description, reference=excluded.reference, status=excluded.status
                       RETURNING table_id
                    """,
                    (code_id, domain, table["name"][:200], table["notes"], table["reference"], status),
                )
                table_id = cur.fetchone()["table_id"]
                conn.execute("DELETE FROM design_table_values WHERE table_id = ?", (table_id,))

                summary["tables_loaded"] += 1
                for row in table["rows"]:
                    for col_name, (val_num, val_text, confidence) in row["cells"].items():
                        conn.execute(
                            """INSERT INTO design_table_values
                               (table_id, row_key, col_key, value_num, value_text, unit,
                                source_classification, confidence, notes)
                               VALUES (?, ?, ?, ?, ?, NULL, 'CODE', ?, NULL)""",
                            (table_id, row["row_key"], str(col_name), val_num, val_text, confidence),
                        )
                        summary["rows_loaded"] += 1
                        if confidence == "FLAGGED":
                            summary["flagged_rows"] += 1
    conn.commit()
    return summary


def load_all_workbooks(conn, data_dir: Path = DATA_DIR) -> dict:
    overall = {}
    for fname, code_id in FILE_TO_CODE.items():
        path = data_dir / fname
        if not path.exists():
            overall[code_id] = {"error": f"file not found: {path}"}
            continue
        # Ensure the code exists (BS_EN is new — not in the original rules ZIP)
        conn.execute(
            "INSERT OR IGNORE INTO codes (code_id, code_name, jurisdiction) VALUES (?, ?, ?)",
            (code_id, code_id, None),
        )
        overall[code_id] = load_workbook_into_db(conn, path, code_id)
    conn.commit()
    return overall


def _is_real_gap(note: str) -> bool:
    """Filter the parsed notes down to genuine, actionable caveats — not just
    section titles/descriptions that happened to land in their own block."""
    n = note.upper()
    return n.startswith("GAP") or "DO NOT USE" in n or "NOT FOUND" in n or "WAS NOT FOUND" in n


if __name__ == "__main__":
    conn = get_connection()
    results = load_all_workbooks(conn)
    for code_id, summary in results.items():
        print(f"\n=== {code_id} ===")
        if "error" in summary:
            print(" ", summary["error"])
            continue
        print(f"  tables loaded : {summary['tables_loaded']}")
        print(f"  values loaded : {summary['rows_loaded']}  (flagged: {summary['flagged_rows']})")
        real_gaps = [g for g in summary["gaps"] if _is_real_gap(g["note"])]
        if real_gaps:
            print(f"  GENUINE GAPS ({len(real_gaps)} of {len(summary['gaps'])} notes):")
            for g in real_gaps:
                print(f"    [{g['domain']}/{g['sheet']}] {g['note'][:160]}")
    conn.close()
