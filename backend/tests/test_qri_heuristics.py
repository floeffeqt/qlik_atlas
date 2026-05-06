import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from fetchers.qri_heuristics import derive_type_group_layer  # type: ignore


def test_derive_type_group_layer_detects_field_by_subtype():
    result = derive_type_group_layer(
        "qri:db:postgresql://sales#field-order_id",
        "order_id",
        {"type": "DATASET", "subtype": "FIELD"},
    )
    assert result["type"] == "field"
    assert result["layer"] == "db"
    assert result["group"] == "db:postgresql"


def test_derive_type_group_layer_detects_field_by_qri_prefix():
    result = derive_type_group_layer(
        "qri:field:sense://OrderDate",
        "OrderDate",
        {},
    )
    assert result["type"] == "field"
    assert result["layer"] == "transform"
