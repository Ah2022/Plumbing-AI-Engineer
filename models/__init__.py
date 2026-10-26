"""
models/__init__.py
--------------------
Shared dataclasses used across the calculation engine. The single most
important one is CalculationResult: every calculation in the system
(cold water, hot water, drainage, vent, storm, tanks, pumps) must
return one of these so the chain

    INPUT -> DESIGN CRITERIA -> CODE RULE -> FORMULA -> CALCULATION
    -> RESULT -> PASS/FAIL

(project spec, section 1) is always auditable, never a black box
(section 2).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CalculationResult:
    calc_id: str
    calc_type: str
    formula: str                      # human-readable formula, e.g. "hf = f * (L/D) * (V^2 / 2g)"
    inputs: dict                      # {name: (value, unit)}
    intermediate: dict                # named intermediate values, e.g. {"velocity_m_s": 1.8}
    result_value: Optional[float]
    result_unit: Optional[str]
    required_value: Optional[float] = None
    selected_value: Optional[float] = None
    status: str = "CALCULATED_NOT_APPROVED"   # PASS | FAIL | WARNING | ASSUMED | MISSING_DATA | CALCULATED_NOT_APPROVED
    reference: Optional[str] = None           # code section / table, or "Textbook hydraulics (public domain)"
    code_rule_id: Optional[str] = None
    notes: Optional[str] = None

    def as_row(self, project_id: int, target_type: str = None, target_id: str = None) -> dict:
        """Flatten for insertion into the `calculations` table."""
        import json
        return {
            "calc_id": self.calc_id,
            "project_id": project_id,
            "calc_type": self.calc_type,
            "target_type": target_type,
            "target_id": target_id,
            "formula": self.formula,
            "inputs_json": json.dumps(self.inputs),
            "intermediate_json": json.dumps(self.intermediate),
            "result_value": self.result_value,
            "result_unit": self.result_unit,
            "required_value": self.required_value,
            "selected_value": self.selected_value,
            "status": self.status,
            "code_rule_id": self.code_rule_id,
            "reference": self.reference,
        }


class MissingCodeDataError(Exception):
    """Raised when a calculation needs a code-sourced numeric value
    (velocity limit, FU-demand table, DFU table, roughness value, etc.)
    that has not yet been supplied in design_tables / design_table_values.

    Per project spec section 30: the system must STOP the calculation
    and report MISSING CODE DATA rather than invent a value."""

    def __init__(self, what: str, where: str = ""):
        self.what = what
        self.where = where
        super().__init__(f"MISSING CODE DATA: {what}" + (f" ({where})" if where else ""))
