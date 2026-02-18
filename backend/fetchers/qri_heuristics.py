import re
from typing import Dict, Optional, Tuple


def normalize_qri(qri: str) -> Tuple[str, Optional[str]]:
    if qri is None:
        return "", None
    original = str(qri)
    cleaned = " ".join(original.split())
    if cleaned != original:
        return cleaned, original
    return cleaned, None


def extract_db_group(qri: str) -> Optional[str]:
    if not qri:
        return None
    m = re.match(r"qri:db:([^:/]+)://", qri, re.I)
    if not m:
        return None
    return f"db:{m.group(1).lower()}"


def infer_group_from_label(label: str) -> Optional[str]:
    if not label:
        return None
    m = re.match(r"`?([^`\.]+)`?\.[^\.]+", label.strip())
    if m:
        return m.group(1)
    return None


def derive_type_group_layer(qri: str, label: str, metadata: Dict) -> Dict[str, Optional[str]]:
    meta_type = (metadata or {}).get("type")
    subtype = (metadata or {}).get("subtype")
    qri_l = (qri or "").lower()
    label_l = (label or "").lower()

    is_qvd = ".qvd" in qri_l or ".qvd" in label_l
    is_file = qri_l.startswith("qri:file:") or "file://" in qri_l
    is_app = qri_l.startswith("qri:app:sense://")
    is_db = qri_l.startswith("qri:db:")

    if is_qvd:
        return {"type": "qvd", "layer": "extract", "group": "qvd"}
    if is_file:
        return {"type": "file", "layer": "extract", "group": "file"}
    if is_app:
        return {"type": "app", "layer": "app", "group": None}
    if is_db:
        group = extract_db_group(qri)
        if subtype == "TABLE":
            return {"type": "table", "layer": "db", "group": group}
        return {"type": "db", "layer": "db", "group": group}
    if meta_type == "DATASET":
        return {"type": "dataset", "layer": "transform", "group": None}
    return {"type": "other", "layer": "other", "group": None}
