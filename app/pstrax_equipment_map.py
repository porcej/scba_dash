"""Pure PSTrax API row -> structured equipment fields (no Flask/db imports)."""

from __future__ import annotations

import json
import re
from typing import Any, Optional

from bs4 import BeautifulSoup

_MDY = re.compile(r"\b(\d{1,2}/\d{1,2}/\d{4})\b")
_MDY_ONLY = re.compile(r"^\s*(\d{1,2}/\d{1,2}/\d{4})\s*$")


def _mdy_from_display(display_val: Any) -> Optional[str]:
    if display_val is None or display_val == "":
        return None
    text = BeautifulSoup(str(display_val), "html.parser").get_text().strip()
    m = _MDY.search(text)
    return m.group(1) if m else None


def _mdy_from_nested(nested: Any, sort_key: str) -> Optional[str]:
    if not isinstance(nested, dict):
        return None
    sort_v = nested.get(sort_key)
    if isinstance(sort_v, str) and _MDY_ONLY.match(sort_v):
        return sort_v.strip()
    disp = nested.get("display")
    d = _mdy_from_display(disp)
    if d:
        return d
    if isinstance(sort_v, str) and (m := _MDY.search(sort_v)):
        return m.group(1)
    return None


def _safe_str(v: Any, max_len: int = 512) -> str:
    if v is None:
        return ""
    s = str(v).strip()
    return s[:max_len] if len(s) > max_len else s


def _nested_str(nested: Any, key: str) -> str:
    if not isinstance(nested, dict):
        return ""
    v = nested.get(key)
    if v is None:
        return ""
    return str(v)


def equipment_kwargs_from_pstrax(item: dict) -> dict:
    """Column kwargs for Equipment (excludes gearid, updated_at)."""
    exp = item.get("expdate") or {}
    nh = item.get("nexthydro") or {}
    nf = item.get("nextflow") or {}
    ll = item.get("lastloglocation") or {}
    nd = item.get("nextdue") or {}
    lb = item.get("lastlogby")
    if lb is not None and not isinstance(lb, (str, int, float)):
        lastlogby_json = json.dumps(lb)
    elif lb is not None:
        lastlogby_json = str(lb)
    else:
        lastlogby_json = None

    exp_date = _mdy_from_nested(exp, "expsort")
    next_hydro = _mdy_from_nested(nh, "hydrosort")
    next_flow = _mdy_from_nested(nf, "flowsort")
    next_due = _mdy_from_nested(nd, "nxtsort") or _mdy_from_display(nd.get("display"))

    gtid = item.get("geartypeid")
    cuid = item.get("currentuserid")

    return {
        "dt_row_id": _safe_str(item.get("DT_RowId"), 64) or None,
        "geartypeid": int(gtid) if gtid is not None and str(gtid).strip() != "" else None,
        "geartype": _safe_str(item.get("geartype"), 128) or None,
        "internalid": _safe_str(item.get("internalid"), 64) or None,
        "serial": _safe_str(item.get("serial"), 128) or None,
        "mfr": _safe_str(item.get("mfr"), 128) or None,
        "model": _safe_str(item.get("model"), 255) or None,
        "size": _safe_str(item.get("size"), 64) or None,
        "cost": _safe_str(item.get("cost"), 64) or None,
        "status": _safe_str(item.get("status"), 64) or None,
        "currentuserid": int(cuid) if cuid is not None and str(cuid).strip() != "" else None,
        "currentuser": _safe_str(item.get("currentuser"), 128) or None,
        "description": _safe_str(item.get("description"), 512) or None,
        "custom1": _safe_str(item.get("custom1"), 512) or None,
        "custom2": _safe_str(item.get("custom2"), 512) or None,
        "custom3": _safe_str(item.get("custom3"), 512) or None,
        "condition": _safe_str(item.get("condition"), 64) or None,
        "mfrdate": _safe_str(item.get("mfrdate"), 32) or None,
        "srvdate": _safe_str(item.get("srvdate"), 32) or None,
        "exp_date": exp_date,
        "expdate_class": _safe_str(exp.get("expclass"), 128) or None,
        "expdate_display_raw": (_nested_str(exp, "display") or None),
        "nexthydro_display": (_nested_str(nh, "display") or None),
        "next_hydro": next_hydro,
        "nexthydro_class": _safe_str(nh.get("hydroclass"), 128) or None,
        "nextflow_display": (_nested_str(nf, "display") or None),
        "next_flow": next_flow,
        "nextflow_class": _safe_str(nf.get("flowclass"), 128) or None,
        "lastloglocation_display": (_nested_str(ll, "display") or None),
        "lastloglocation_logsort": (
            str(ll["logsort"]) if ll.get("logsort") is not None else None
        ),
        "lastlogby_json": lastlogby_json,
        "nextdue_display": (_nested_str(nd, "display") or None),
        "next_due": next_due,
        "nextdue_class": _safe_str(nd.get("nxtclass"), 128) or None,
    }
