import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from fetchers.fetch_app_data_metadata import fetch_app_data_metadata  # type: ignore


class _FakeClient:
    def __init__(self, payload):
        self.base_url = "https://tenant.example.com"
        self._payload = payload
        self.logger = None

    async def get_json(self, path, params=None):
        return self._payload, 200


@pytest.mark.asyncio
async def test_fetch_app_data_metadata_maps_example_and_collects_extra_fields():
    payload = {
        "fields": [
            {
                "hash": "field-hash-1",
                "name": "Field-1",
                "comment": "Comment-1",
                "cardinal": 42,
                "byte_size": 128,
                "is_hidden": False,
                "is_locked": True,
                "is_system": False,
                "is_numeric": True,
                "is_semantic": False,
                "total_count": 100,
                "distinct_only": False,
                "always_one_selected": False,
                "tags": ["$numeric"],
                "src_tables": ["Table-1"],
                "unknown_field_key": "drift",
            }
        ],
        "tables": [
            {
                "name": "Table-1",
                "comment": "table comment",
                "is_loose": False,
                "byte_size": 256,
                "is_system": False,
                "is_semantic": True,
                "no_of_rows": 10,
                "no_of_fields": 5,
                "no_of_key_fields": 2,
                "unknown_table_key": "drift",
            }
        ],
        "reload_meta": {
            "cpu_time_spent_ms": 2000,
            "peak_memory_bytes": 12000,
            "fullReloadPeakMemoryBytes": 13000,
            "partialReloadPeakMemoryBytes": 8000,
            "hardware": {"total_memory": 999999, "logical_cores": 8, "extra_hw": "drift"},
            "extra_reload_meta": "drift",
        },
        "static_byte_size": 1234,
        "has_section_access": True,
        "is_direct_query_mode": False,
        "tables_profiling_data": [
            {
                "NoOfRows": 42,
                "FieldProfiling": [
                    {
                        "Name": "my_field",
                        "Max": 12,
                        "Min": 1,
                        "Std": 2.1,
                        "Sum": 100.0,
                        "Sum2": 1000.0,
                        "Median": 5,
                        "Average": 6.3,
                        "Kurtosis": 1.1,
                        "Skewness": 0.2,
                        "FieldTags": ["$numeric"],
                        "Fractiles": [1, 2, 3],
                        "MostFrequent": [
                            {"Symbol": {"Text": "A", "Number": 1}, "Frequency": 10, "extra_mf": "x"}
                        ],
                        "FrequencyDistribution": {
                            "BinsEdges": [0.0, 10.0],
                            "Frequencies": [5, 7],
                            "NumberOfBins": 2,
                            "extra_fd": "x",
                        },
                        "NumberFormat": {"Dec": ".", "Fmt": "#,##0.00", "Thou": ",", "nDec": 2, "UseThou": 1},
                        "field_extra": "drift",
                    }
                ],
                "table_profile_extra": "drift",
            }
        ],
        "top_level_extra": "drift",
    }
    client = _FakeClient(payload)

    result = await fetch_app_data_metadata(app_id="app-1", client=client, profiling_enabled=True)

    assert result["app_id"] == "app-1"
    assert result["source"] == "/api/v1/apps/app-1/data/metadata"
    assert result["tenant"] == "tenant.example.com"
    assert result["schema_hash"] and len(result["schema_hash"]) == 64
    assert result["static_byte_size"] == 1234
    assert result["reload_meta_full_reload_peak_memory_bytes"] == 13000

    assert len(result["fields"]) == 1
    assert result["fields"][0]["field_hash"] == "field-hash-1"
    assert result["fields"][0]["extra_json"]["unknown_field_key"] == "drift"

    assert len(result["tables"]) == 1
    assert result["tables"][0]["name"] == "Table-1"
    assert result["tables"][0]["extra_json"]["unknown_table_key"] == "drift"

    assert len(result["table_profiles"]) == 1
    profile = result["table_profiles"][0]
    assert profile["no_of_rows"] == 42
    assert profile["extra_json"]["table_profile_extra"] == "drift"
    field_profile = profile["field_profiles"][0]
    assert field_profile["name"] == "my_field"
    assert field_profile["extra_json"]["field_extra"] == "drift"
    assert len(field_profile["most_frequent"]) == 1
    assert len(field_profile["frequency_distribution"]) == 2

    assert result["extra_json"]["unknown_top_level"]["top_level_extra"] == "drift"
    assert result["extra_json"]["reload_meta_extra"]["extra_reload_meta"] == "drift"
    assert result["extra_json"]["reload_meta_hardware_extra"]["extra_hw"] == "drift"


@pytest.mark.asyncio
async def test_fetch_app_data_metadata_handles_empty_structure():
    client = _FakeClient({})
    result = await fetch_app_data_metadata(app_id="app-empty", client=client, profiling_enabled=False)

    assert result["app_id"] == "app-empty"
    assert result["fields"] == []
    assert result["tables"] == []
    assert result["table_profiles"] == []
    assert result["static_byte_size"] is None
    assert result["has_section_access"] is None
    assert result["is_direct_query_mode"] is None
