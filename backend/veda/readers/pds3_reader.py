"""Pure-Python PDS3 Label (.LBL) and Table (.TAB) reader for VEDA.

Designed without third-party PVL dependencies so it operates reliably in any
standard Python environment. Handles fixed-width and comma-delimited PDS3 ASCII
tables with column offset parsing, units extraction, and sentinel masking.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import numpy as np


@dataclass
class ColumnDef:
    name: str
    column_number: int
    start_byte: int  # 1-indexed
    bytes_count: int
    data_type: str = "ASCII_REAL"
    unit: str = ""
    invalid_constant: Optional[float] = None
    missing_constant: Optional[float] = None


@dataclass
class Pds3Table:
    label_path: str
    table_path: str
    metadata: Dict[str, Any]
    columns: Dict[str, np.ndarray]
    units: Dict[str, str]
    descriptions: Dict[str, str] = field(default_factory=dict)

    def series(self, name: str) -> Optional[np.ndarray]:
        """Case-insensitive column series lookup."""
        n_clean = name.strip().upper()
        for k, v in self.columns.items():
            if k.strip().upper() == n_clean:
                return v
        # Also check partial matching (e.g. 'TEMPERATURE' inside 'TEMPERATURE (MEDIUM...)')
        for k, v in self.columns.items():
            if n_clean in k.strip().upper():
                return v
        return None


def parse_pds3_label(label_text: str) -> Tuple[Dict[str, Any], List[ColumnDef]]:
    """Parse key-value pairs and COLUMN objects from a PDS3 label."""
    metadata: Dict[str, Any] = {}
    columns: List[ColumnDef] = []

    # Clean lines and handle comments
    lines = label_text.splitlines()
    clean_lines = []
    in_comment = False
    for line in lines:
        l = line.strip()
        if not l:
            continue
        if "/*" in l and "*/" in l:
            l = re.sub(r'/\*.*?\*/', '', l).strip()
        elif "/*" in l:
            in_comment = True
            l = l[:l.find("/*")].strip()
        elif "*/" in l:
            in_comment = False
            l = l[l.find("*/") + 2:].strip()
        elif in_comment:
            continue
        if l:
            clean_lines.append(l)

    # State machine to capture global keywords and COLUMN blocks
    curr_obj = None
    curr_col: Dict[str, Any] = {}

    for line in clean_lines:
        if "=" not in line:
            continue
        parts = line.split("=", 1)
        key = parts[0].strip().upper()
        val = parts[1].strip()

        # Clean value quotes and angle units e.g. "6051.8 <km>"
        if val.startswith('"') and val.endswith('"'):
            val_clean = val[1:-1]
        elif val.startswith("'") and val.endswith("'"):
            val_clean = val[1:-1]
        else:
            val_clean = val

        if key == "OBJECT":
            curr_obj = val_clean.upper()
            if curr_obj == "COLUMN":
                curr_col = {}
        elif key == "END_OBJECT":
            if val_clean.upper() == "COLUMN" and curr_col:
                col_name = curr_col.get("NAME", f"COL_{len(columns)+1}")
                c_num = int(curr_col.get("COLUMN_NUMBER", len(columns)+1))
                s_byte = int(curr_col.get("START_BYTE", 1))
                b_count = int(curr_col.get("BYTES", 10))
                dtype = curr_col.get("DATA_TYPE", "ASCII_REAL")
                unit = curr_col.get("UNIT", "")
                inv = None
                if "INVALID_CONSTANT" in curr_col:
                    try:
                        inv = float(curr_col["INVALID_CONSTANT"])
                    except (ValueError, TypeError):
                        pass
                miss = None
                if "MISSING_CONSTANT" in curr_col:
                    try:
                        miss = float(curr_col["MISSING_CONSTANT"])
                    except (ValueError, TypeError):
                        pass

                columns.append(ColumnDef(
                    name=col_name,
                    column_number=c_num,
                    start_byte=s_byte,
                    bytes_count=b_count,
                    data_type=dtype,
                    unit=unit,
                    invalid_constant=inv,
                    missing_constant=miss,
                ))
                curr_col = {}
            curr_obj = None
        else:
            if curr_obj == "COLUMN":
                curr_col[key] = val_clean
            else:
                metadata[key] = val_clean

    return metadata, columns


def read_pds3_table(table_or_label_path: str) -> Pds3Table:
    """Read a PDS3 label (.lbl) and its corresponding data table (.tab)."""
    p = Path(table_or_label_path)
    if p.suffix.lower() == ".tab":
        lbl_p = p.with_suffix(".lbl")
        if not lbl_p.exists():
            lbl_p = p.with_suffix(".LBL")
        tab_p = p
    else:
        lbl_p = p
        tab_p = p.with_suffix(".tab")
        if not tab_p.exists():
            tab_p = p.with_suffix(".TAB")

    if not lbl_p.exists():
        raise FileNotFoundError(f"PDS3 label not found at {lbl_p}")
    if not tab_p.exists():
        raise FileNotFoundError(f"PDS3 table not found at {tab_p}")

    lbl_text = lbl_p.read_text(encoding="utf-8", errors="replace")
    metadata, col_defs = parse_pds3_label(lbl_text)

    # Read the table file lines
    with tab_p.open("r", encoding="utf-8", errors="replace") as f:
        lines = [ln for ln in f.read().splitlines() if ln.strip()]

    n_rows = len(lines)
    columns_data: Dict[str, np.ndarray] = {}
    units_dict: Dict[str, str] = {}

    # Check if comma-delimited or fixed-width
    first_line = lines[0] if lines else ""
    is_csv = "," in first_line and len(first_line.split(",")) >= len(col_defs)

    if is_csv:
        import csv
        reader = csv.reader(lines)
        raw_rows = list(reader)
        for idx, c in enumerate(col_defs):
            c_idx = c.column_number - 1 if 0 <= c.column_number - 1 < len(raw_rows[0]) else idx
            arr = np.full(n_rows, np.nan, dtype=np.float64)
            for r_i, r_data in enumerate(raw_rows):
                if c_idx < len(r_data):
                    val_s = r_data[c_idx].strip().strip('"').strip("'")
                    try:
                        f_val = float(val_s)
                        if c.invalid_constant is not None and abs(f_val - c.invalid_constant) < 1e-4:
                            continue
                        if c.missing_constant is not None and abs(f_val - c.missing_constant) < 1e-4:
                            continue
                        if abs(f_val - (-999.0)) < 1e-3 or abs(f_val - (-9999.0)) < 1e-3:
                            continue
                        arr[r_i] = f_val
                    except ValueError:
                        pass
            columns_data[c.name] = arr
            units_dict[c.name] = c.unit
    else:
        # Fixed-width column slicing by START_BYTE and BYTES
        for c in col_defs:
            arr = np.full(n_rows, np.nan, dtype=np.float64)
            s_idx = c.start_byte - 1
            e_idx = s_idx + c.bytes_count

            for r_i, line in enumerate(lines):
                if s_idx < len(line):
                    chunk = line[s_idx:min(e_idx, len(line))].strip().strip(',').strip('"').strip("'")
                    if chunk:
                        try:
                            f_val = float(chunk)
                            if c.invalid_constant is not None and abs(f_val - c.invalid_constant) < 1e-4:
                                continue
                            if c.missing_constant is not None and abs(f_val - c.missing_constant) < 1e-4:
                                continue
                            if abs(f_val - (-999.0)) < 1e-3 or abs(f_val - (-9999.0)) < 1e-3:
                                continue
                            arr[r_i] = f_val
                        except ValueError:
                            pass
            columns_data[c.name] = arr
            units_dict[c.name] = c.unit

    return Pds3Table(
        label_path=str(lbl_p),
        table_path=str(tab_p),
        metadata=metadata,
        columns=columns_data,
        units=units_dict,
    )
