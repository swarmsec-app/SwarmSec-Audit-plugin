"""Security-oriented summary of a git diff over Solidity sources.

Maps changed lines to functions, lists unchanged code that calls changed functions, and compares
storage layout and access modifiers between the two revisions.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from .solscan import Contract, SourceFile, declared_names, resolve_access, scan_source

HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", re.M)
REF_RE = re.compile(r"^[\w./@^~{}:-]+$")


class DiffError(Exception):
    pass


def _git(root: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        timeout=60,
        stdin=subprocess.DEVNULL,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        raise DiffError(f"git {' '.join(args[:2])} failed: {proc.stderr.strip()}")
    return proc.stdout


def parse_range(spec: str | None, root: Path) -> tuple[str | None, str | None]:
    """Turn a user range into (base, head). head None means the working tree.

    Accepts A...B (from merge base), A..B, a single commit (its own change), or nothing
    (uncommitted changes against HEAD).
    """
    if not spec:
        return "HEAD", None
    if spec.startswith("-") or not REF_RE.match(spec):
        raise DiffError(f"not a usable git range: {spec!r}")
    if "..." in spec:
        a, b = spec.split("...", 1)
        head = b or "HEAD"
        base = _git(root, "merge-base", _verify(root, a), _verify(root, head)).strip()
        return base, _verify(root, head)
    if ".." in spec:
        a, b = spec.split("..", 1)
        return _verify(root, a), _verify(root, b or "HEAD")
    commit = _verify(root, spec)
    parents = _git(root, "rev-list", "--parents", "-n", "1", commit).split()
    if len(parents) < 2:
        raise DiffError(f"{spec} has no parent; give an explicit range")
    return parents[1], commit


def _verify(root: Path, ref: str) -> str:
    if ref.startswith("-"):
        raise DiffError(f"not a usable git ref: {ref!r}")
    try:
        return _git(root, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}").strip()
    except DiffError:
        raise DiffError(f"unknown git revision: {ref}") from None


def _read(root: Path, rev: str | None, path: str) -> str | None:
    if rev is None:
        p = root / path
        return p.read_text(encoding="utf-8", errors="replace") if p.is_file() else None
    try:
        return _git(root, "show", f"{rev}:{path}")
    except DiffError:
        return None


def _changed(root: Path, base: str, head: str | None) -> dict[str, dict]:
    args = ["diff", "--unified=0", "--no-color", "--no-ext-diff", "-M", base]
    if head:
        args.append(head)
    args += ["--", "*.sol"]
    out = _git(root, *args)
    files: dict[str, dict] = {}
    current = None
    for line in out.splitlines():
        if line.startswith("diff --git"):
            current = None
        elif line.startswith("--- "):
            old = line[4:].strip()
            old_path = None if old == "/dev/null" else old.removeprefix("a/")
        elif line.startswith("+++ "):
            new = line[4:].strip()
            new_path = None if new == "/dev/null" else new.removeprefix("b/")
            key = new_path or old_path
            current = files.setdefault(
                key, {"old_path": old_path, "new_path": new_path, "old_lines": set(), "new_lines": set()}
            )
        elif current is not None and (m := HUNK_RE.match(line)):
            o_start, o_len = int(m.group(1)), int(m.group(2) or 1)
            n_start, n_len = int(m.group(3)), int(m.group(4) or 1)
            current["old_lines"].update(range(o_start, o_start + o_len))
            current["new_lines"].update(range(n_start, n_start + n_len))
    return files


def _functions_touching(sf: SourceFile | None, lines: set[int]) -> set[str]:
    if sf is None:
        return set()
    out = set()
    for c in sf.contracts:
        for fn in c.functions:
            if lines & set(range(fn.location.start_line, fn.location.end_line + 1)):
                out.add(f"{c.name}.{fn.name or fn.kind}")
        for mod in c.modifiers:
            if lines & set(range(mod.location.start_line, mod.location.end_line + 1)):
                out.add(f"{c.name}.{mod.name}")
        for v in c.state_vars:
            if v.line in lines:
                out.add(f"{c.name}.<state>")
    return out


def storage_layout_changes(old: Contract, new: Contract) -> list[str]:
    """Compare declaration order of storage variables in one contract (inherited slots not included)."""
    o = [(v.name, v.type) for v in old.state_vars if not (v.constant or v.immutable)]
    n = [(v.name, v.type) for v in new.state_vars if not (v.constant or v.immutable)]
    notes = []
    for i, (old_var, new_var) in enumerate(zip(o, n, strict=False)):
        if old_var != new_var:
            if old_var[0] == new_var[0]:
                notes.append(f"slot order {i}: type of {old_var[0]} changed {old_var[1]} -> {new_var[1]}")
            else:
                notes.append(
                    f"slot order {i}: {old_var[1]} {old_var[0]} replaced by {new_var[1]} {new_var[0]} "
                    "(existing storage is reinterpreted after an upgrade)"
                )
            break
    if len(n) < len(o):
        removed = [name for name, _ in o if name not in {x for x, _ in n}]
        notes.append(f"storage variables removed: {', '.join(removed) or 'tail entries'}")
    elif len(n) > len(o) and not notes:
        notes.append(
            f"storage variables appended: {', '.join(name for name, _ in n[len(o) :])} "
            "(safe for upgrades only if no child contract or gap occupies those slots)"
        )
    if old.bases != new.bases:
        notes.append(f"inheritance changed {old.bases} -> {new.bases} (inherited storage order may shift)")
    return notes


def _scan(text: str | None, path: str | None, known: set[str]) -> SourceFile | None:
    if text is None or path is None:
        return None
    sf = scan_source(text, path, known)
    resolve_access([sf])
    return sf


def diff_summary(root: Path, spec: str | None) -> dict:
    root = root.resolve()
    _git(root, "rev-parse", "--git-dir")
    base, head = parse_range(spec, root)
    changed = _changed(root, base, head)

    skip = {"lib", "node_modules", ".git", "out", "cache", ".swarmsec-audit"}
    if head is None:
        rels = [p.relative_to(root).as_posix() for p in sorted(root.rglob("*.sol")) if p.is_file()]
    else:
        rels = [r for r in _git(root, "ls-tree", "-r", "--name-only", head).splitlines() if r.endswith(".sol")]
    head_files = {rel: _read(root, head, rel) or "" for rel in rels if not skip & set(Path(rel).parts[:-1])}
    known = set().union(*(declared_names(t)[0] for t in head_files.values())) if head_files else set()

    files_out, changed_fns = [], set()
    for key, info in sorted(changed.items()):
        old_sf = _scan(_read(root, base, info["old_path"]) if info["old_path"] else None, info["old_path"], known)
        new_sf = _scan(_read(root, head, info["new_path"]) if info["new_path"] else None, info["new_path"], known)
        touched = _functions_touching(old_sf, info["old_lines"]) | _functions_touching(new_sf, info["new_lines"])
        changed_fns |= touched
        entry = {
            "file": key,
            "status": "added"
            if not info["old_path"]
            else "deleted"
            if not info["new_path"]
            else "renamed"
            if info["old_path"] != info["new_path"]
            else "modified",
            "changed_lines_new": _ranges(info["new_lines"]),
            "changed_members": sorted(touched),
            "access_changes": [],
            "storage_layout": [],
            "functions_added": [],
            "functions_removed": [],
        }
        old_c = {c.name: c for c in old_sf.contracts} if old_sf else {}
        new_c = {c.name: c for c in new_sf.contracts} if new_sf else {}
        for name in sorted(set(old_c) | set(new_c)):
            oc, nc = old_c.get(name), new_c.get(name)
            if oc and nc:
                for note in storage_layout_changes(oc, nc):
                    entry["storage_layout"].append(f"{name}: {note}")
                ofn = {f.name or f.kind: f for f in oc.functions}
                nfn = {f.name or f.kind: f for f in nc.functions}
                for fname in sorted(set(ofn) & set(nfn)):
                    a, b = ofn[fname], nfn[fname]
                    if (a.visibility, a.mutability, sorted(a.modifiers), a.access) != (
                        b.visibility,
                        b.mutability,
                        sorted(b.modifiers),
                        b.access,
                    ):
                        entry["access_changes"].append(
                            f"{name}.{fname}: {a.visibility} {a.mutability} mods={a.modifiers} access={a.access}"
                            f" -> {b.visibility} {b.mutability} mods={b.modifiers} access={b.access}"
                        )
                entry["functions_added"] += [f"{name}.{f}" for f in sorted(set(nfn) - set(ofn))]
                entry["functions_removed"] += [f"{name}.{f}" for f in sorted(set(ofn) - set(nfn))]
            elif nc:
                entry["functions_added"] += [f"{name}.{f.name or f.kind}" for f in nc.functions]
            elif oc:
                entry["functions_removed"] += [f"{name}.{f.name or f.kind}" for f in oc.functions]
        files_out.append(entry)

    callers = _callers_outside_diff(head_files, changed_fns, changed, known)
    return {
        "base": base,
        "head": head or "working-tree",
        "files": files_out,
        "unchanged_callers": callers,
        "note": "Lexical analysis. Callers are matched by function name; confirm each in source.",
    }


def _callers_outside_diff(
    head_files: dict[str, str], changed_fns: set[str], changed: dict, known: set[str]
) -> list[dict]:
    names = {fn.split(".", 1)[1] for fn in changed_fns if not fn.endswith(".<state>")}
    out = []
    for rel, text in sorted(head_files.items()):
        sf = scan_source(text, rel, known)
        changed_lines = changed.get(rel, {}).get("new_lines", set())
        for c in sf.contracts:
            for fn in c.functions:
                called = set(fn.internal_calls) | {call.target.split(".")[-1] for call in fn.external_calls}
                hits = sorted(called & names)
                span = set(range(fn.location.start_line, fn.location.end_line + 1))
                if hits and not span & changed_lines:
                    out.append(
                        {
                            "function": f"{c.name}.{fn.name or fn.kind}",
                            "location": f"{rel}:{fn.location.start_line}-{fn.location.end_line}",
                            "calls_changed": hits,
                        }
                    )
    return out


def _ranges(lines: set[int]) -> list[str]:
    out, run = [], []
    for n in sorted(lines):
        if run and n != run[-1] + 1:
            out.append(f"{run[0]}-{run[-1]}" if len(run) > 1 else str(run[0]))
            run = []
        run.append(n)
    if run:
        out.append(f"{run[0]}-{run[-1]}" if len(run) > 1 else str(run[0]))
    return out


def format_text(summary: dict) -> str:
    head = "working tree" if summary["head"] == "working-tree" else summary["head"][:12]
    out = [f"diff {summary['base'][:12]} -> {head}"]
    for f in summary["files"]:
        out.append(f"{f['status']} {f['file']} lines {', '.join(f['changed_lines_new']) or '-'}")
        out += [f"  changed: {m}" for m in f["changed_members"]]
        out += [f"  ACCESS: {a}" for a in f["access_changes"]]
        out += [f"  STORAGE: {s}" for s in f["storage_layout"]]
        out += [f"  added: {a}" for a in f["functions_added"]]
        out += [f"  removed: {r}" for r in f["functions_removed"]]
    if summary["unchanged_callers"]:
        out.append("unchanged code that calls changed functions:")
        out += [
            f"  {c['function']} ({c['location']}) -> {', '.join(c['calls_changed'])}"
            for c in summary["unchanged_callers"]
        ]
    out.append(summary["note"])
    return "\n".join(out)
