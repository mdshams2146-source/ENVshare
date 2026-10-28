from typing import List, Dict

def parse_raw_env(raw_text: str) -> List[Dict[str, str]]:
    """Parses raw text into key-value pairs, ignoring empty lines and comments."""
    parsed = []
    lines = raw_text.splitlines()
    for line in lines:
        cleaned = line.strip()
        if not cleaned or cleaned.startswith("#"):
            continue
        if "=" not in cleaned:
            continue
        key, value = cleaned.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key:
            parsed.append({"key": key, "value": value})
    return parsed

def compute_diff(incoming: List[Dict[str, str]], existing_vars: Dict[str, str]) -> List[dict]:
    """Computes NEW, UPDATE, and UNCHANGED status for pre-import review."""
    diff_results = []
    for item in incoming:
        key, val = item["key"], item["value"]
        if key not in existing_vars:
            diff_results.append({
                "key": key,
                "old_value": None,
                "new_value": val,
                "status": "NEW",
                "is_sensitive": False
            })
        elif existing_vars[key] != val:
            diff_results.append({
                "key": key,
                "old_value": existing_vars[key],
                "new_value": val,
                "status": "UPDATE",
                "is_sensitive": False
            })
        else:
            diff_results.append({
                "key": key,
                "old_value": val,
                "new_value": val,
                "status": "UNCHANGED",
                "is_sensitive": False
            })
    return diff_results