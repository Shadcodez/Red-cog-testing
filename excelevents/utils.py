# ExcelEvents/utils.py
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional

def _normalize_key(name: str) -> str:
    return str(name).strip().lower()

def _is_valid_xlsx(file_path: Path) -> bool:
    try:
        with open(file_path, "rb") as f:
            header = f.read(4)
        return header[:2] == b'PK'
    except Exception:
        return False

def _get_column_indices(headers: List[str]) -> Dict[str, int]:
    col_map = {}
    aliases = {
        "name": ["name", "event name", "title", "event"],
        "start": ["start", "start time", "start date", "date", "when"],
        "end": ["end", "end time", "end date"],
        "description": ["description", "desc", "details"],
        "type": ["type", "event type", "format", "kind"],
        "location": ["location", "place", "venue", "address", "link"],
        "channelid": ["channelid", "channel id", "channel", "voice channel", "stage channel"],
        "image": ["image", "cover", "banner", "imageurl", "cover image", "event image"],
    }
    for i, h in enumerate(headers):
        if not h:
            continue
        norm = _normalize_key(h)
        for canonical, alias_list in aliases.items():
            if any(norm == _normalize_key(a) for a in alias_list):
                col_map[canonical] = i
                break
        else:
            col_map[norm] = i
    return col_map

def _get_cell(row: tuple, col_map: Dict[str, int], key: str, default=None):
    idx = col_map.get(key)
    if idx is not None and idx < len(row):
        val = row[idx]
        return val if val is not None else default
    return default

async def _parse_datetime(value) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, (int, float)):
        try:
            base = datetime(1899, 12, 30)
            dt = base + timedelta(days=value)
            return dt.replace(tzinfo=timezone.utc)
        except Exception:
            pass
    value_str = str(value).strip()
    if not value_str:
        return None
    formats = [
        "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S",
        "%m/%d/%Y %H:%M", "%m/%d/%Y %H:%M:%S",
        "%m/%d/%y %H:%M", "%m/%d/%y %H:%M:%S",
        "%m/%d/%Y %I:%M %p", "%m/%d/%Y %I:%M:%S %p",
        "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %I:%M %p",
        "%d/%m/%Y %H:%M", "%d/%m/%Y %H:%M:%S",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(value_str, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None
