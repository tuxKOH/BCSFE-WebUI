#!/usr/bin/env python3
"""
BCSFE Save Diff Tool

Compares two Battle Cats save files (save and save2) using BCSFE's own parser,
showing every field that differs in a readable format.

Usage:
    python diff_saves.py <save1> <save2>
"""

import sys
import os
import json

# Add src to path so we can import the project modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from bcsfe import core
from pathlib import Path as PyPath


# ── Helpers ──────────────────────────────────────────────────────


def natural_key(key: str) -> tuple:
    """Sort keys naturally: numbers within strings sort numerically."""
    import re

    parts = re.split(r"(\d+)", key)
    result = []
    for p in parts:
        try:
            result.append((0, int(p)))
        except ValueError:
            result.append((1, p.lower()))
    return result


def format_value(v, indent: int = 0) -> str:
    """Pretty-format a value for terminal output."""
    pad = "  " * indent
    if isinstance(v, dict):
        if not v:
            return "{}"
        lines = ["{"]
        for k in sorted(v.keys(), key=natural_key):
            lines.append(f"{pad}  {k!r}: {format_value(v[k], indent + 1)}")
        lines.append(f"{pad}}}")
        return "\n".join(lines)
    elif isinstance(v, list):
        if not v:
            return "[]"
        if len(v) <= 6 and all(isinstance(x, (int, float, bool, str)) for x in v):
            # Short flat list → inline
            return "[" + ", ".join(format_value(x) for x in v) + "]"
        lines = ["["]
        for item in v:
            lines.append(f"{pad}  {format_value(item, indent + 1)},")
        lines.append(f"{pad}]")
        return "\n".join(lines)
    elif isinstance(v, float):
        return f"{v:.6f}"
    elif isinstance(v, str):
        if len(v) > 80:
            return repr(v[:77] + "...")
        return repr(v)
    elif v is None:
        return "null"
    else:
        return repr(v)


def gather_keys(d1: dict, d2: dict, prefix: str = "") -> set[str]:
    """Get all unique dotted-key paths present in either dict."""
    keys: set[str] = set()
    for d in (d1, d2):
        for k, v in d.items():
            pk = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict) and not k.endswith("_serialized_tag"):
                keys |= gather_keys(v, v, pk)
            else:
                keys.add(pk)
    return keys


def get_value_at_path(d: dict, path: str):
    """Resolve a dotted path like 'cats.unlocked.0' into a value."""
    parts = path.split(".")
    current = d
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part, _MISSING)
        elif isinstance(current, (list, tuple)):
            try:
                current = current[int(part)]
            except (IndexError, ValueError):
                return _MISSING
        else:
            return _MISSING
        if current is _MISSING:
            break
    return current


class _Missing:
    def __repr__(self):
        return "<MISSING>"


_MISSING = _Missing()


def flatten_dict(d: dict, prefix: str = "") -> dict[str, object]:
    """Flatten nested dict/lists to dotted paths for easy comparison."""
    result: dict[str, object] = {}
    for k, v in d.items():
        pk = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            # Skip sub-dict serializations — we compare the top-level field
            # as a whole JSON-serialized value
            sub = flatten_dict(v, pk)
            result.update(sub)
        elif isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
            # List of dicts — flatten each entry
            for i, item in enumerate(v):
                if isinstance(item, dict):
                    sub = flatten_dict(item, f"{pk}[{i}]")
                    result.update(sub)
                else:
                    result[f"{pk}[{i}]"] = item
        else:
            result[pk] = v
    return result


def diff_dicts(d1: dict, d2: dict) -> dict:
    """Verbose diff: returns {'only_a': ..., 'only_b': ..., 'changed': ...}."""
    flat1 = flatten_dict(d1)
    flat2 = flatten_dict(d2)

    keys1 = set(flat1.keys())
    keys2 = set(flat2.keys())

    only_a = {}
    only_b = {}
    changed = {}

    for k in sorted(keys1 - keys2, key=natural_key):
        only_a[k] = flat1[k]
    for k in sorted(keys2 - keys1, key=natural_key):
        only_b[k] = flat2[k]
    for k in sorted(keys1 & keys2, key=natural_key):
        v1, v2 = flat1[k], flat2[k]
        if v1 != v2:
            changed[k] = (v1, v2)

    return {
        "only_save1": only_a,
        "only_save2": only_b,
        "changed": changed,
    }


