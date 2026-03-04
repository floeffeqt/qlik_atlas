import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Set
from urllib.parse import urlparse

from shared.qlik_client import QlikClient, resolve_logger


KNOWN_TOP_LEVEL_KEYS = {
    "fields",
    "tables",
    "reload_meta",
    "static_byte_size",
    "has_section_access",
    "is_direct_query_mode",
    "tables_profiling_data",
}

KNOWN_RELOAD_META_KEYS = {
    "cpu_time_spent_ms",
    "peak_memory_bytes",
    "fullReloadPeakMemoryBytes",
    "partialReloadPeakMemoryBytes",
    "hardware",
}

KNOWN_HARDWARE_KEYS = {
    "total_memory",
    "logical_cores",
}

KNOWN_FIELD_KEYS = {
    "hash",
    "name",
    "comment",
    "cardinal",
    "byte_size",
    "is_hidden",
    "is_locked",
    "is_system",
    "is_numeric",
    "is_semantic",
    "total_count",
    "distinct_only",
    "always_one_selected",
    "tags",
    "src_tables",
}

KNOWN_TABLE_KEYS = {
    "name",
    "comment",
    "is_loose",
    "byte_size",
    "is_system",
    "is_semantic",
    "no_of_rows",
    "no_of_fields",
    "no_of_key_fields",
}

KNOWN_TABLE_PROFILE_KEYS = {
    "NoOfRows",
    "FieldProfiling",
}

KNOWN_FIELD_PROFILE_KEYS = {
    "Max",
    "Min",
    "Std",
    "Sum",
    "Name",
    "Sum2",
    "Median",
    "Average",
    "Kurtosis",
    "Skewness",
    "FieldTags",
    "Fractiles",
    "NegValues",
    "PosValues",
    "LastSorted",
    "NullValues",
    "TextValues",
    "ZeroValues",
    "FirstSorted",
    "AvgStringLen",
    "DataEvenness",
    "EmptyStrings",
    "MaxStringLen",
    "MinStringLen",
    "MostFrequent",
    "NumberFormat",
    "SumStringLen",
    "NumericValues",
    "DistinctValues",
    "DistinctTextValues",
    "DistinctNumericValues",
    "FrequencyDistribution",
}

KNOWN_MOST_FREQUENT_KEYS = {
    "Symbol",
    "Frequency",
}

KNOWN_SYMBOL_KEYS = {
    "Text",
    "Number",
}

KNOWN_NUMBER_FORMAT_KEYS = {
    "Dec",
    "Fmt",
    "Thou",
    "nDec",
    "UseThou",
}

KNOWN_FREQUENCY_DISTRIBUTION_KEYS = {
    "BinsEdges",
    "Frequencies",
    "NumberOfBins",
}


