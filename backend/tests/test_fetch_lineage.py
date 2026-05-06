import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from fetchers.fetch_lineage import _app_graph_path, _normalize_graph_level  # type: ignore


def test_normalize_graph_level_rejects_unknown_value():
    assert _normalize_graph_level("custom") == "resource"


def test_normalize_graph_level_accepts_field():
    assert _normalize_graph_level("field") == "field"


def test_app_graph_path_embeds_selected_level():
    path = _app_graph_path("app-123", up_depth="-1", collapse="true", graph_level="field")
    assert "level=field" in path
    assert "up=-1" in path
    assert "collapse=true" in path


def test_app_graph_path_falls_back_to_resource_level():
    path = _app_graph_path("app-123", up_depth="-1", collapse="true", graph_level="invalid")
    assert "level=resource" in path
