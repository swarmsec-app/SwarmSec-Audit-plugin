"""Import output from optional tools as unverified hints. Nothing here produces findings."""

from __future__ import annotations

import json
from pathlib import Path

CONTRACTMAP_MAJOR = "1"


class AdapterError(Exception):
    pass


def load_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AdapterError(f"cannot read {path.name}: {exc}") from exc
    if not isinstance(data, dict):
        raise AdapterError(f"{path.name}: expected a JSON object")
    return data


def import_contractmap(data: dict) -> dict:
    """Summarise a ContractMap AnalysisResult (schema 1.x) into attack-surface hints."""
    if data.get("tool") != "contractmap":
        raise AdapterError("not ContractMap output (field 'tool' is not 'contractmap')")
    version = str(data.get("schema_version", ""))
    if version.split(".")[0] != CONTRACTMAP_MAJOR:
        raise AdapterError(f"ContractMap schema {version or 'missing'} is not supported (need {CONTRACTMAP_MAJOR}.x)")
    contracts = {c["id"]: c for c in data.get("contracts", [])}

    def cname(cid: str | None) -> str:
        return contracts.get(cid, {}).get("name", cid or "?")

    entry_points = []
    for fn in data.get("functions", []):
        if fn.get("visibility") not in ("public", "external") or fn.get("mutability") in ("view", "pure"):
            continue
        access = fn.get("access", {})
        entry_points.append(
            {
                "function": f"{cname(fn.get('contract_id'))}.{fn.get('name')}",
                "signature": fn.get("signature"),
                "restriction": access.get("restriction", "unresolved"),
                "roles": access.get("roles", []),
                "modifiers": fn.get("modifiers", []),
                "calls_external": fn.get("calls_external", False),
                "source": fn.get("source"),
            }
        )
    proxies = [
        {
            "contract": c.get("name"),
            "kind": (c.get("proxy") or {}).get("kind"),
            "implementation": (c.get("proxy") or {}).get("implementation"),
            "admin": (c.get("proxy") or {}).get("admin"),
            "resolution": (c.get("proxy") or {}).get("resolution"),
        }
        for c in contracts.values()
        if c.get("is_proxy")
    ]
    edges = data.get("edges", [])
    return {
        "source": "contractmap",
        "schema_version": version,
        "tool_version": data.get("metadata", {}).get("tool_version"),
        "analysis_complete": data.get("metadata", {}).get("analysis_complete"),
        "entry_points": sorted(entry_points, key=lambda e: e["function"]),
        "roles": sorted(
            (
                {"name": r.get("name"), "kind": r.get("kind"), "contract": cname(r.get("contract_id"))}
                for r in data.get("roles", [])
            ),
            key=lambda r: (r["contract"], r["name"] or ""),
        ),
        "proxies": proxies,
        "external_call_edges": sorted(
            f"{e['source']} -{e['kind']}-> {e['target']}" for e in edges if e.get("kind") in ("calls", "delegatecalls")
        ),
        "unresolved_edges": sorted(
            f"{e['source']} -{e['kind']}-> {e['target']}" for e in edges if e.get("resolution") == "unresolved"
        ),
        "warnings": [w.get("message") for w in data.get("warnings", [])],
        "note": "Imported from ContractMap. Treat as leads; confirm high-consequence relationships in source.",
    }


def import_slither(data: dict) -> dict:
    """Normalise `slither --json` output into hints with file and line provenance."""
    if "results" not in data and "success" not in data:
        raise AdapterError("not Slither JSON output (no 'results')")
    if data.get("success") is False:
        raise AdapterError(f"Slither reported failure: {data.get('error') or 'no error message'}")
    hints = []
    for det in (data.get("results") or {}).get("detectors", []):
        locations = []
        for el in det.get("elements", []):
            sm = el.get("source_mapping") or {}
            lines = sm.get("lines") or []
            if sm.get("filename_relative") and lines:
                locations.append(f"{sm['filename_relative']}:{min(lines)}-{max(lines)}")
        hints.append(
            {
                "detector": det.get("check"),
                "impact": det.get("impact"),
                "confidence": det.get("confidence"),
                "description": (det.get("description") or "").strip().splitlines()[0] if det.get("description") else "",
                "locations": sorted(set(locations)),
            }
        )
    order = {"High": 0, "Medium": 1, "Low": 2, "Informational": 3, "Optimization": 4}
    hints.sort(key=lambda h: (order.get(h["impact"], 5), h["detector"] or "", h["locations"]))
    return {
        "source": "slither",
        "hints": hints,
        "note": "Slither detector output. Each hint is unverified until traced in source; many are false positives.",
    }


def format_hints(summary: dict) -> str:
    out = [summary["note"]]
    if summary["source"] == "slither":
        out += [
            f"[{h['impact']}/{h['confidence']}] {h['detector']}: {h['description']} "
            f"({', '.join(h['locations']) or 'no location'})"
            for h in summary["hints"]
        ]
        return "\n".join(out)
    out.append(
        f"ContractMap {summary['tool_version']} schema {summary['schema_version']}, "
        f"complete={summary['analysis_complete']}"
    )
    out += [
        f"entry {e['function']} restriction={e['restriction']} roles={e['roles']} mods={e['modifiers']}"
        for e in summary["entry_points"]
    ]
    out += [
        f"proxy {p['contract']} kind={p['kind']} impl={p['implementation']} ({p['resolution']})"
        for p in summary["proxies"]
    ]
    out += [f"unresolved edge {e}" for e in summary["unresolved_edges"]]
    out += [f"warning: {w}" for w in summary["warnings"]]
    return "\n".join(out)