def print_diff_stats(save1_path: str, save2_path: str):
    """Stats from raw binary — without parsing."""
    raw1 = open(save1_path, "rb").read()
    raw2 = open(save2_path, "rb").read()

    import hashlib

    md5_1 = hashlib.md5(raw1).hexdigest()
    md5_2 = hashlib.md5(raw2).hexdigest()

    print("=" * 60)
    print("  Raw Binary Stats")
    print("=" * 60)
    print(f"  {'':20s}  {'save1':>12s}  {'save2':>12s}")
    print(f"  {'─' * 20}  {'─' * 12}  {'─' * 12}")
    print(f"  {'Size (bytes)':20s}  {len(raw1):>12d}  {len(raw2):>12d}")
    print(f"  {'Size diff':20s}  {'':>12s}  {len(raw2)-len(raw1):>+12d}")
    print(f"  {'MD5':20s}  {md5_1:>12s}  {md5_2:>12s}")
    print()


def print_parsed_diff(
    label1: str, label2: str, d1: dict, d2: dict, verbose: bool = False
):
    """Print the parsed-field diff in a readable format."""
    result = diff_dicts(d1, d2)

    only_a = result["only_save1"]
    only_b = result["only_save2"]
    changed = result["changed"]

    changed_count = len(changed)
    only1_count = len(only_a)
    only2_count = len(only_b)
    total = changed_count + only1_count + only2_count

    if total == 0:
        print("  ✓ The two saves are IDENTICAL (all parsed fields match).")
        return

    print(f"\n  Summary: {total} difference(s) found")
    print(f"    • {changed_count} changed field(s)")
    print(f"    • {only1_count} field(s) only in {label1}")
    print(f"    • {only2_count} field(s) only in {label2}")
    print()

    if changed:
        print(f"  ── Changed Fields ──")
        for key in sorted(changed.keys(), key=natural_key):
            v1, v2 = changed[key]
            print(f"\n  [{key}]")
            print(f"    {label1}: {format_value(v1)}")
            print(f"    {label2}: {format_value(v2)}")
        print()

    if only_a:
        print(f"  ── Only in {label1} ──")
        for key in sorted(only_a.keys(), key=natural_key):
            print(f"  [{key}] = {format_value(only_a[key])}")
        print()

    if only_b:
        print(f"  ── Only in {label2} ──")
        for key in sorted(only_b.keys(), key=natural_key):
            print(f"  [{key}] = {format_value(only_b[key])}")
        print()


# ── Main ─────────────────────────────────────────────────────────


def main():
    if len(sys.argv) < 3:
        print("Usage: python diff_saves.py <save1> <save2>")
        print("       python diff_saves.py <save1> <save2> --json")
        print("       python diff_saves.py <save1> <save2> --raw")
        sys.exit(1)

    save1_path = sys.argv[1]
    save2_path = sys.argv[2]
    flag_json = "--json" in sys.argv
    flag_raw = "--raw" in sys.argv

    label1 = os.path.basename(save1_path)
    label2 = os.path.basename(save2_path)

    # ── 1. Print raw binary stats ──
    if not flag_json:
        print_diff_stats(save1_path, save2_path)

    # ── 2. BCSFE raw data compare ──
    raw1 = core.Data.from_file(core.Path(save1_path))
    raw2 = core.Data.from_file(core.Path(save2_path))
    raw_diff = raw1.data != raw2.data

    if not flag_json and not raw_diff:
        print("  ✓ Raw binary data is identical (same bytes).")
        if not flag_raw:
            return
    else:
        if not flag_json:
            print(f"  Raw binary differs: {len(raw1.data)} vs {len(raw2.data)} bytes")

    # ── 3. Parse with BCSFE and compare fields ──
    try:
        sf1 = core.SaveFile(raw1)
        sf2 = core.SaveFile(raw2)
    except Exception as e:
        print(f"\n  ✗ Parse error: {e}")
        print("  (Some save files may be corrupted or from incompatible versions)")
        sys.exit(1)

    d1 = sf1.to_dict()
    d2 = sf2.to_dict()

    if flag_json:
        # Machine-readable JSON output
        result = diff_dicts(d1, d2)
        print(json.dumps(result, indent=2, default=str))
        return

    print()
    print_parsed_diff(label1, label2, d1, d2)

    # ── 4. Quick flag for identical saves ──
    if not raw_diff and not diff_dicts(d1, d2)["changed"]:
        print("\n  (=) Saves are byte-for-byte identical in both raw and parsed form.")
    elif not diff_dicts(d1, d2)["changed"] and raw_diff:
        print("\n  (!) Saves differ at raw byte level but all parsed fields match.")
        print("      This likely means the remaining_data or padding differs.")


if __name__ == "__main__":
    main()