def _tenant_from_client(client: QlikClient) -> str:
    parsed = urlparse(client.base_url)
    return parsed.netloc or parsed.path or client.base_url


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _str_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bool_or_none(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y"}:
        return True
    if text in {"false", "0", "no", "n"}:
        return False
    return None


def _text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        text = _str_or_none(item)
        if text is not None:
            out.append(text)
    return out


def _number_list(value: Any) -> list[float]:
    if not isinstance(value, list):
        return []
    out: list[float] = []
    for item in value:
        number = _float_or_none(item)
        if number is not None:
            out.append(number)
    return out


def _unknown_fields(item: dict[str, Any], known_keys: Set[str]) -> dict[str, Any]:
    return {k: v for k, v in item.items() if k not in known_keys}


def _collect_key_paths(value: Any, prefix: str = "", out: Set[str] | None = None) -> Set[str]:
    if out is None:
        out = set()
    if isinstance(value, dict):
        for key, nested in value.items():
            key_str = str(key)
            path = f"{prefix}.{key_str}" if prefix else key_str
            out.add(path)
            _collect_key_paths(nested, path, out)
    elif isinstance(value, list):
        for nested in value:
            _collect_key_paths(nested, prefix, out)
    return out


def _schema_hash(payload: dict[str, Any]) -> str:
    paths = sorted(_collect_key_paths(payload))
    raw = "\n".join(paths)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _field_hash(field: dict[str, Any]) -> str:
    explicit = _str_or_none(field.get("hash"))
    if explicit:
        return explicit
    raw = "|".join(
        [
            _str_or_none(field.get("name")) or "",
            _str_or_none(field.get("comment")) or "",
            str(_int_or_none(field.get("cardinal")) or ""),
            str(_int_or_none(field.get("byte_size")) or ""),
        ]
    )
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()
    return f"field_{digest}"


def _normalize_field(field: dict[str, Any]) -> dict[str, Any]:
    return {
        "field_hash": _field_hash(field),
        "name": _str_or_none(field.get("name")),
        "comment": _str_or_none(field.get("comment")),
        "cardinal": _int_or_none(field.get("cardinal")),
        "byte_size": _int_or_none(field.get("byte_size")),
        "is_hidden": _bool_or_none(field.get("is_hidden")),
        "is_locked": _bool_or_none(field.get("is_locked")),
        "is_system": _bool_or_none(field.get("is_system")),
        "is_numeric": _bool_or_none(field.get("is_numeric")),
        "is_semantic": _bool_or_none(field.get("is_semantic")),
        "total_count": _int_or_none(field.get("total_count")),
        "distinct_only": _bool_or_none(field.get("distinct_only")),
        "always_one_selected": _bool_or_none(field.get("always_one_selected")),
        "tags": _text_list(field.get("tags")),
        "src_tables": _text_list(field.get("src_tables")),
        "extra_json": _unknown_fields(field, KNOWN_FIELD_KEYS) or None,
    }


def _normalize_table(table: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": _str_or_none(table.get("name")),
        "comment": _str_or_none(table.get("comment")),
        "is_loose": _bool_or_none(table.get("is_loose")),
        "byte_size": _int_or_none(table.get("byte_size")),
        "is_system": _bool_or_none(table.get("is_system")),
        "is_semantic": _bool_or_none(table.get("is_semantic")),
        "no_of_rows": _int_or_none(table.get("no_of_rows")),
        "no_of_fields": _int_or_none(table.get("no_of_fields")),
        "no_of_key_fields": _int_or_none(table.get("no_of_key_fields")),
        "extra_json": _unknown_fields(table, KNOWN_TABLE_KEYS) or None,
    }


def _normalize_tables_profiling_data(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    out: list[dict[str, Any]] = []
    for table_idx, table_profile in enumerate(value):
        if not isinstance(table_profile, dict):
            continue
        field_profiles_raw = table_profile.get("FieldProfiling")
        row: dict[str, Any] = {
            "profile_index": table_idx,
            "no_of_rows": _int_or_none(table_profile.get("NoOfRows")),
            "extra_json": _unknown_fields(table_profile, KNOWN_TABLE_PROFILE_KEYS) or None,
            "field_profiles": [],
        }
        if isinstance(field_profiles_raw, list):
            for field_idx, field_profile in enumerate(field_profiles_raw):
                if not isinstance(field_profile, dict):
                    continue
                most_frequent = field_profile.get("MostFrequent")
                freq_distribution = field_profile.get("FrequencyDistribution")
                number_format = field_profile.get("NumberFormat") if isinstance(field_profile.get("NumberFormat"), dict) else {}
                fp_extra = _unknown_fields(field_profile, KNOWN_FIELD_PROFILE_KEYS)
                if isinstance(number_format, dict):
                    number_format_extra = _unknown_fields(number_format, KNOWN_NUMBER_FORMAT_KEYS)
                    if number_format_extra:
                        fp_extra["number_format_extra"] = number_format_extra
                field_row: dict[str, Any] = {
                    "profile_index": field_idx,
                    "name": _str_or_none(field_profile.get("Name")),
                    "max_value": _float_or_none(field_profile.get("Max")),
                    "min_value": _float_or_none(field_profile.get("Min")),
                    "std_value": _float_or_none(field_profile.get("Std")),
                    "sum_value": _float_or_none(field_profile.get("Sum")),
                    "sum2_value": _float_or_none(field_profile.get("Sum2")),
                    "median_value": _float_or_none(field_profile.get("Median")),
                    "average_value": _float_or_none(field_profile.get("Average")),
                    "kurtosis": _float_or_none(field_profile.get("Kurtosis")),
                    "skewness": _float_or_none(field_profile.get("Skewness")),
                    "field_tags": _text_list(field_profile.get("FieldTags")),
                    "fractiles": _number_list(field_profile.get("Fractiles")),
                    "neg_values": _int_or_none(field_profile.get("NegValues")),
                    "pos_values": _int_or_none(field_profile.get("PosValues")),
                    "last_sorted": _str_or_none(field_profile.get("LastSorted")),
                    "null_values": _int_or_none(field_profile.get("NullValues")),
                    "text_values": _int_or_none(field_profile.get("TextValues")),
                    "zero_values": _int_or_none(field_profile.get("ZeroValues")),
                    "first_sorted": _str_or_none(field_profile.get("FirstSorted")),
                    "avg_string_len": _float_or_none(field_profile.get("AvgStringLen")),
                    "data_evenness": _float_or_none(field_profile.get("DataEvenness")),
                    "empty_strings": _int_or_none(field_profile.get("EmptyStrings")),
                    "max_string_len": _int_or_none(field_profile.get("MaxStringLen")),
                    "min_string_len": _int_or_none(field_profile.get("MinStringLen")),
                    "sum_string_len": _int_or_none(field_profile.get("SumStringLen")),
                    "numeric_values": _int_or_none(field_profile.get("NumericValues")),
                    "distinct_values": _int_or_none(field_profile.get("DistinctValues")),
                    "distinct_text_values": _int_or_none(field_profile.get("DistinctTextValues")),
                    "distinct_numeric_values": _int_or_none(field_profile.get("DistinctNumericValues")),
                    "number_format_dec": _str_or_none(number_format.get("Dec")) if isinstance(number_format, dict) else None,
                    "number_format_fmt": _str_or_none(number_format.get("Fmt")) if isinstance(number_format, dict) else None,
                    "number_format_thou": _str_or_none(number_format.get("Thou")) if isinstance(number_format, dict) else None,
                    "number_format_ndec": _int_or_none(number_format.get("nDec")) if isinstance(number_format, dict) else None,
                    "number_format_use_thou": _int_or_none(number_format.get("UseThou")) if isinstance(number_format, dict) else None,
                    "extra_json": fp_extra or None,
                    "most_frequent": [],
                    "frequency_distribution": [],
                }
                if isinstance(most_frequent, list):
                    for rank, item in enumerate(most_frequent):
                        if not isinstance(item, dict):
                            continue
                        symbol = item.get("Symbol") if isinstance(item.get("Symbol"), dict) else {}
                        mf_extra = _unknown_fields(item, KNOWN_MOST_FREQUENT_KEYS)
                        if isinstance(symbol, dict):
                            symbol_extra = _unknown_fields(symbol, KNOWN_SYMBOL_KEYS)
                            if symbol_extra:
                                mf_extra["symbol_extra"] = symbol_extra
                        field_row["most_frequent"].append(
                            {
                                "rank": rank,
                                "symbol_text": _str_or_none(symbol.get("Text")) if isinstance(symbol, dict) else None,
                                "symbol_number": _float_or_none(symbol.get("Number")) if isinstance(symbol, dict) else None,
                                "frequency": _int_or_none(item.get("Frequency")),
                                "extra_json": mf_extra or None,
                            }
                        )
                if isinstance(freq_distribution, dict):
                    bins_edges = freq_distribution.get("BinsEdges") if isinstance(freq_distribution.get("BinsEdges"), list) else []
                    frequencies = freq_distribution.get("Frequencies") if isinstance(freq_distribution.get("Frequencies"), list) else []
                    number_of_bins = _int_or_none(freq_distribution.get("NumberOfBins"))
                    dist_extra = _unknown_fields(freq_distribution, KNOWN_FREQUENCY_DISTRIBUTION_KEYS) or None
                    limit = max(len(bins_edges), len(frequencies))
                    for bin_idx in range(limit):
                        edge_value = bins_edges[bin_idx] if bin_idx < len(bins_edges) else None
                        freq_value = frequencies[bin_idx] if bin_idx < len(frequencies) else None
                        field_row["frequency_distribution"].append(
                            {
                                "bin_index": bin_idx,
                                "bin_edge": _float_or_none(edge_value),
                                "frequency": _int_or_none(freq_value),
                                "number_of_bins": number_of_bins,
                                "extra_json": dist_extra,
                            }
                        )
                row["field_profiles"].append(field_row)
        out.append(row)
    return out


async def fetch_app_data_metadata(
    app_id: str,
    client: QlikClient,
    *,
    profiling_enabled: bool = True,
) -> Dict[str, Any]:
    logger = resolve_logger(getattr(client, "logger", None), "qlik.fetch.app_data_metadata")
    app_id_clean = _str_or_none(app_id)
    if not app_id_clean:
        raise ValueError("app_id must not be empty")

    endpoint = f"/api/v1/apps/{app_id_clean}/data/metadata"
    tenant = _tenant_from_client(client)
    source = endpoint
    fetched_at = _utc_now_iso()

    logger.info("Fetching app data metadata app_id=%s", app_id_clean)
    response, _ = await client.get_json(endpoint)
    payload = response if isinstance(response, dict) else {}

    fields_raw = payload.get("fields")
    tables_raw = payload.get("tables")
    tables_profiling_raw = payload.get("tables_profiling_data")
    reload_meta = payload.get("reload_meta") if isinstance(payload.get("reload_meta"), dict) else {}
    hardware = reload_meta.get("hardware") if isinstance(reload_meta.get("hardware"), dict) else {}

    fields: list[dict[str, Any]] = []
    if isinstance(fields_raw, list):
        for field in fields_raw:
            if isinstance(field, dict):
                fields.append(_normalize_field(field))

    tables: list[dict[str, Any]] = []
    if isinstance(tables_raw, list):
        for table in tables_raw:
            if isinstance(table, dict):
                normalized = _normalize_table(table)
                if normalized.get("name"):
                    tables.append(normalized)

    table_profiles = _normalize_tables_profiling_data(tables_profiling_raw) if profiling_enabled else []

    extra_json: dict[str, Any] = {}
    top_extra = _unknown_fields(payload, KNOWN_TOP_LEVEL_KEYS)
    if top_extra:
        extra_json["unknown_top_level"] = top_extra
    reload_meta_extra = _unknown_fields(reload_meta, KNOWN_RELOAD_META_KEYS) if isinstance(reload_meta, dict) else {}
    if reload_meta_extra:
        extra_json["reload_meta_extra"] = reload_meta_extra
    hardware_extra = _unknown_fields(hardware, KNOWN_HARDWARE_KEYS) if isinstance(hardware, dict) else {}
    if hardware_extra:
        extra_json["reload_meta_hardware_extra"] = hardware_extra

    schema_hash = _schema_hash(payload)

    if not payload:
        logger.info("Metadata endpoint returned empty object for app_id=%s", app_id_clean)

    return {
        "app_id": app_id_clean,
        "fetched_at": fetched_at,
        "source": source,
        "tenant": tenant,
        "static_byte_size": _int_or_none(payload.get("static_byte_size")),
        "has_section_access": _bool_or_none(payload.get("has_section_access")),
        "is_direct_query_mode": _bool_or_none(payload.get("is_direct_query_mode")),
        "reload_meta_cpu_time_spent_ms": _int_or_none(reload_meta.get("cpu_time_spent_ms")) if isinstance(reload_meta, dict) else None,
        "reload_meta_peak_memory_bytes": _int_or_none(reload_meta.get("peak_memory_bytes")) if isinstance(reload_meta, dict) else None,
        "reload_meta_full_reload_peak_memory_bytes": _int_or_none(
            reload_meta.get("fullReloadPeakMemoryBytes") if isinstance(reload_meta, dict) else None
        ),
        "reload_meta_partial_reload_peak_memory_bytes": _int_or_none(
            reload_meta.get("partialReloadPeakMemoryBytes") if isinstance(reload_meta, dict) else None
        ),
        "reload_meta_hardware_total_memory": _int_or_none(hardware.get("total_memory")) if isinstance(hardware, dict) else None,
        "reload_meta_hardware_logical_cores": _int_or_none(hardware.get("logical_cores")) if isinstance(hardware, dict) else None,
        "schema_hash": schema_hash,
        "extra_json": extra_json or None,
        "fields": fields,
        "tables": tables,
        "table_profiles": table_profiles,
        "profiling_enabled": bool(profiling_enabled),
    }
