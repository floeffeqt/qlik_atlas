from pathlib import Path
from typing import Any, Dict

from exporters.json_writer import write_json


def write_manifest(path: Path, manifest: Dict[str, Any]) -> None:
    write_json(path, manifest)
