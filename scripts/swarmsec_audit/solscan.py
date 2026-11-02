"""Lexical Solidity scanner.

Produces an inventory of contracts, functions, modifiers, state variables and
security-relevant constructs with line numbers. It does not compile or resolve
types, so every result is a pointer for the reviewer to confirm in source.
"""

from __future__ import annotations

import bisect
import hashlib
import re
import tomllib
from dataclasses import asdict, dataclass, field
from pathlib import Path

SKIP_DIRS = {
    ".git",
    "out",
    "cache",
    "artifacts",
    "broadcast",
    "node_modules",
    ".swarmsec-audit",
    "typechain",
    "typechain-types",
    "crytic-export",
    "coverage",
}
VENDOR_DIRS = {"lib", "dependencies", ".deps", "node_modules"}
MAX_FILE_BYTES = 1_000_000
MAX_FILES = 2_000

IDENT = r"[A-Za-z_$][\w$]*"
CONTRACT_RE = re.compile(rf"\b(abstract\s+contract|contract|interface|library)\s+({IDENT})\s*(?:is\s+([^{{]*))?\{{")
PRAGMA_RE = re.compile(r"pragma\s+solidity\s+([^;]+);")
IMPORT_RE = re.compile(r"""import\s+(?:[^'";]*?\bfrom\s+)?["']([^"']+)["']""")
VISIBILITIES = {"public", "external", "internal", "private"}
MUTABILITIES = {"view", "pure", "payable", "nonpayable"}
FUNC_KEYWORDS = VISIBILITIES | MUTABILITIES | {"virtual", "override", "returns", "constant"}
VAR_KEYWORDS = VISIBILITIES | {"constant", "immutable", "override", "transient"}
NON_RECEIVERS = {
    "abi",
    "msg",
    "block",
    "tx",
    "type",
    "bytes",
    "string",
    "super",
    "address",
    "Math",
    "SafeCast",
    "Strings",
    "this",
}
# Modifier names that usually gate the caller. Used only when the modifier body is not in scope.
ACCESS_MODIFIER_RE = re.compile(
    r"^(only|auth$|requiresAuth|restricted|isAuthorized)|"
    r"(owner|admin|role|governance|governor|authorized|keeper|operator|guardian|minter|manager)",
    re.IGNORECASE,
)
SENDER_CHECK_RE = re.compile(
    r"msg\.sender\s*[!=]=|[!=]=\s*msg\.sender|_msgSender\(\)\s*[!=]=|[!=]=\s*_msgSender\(\)|"
    r"\b(hasRole|_checkRole|_checkOwner|_onlyOwner|_authorizeUpgrade|isAuthorized|canCall)\s*\("
)
ERC1967_SLOT = "360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc"

FLAG_PATTERNS: dict[str, re.Pattern[str]] = {
    # Solidity member call or Yul builtin (inline-assembly proxies).
    "delegatecall": re.compile(r"\.delegatecall\s*[({]|(?<![\w$.])delegatecall\s*\("),
    "assembly": re.compile(r"\bassembly\b"),
    "unchecked": re.compile(r"\bunchecked\s*\{"),
    "selfdestruct": re.compile(r"\bselfdestruct\s*\("),
    "tx-origin": re.compile(r"\btx\.origin\b"),
    "ecrecover": re.compile(r"\becrecover\s*\(|\bECDSA\.(?:try)?[Rr]ecover\s*\(|\.recover\s*\("),
    "block-timestamp": re.compile(r"\bblock\.timestamp\b"),
    "blockhash-randomness": re.compile(r"\bblockhash\s*\(|\bblock\.prevrandao\b|\bblock\.difficulty\b"),
    "self-balance": re.compile(
        r"\bbalanceOf\s*\(\s*address\s*\(\s*this\s*\)\s*\)|address\s*\(\s*this\s*\)\s*\.balance"
    ),
    "oracle-read": re.compile(r"\blatestRoundData\s*\(|\blatestAnswer\s*\("),
    "spot-price": re.compile(r"\bgetReserves\s*\(|\bslot0\s*\("),
    "permit": re.compile(r"\.permit\s*\("),
    "encode-packed": re.compile(r"\babi\.encodePacked\s*\("),
}


@dataclass
class Location:
    file: str
    start_line: int
    end_line: int


@dataclass
class ExternalCall:
    kind: str  # low-level-call, delegatecall, staticcall, eth-transfer, typed, self-call
    target: str
    line: int


@dataclass
class Function:
    contract: str
    name: str
    kind: str  # function, constructor, fallback, receive
    visibility: str
    mutability: str
    modifiers: list[str]
    location: Location
    has_body: bool
    access: str = "none-detected"  # modifier, inline-check, unresolved-modifier, none-detected
    external_calls: list[ExternalCall] = field(default_factory=list)
    state_writes: list[str] = field(default_factory=list)
    internal_calls: list[str] = field(default_factory=list)
    flags: dict[str, list[int]] = field(default_factory=dict)

    @property
    def entry_point(self) -> bool:
        if self.kind in ("fallback", "receive"):
            return True
        return (
            self.kind == "function"
            and self.visibility in ("public", "external")
            and self.mutability not in ("view", "pure")
        )


@dataclass
class Modifier:
    contract: str
    name: str
    location: Location
    checks_sender: bool


@dataclass
class StateVar:
    contract: str
    name: str
    type: str
    line: int
    constant: bool
    immutable: bool


@dataclass
class Contract:
    name: str
    kind: str
    bases: list[str]
    location: Location
    functions: list[Function] = field(default_factory=list)
    modifiers: list[Modifier] = field(default_factory=list)
    state_vars: list[StateVar] = field(default_factory=list)
    structs: list[str] = field(default_factory=list)
    proxy_hints: list[str] = field(default_factory=list)


@dataclass
class SourceFile:
    path: str
    role: str  # production, test, script, mock, interface, vendored
    sha256: str
    lines: int
    pragmas: list[str]
    imports: list[str]
    contracts: list[Contract]


def blank(text: str) -> str:
    return re.sub(r"[^\n]", " ", text)


def strip_comments_and_strings(src: str) -> str:
    """Blank out comments and string contents, keeping offsets and line numbers intact."""
    out: list[str] = []
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        nxt = src[i + 1] if i + 1 < n else ""
        if c == "/" and nxt == "/":
            j = src.find("\n", i)
            j = n if j == -1 else j
            out.append(" " * (j - i))
            i = j
        elif c == "/" and nxt == "*":
            j = src.find("*/", i + 2)
            j = n if j == -1 else j + 2
            out.append(blank(src[i:j]))
            i = j
        elif c in "\"'":
            j = i + 1
            while j < n and src[j] != c and src[j] != "\n":
                j += 2 if src[j] == "\\" else 1
            j = min(j + 1, n)
            out.append(c + blank(src[i + 1 : j - 1]) + (src[j - 1] if j - 1 > i else ""))
            i = j
        else:
            out.append(c)
            i += 1
    return "".join(out)


class _Lines:
    def __init__(self, text: str) -> None:
        self.starts = [0] + [m.end() for m in re.finditer("\n", text)]

    def line(self, offset: int) -> int:
        return bisect.bisect_right(self.starts, offset)


def match_close(text: str, open_idx: int) -> int:
    """Index of the bracket closing the one at open_idx, or len(text) if unbalanced."""
    pairs = {"{": "}", "(": ")", "[": "]"}
    opener = text[open_idx]
    closer = pairs[opener]
    depth = 0
    for i in range(open_idx, len(text)):
        if text[i] == opener:
            depth += 1
        elif text[i] == closer:
            depth -= 1
            if depth == 0:
                return i
    return len(text)


def split_top_level(text: str, sep: str = ",") -> list[str]:
    parts, depth, cur = [], 0, []
    for ch in text:
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        if ch == sep and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    parts.append("".join(cur))
    return [p.strip() for p in parts if p.strip()]


def classify_path(rel: Path) -> str:
    parts = {p.lower() for p in rel.parts[:-1]}
    name = rel.name
    if parts & VENDOR_DIRS:
        return "vendored"
    if name.endswith(".t.sol") or parts & {"test", "tests"}:
        return "test"
    if name.endswith(".s.sol") or parts & {"script", "scripts"}:
        return "script"
    if parts & {"mock", "mocks"} or name.lower().startswith("mock"):
        return "mock"
    return "production"


def _members(text: str, start: int, end: int):
    """Yield (header_start, header_end, terminator_idx, member_end) for top-level members of a body."""
    p = start
    while p < end:
        while p < end and text[p].isspace():
            p += 1
        if p >= end:
            return
        depth = 0
        k = p
        while k < end:
            ch = text[k]
            if ch in "([":
                depth += 1
            elif ch in ")]":
                depth -= 1
            elif depth == 0 and ch in "{;":
                break
            k += 1
        if k >= end:
            return
        member_end = match_close(text, k) if text[k] == "{" else k
        yield p, k, member_end
        p = member_end + 1


def _parse_function_header(header: str) -> tuple[str, str, str, list[str]] | None:
    """Return (kind, name, attrs, params) for a function-like header."""
    m = re.match(rf"\s*(function\s+({IDENT})|function|constructor|fallback|receive)\s*\(", header)
    if not m:
        return None
    word = m.group(1)
    if word.startswith("function"):
        name = m.group(2) or ""
        kind = "function" if name else "fallback"
    else:
        name, kind = word, word
    open_idx = m.end() - 1
    close_idx = match_close(header, open_idx)
    params = split_top_level(header[open_idx + 1 : close_idx])
    attrs = header[close_idx + 1 :]
    returns = re.search(r"\breturns\s*\(", attrs)
    if returns:
        attrs = attrs[: returns.start()]
    return kind, name, attrs, params


def _attr_tokens(attrs: str) -> list[str]:
    tokens, i = [], 0
    while i < len(attrs):
        m = re.match(rf"\s*({IDENT})", attrs[i:])
        if not m:
            i += 1
            continue
        tok = m.group(1)
        i += m.end()
        rest = attrs[i:]
        if rest.lstrip().startswith("("):
            open_idx = i + (len(rest) - len(rest.lstrip()))
            i = match_close(attrs, open_idx) + 1
        tokens.append(tok)
    return tokens


def _declared_types(params: list[str]) -> dict[str, str]:
    out = {}
    for p in params:
        words = p.split()
        if len(words) >= 2:
            out[words[-1]] = words[0]
    return out


def _analyze_body(
    fn: Function,
    body: str,
    body_offset: int,
    lines: _Lines,
    state_vars: dict[str, str],
    known_types: set[str],
    libraries: set[str],
    local_types: dict[str, str],
) -> None:
    def line_at(i: int) -> int:
        return lines.line(body_offset + i)

    for name, pat in FLAG_PATTERNS.items():
        hits = sorted({line_at(m.start()) for m in pat.finditer(body)})
        if hits:
            fn.flags[name] = hits

    for m in re.finditer(r"\.\s*(call|delegatecall|staticcall)\s*(\{[^}]*\})?\s*\(", body):
        kind = {"call": "low-level-call"}.get(m.group(1), m.group(1))
        fn.external_calls.append(ExternalCall(kind, _receiver(body, m.start()), line_at(m.start())))
    for m in re.finditer(r"\.\s*(send|transfer)\s*\(", body):
        close = match_close(body, m.end() - 1)
        if len(split_top_level(body[m.end() : close])) == 1:
            fn.external_calls.append(ExternalCall("eth-transfer", _receiver(body, m.start()), line_at(m.start())))

    typed = {**state_vars, **local_types}
    for m in re.finditer(rf"({IDENT})\s*\.\s*({IDENT})\s*(\{{[^}}]*\}})?\s*\(", body):
        recv, method = m.group(1), m.group(2)
        if method in ("call", "delegatecall", "staticcall", "send") or recv in NON_RECEIVERS:
            continue
        if method == "transfer" and len(split_top_level(body[m.end() : match_close(body, m.end() - 1)])) == 1:
            continue
        if recv in libraries:
            continue
        rtype = typed.get(recv, "")
        if rtype in known_types or _looks_like_interface(rtype):
            fn.external_calls.append(ExternalCall("typed", f"{recv}.{method}", line_at(m.start())))
    # Calls through a mapping of contracts: feeds[token].latestRoundData()
    for m in re.finditer(rf"({IDENT})\s*\[[^\]]*\]\s*\.\s*({IDENT})\s*\(", body):
        value_type = typed.get(m.group(1), "").rsplit("=>", 1)[-1].strip(" )")
        if value_type in known_types or _looks_like_interface(value_type):
            fn.external_calls.append(ExternalCall("typed", f"{m.group(1)}[].{m.group(2)}", line_at(m.start())))
    # Interface casts: IERC20(token).transfer(...), IWETH(weth).deposit{value: x}()
    for m in re.finditer(rf"\b({IDENT})\s*\(([^()]*)\)\s*\.\s*({IDENT})\s*(?:\{{[^}}]*\}}\s*)?\(", body):
        cast, method = m.group(1), m.group(3)
        if (cast in known_types and cast not in libraries) or _looks_like_interface(cast):
            fn.external_calls.append(
                ExternalCall("typed", f"{cast}({m.group(2).strip()}).{method}", line_at(m.start()))
            )
    for m in re.finditer(r"\bthis\s*\.\s*(\w+)\s*\(", body):
        fn.external_calls.append(ExternalCall("self-call", f"this.{m.group(1)}", line_at(m.start())))
    fn.external_calls.sort(key=lambda c: (c.line, c.kind, c.target))

    writes = set()
    for var in state_vars:
        v = re.escape(var)
        assign = rf"(?<![\w$.]){v}\s*(?:\[[^\]]*\]\s*)*(?:\.\s*[\w$]+\s*)*(?:[-+*/%|&^]|<<|>>)?=(?!=)"
        incdec = rf"(?:\+\+|--)\s*{v}\b|(?<![\w$.]){v}\s*(?:\[[^\]]*\]\s*)*(?:\.\s*[\w$]+\s*)*(?:\+\+|--)"
        other = rf"\bdelete\s+{v}\b|(?<![\w$.]){v}\s*(?:\[[^\]]*\]\s*)*\.\s*(?:push|pop)\s*\("
        if re.search(assign, body) or re.search(incdec, body) or re.search(other, body):
            writes.add(var)
    fn.state_writes = sorted(writes)
    fn.internal_calls = sorted({m.group(1) for m in re.finditer(rf"(?<![\w$.])({IDENT})\s*\(", body)})

    if SENDER_CHECK_RE.search(body):
        fn.access = "inline-check"


def declared_names(text: str) -> tuple[set[str], set[str]]:
    """(contract/interface/library names, library names) declared in a source text."""
    found = list(CONTRACT_RE.finditer(strip_comments_and_strings(text)))
    return {m.group(2) for m in found}, {m.group(2) for m in found if m.group(1) == "library"}


def scan_source(
    text: str, rel_path: str, known_types: set[str] | None = None, libraries: set[str] | None = None
) -> SourceFile:
    """Scan one file. Pass names declared elsewhere in the project to recognise cross-file types."""
    stripped = strip_comments_and_strings(text)
    lines = _Lines(stripped)
    rel = Path(rel_path)
    contracts: list[Contract] = []
    local_known, local_libs = declared_names(text)
    known_types = local_known | (known_types or set())
    libraries = local_libs | (libraries or set())

    for m in CONTRACT_RE.finditer(stripped):
        open_idx = m.end() - 1
        close_idx = match_close(stripped, open_idx)
        kind = "abstract" if m.group(1).startswith("abstract") else m.group(1)
        bases = [
            re.match(rf"\s*({IDENT}(?:\.{IDENT})*)", b).group(1)
            for b in split_top_level(m.group(3) or "")
            if re.match(rf"\s*{IDENT}", b)
        ]
        contract = Contract(
            m.group(2), kind, bases, Location(rel.as_posix(), lines.line(m.start()), lines.line(close_idx))
        )
        pending: list[tuple[Function, int, int, dict[str, str]]] = []
        for h_start, term, end in _members(stripped, open_idx + 1, close_idx):
            header = stripped[h_start:term]
            first = header.split(None, 1)[0] if header.split() else ""
            loc = Location(rel.as_posix(), lines.line(h_start), lines.line(end))
            if first == "modifier":
                name = re.match(rf"\s*modifier\s+({IDENT})", header)
                body = stripped[term : end + 1] if stripped[term] == "{" else ""
                if name:
                    contract.modifiers.append(
                        Modifier(contract.name, name.group(1), loc, bool(SENDER_CHECK_RE.search(body)))
                    )
                continue
            if first in ("struct", "enum"):
                sm = re.match(rf"\s*(?:struct|enum)\s+({IDENT})", header)
                if sm:
                    contract.structs.append(sm.group(1))
                continue
            if first in ("event", "error", "using", "type", "import", "pragma"):
                continue
            # `function(...) ... name;` at contract level is a function-typed state variable, not a fallback.
            is_fn_var = stripped[term] == ";" and contract.kind != "interface" and re.match(r"\s*function\s*\(", header)
            parsed = None if is_fn_var else _parse_function_header(header)
            if parsed:
                kind_f, name, attrs, params = parsed
                tokens = _attr_tokens(attrs)
                vis = next(
                    (t for t in tokens if t in VISIBILITIES),
                    "external" if contract.kind == "interface" or kind_f in ("fallback", "receive") else "public",
                )
                mut = next((t for t in tokens if t in MUTABILITIES and t != "nonpayable"), "nonpayable")
                if "constant" in tokens:
                    mut = "view"
                mods = [t for t in tokens if t not in FUNC_KEYWORDS]
                has_body = stripped[term] == "{"
                fn = Function(contract.name, name, kind_f, vis, mut, mods, loc, has_body)
                if has_body:
                    pending.append((fn, term + 1, end, _declared_types(params)))
                contract.functions.append(fn)
                continue
            # Anything else ending in ';' at contract level is a state variable declaration.
            if stripped[term] == ";":
                decl = _before_initializer(header).strip()
                decl_words = _attr_tokens(decl) if decl else []
                if len(decl_words) < 2:
                    continue
                name = decl_words[-1]
                type_part = decl[: decl.rfind(name)].strip()
                for kw in VAR_KEYWORDS:
                    type_part = re.sub(rf"\b{kw}\b(\s*\([^)]*\))?", "", type_part)
                contract.state_vars.append(
                    StateVar(
                        contract.name,
                        name,
                        " ".join(type_part.split()),
                        loc.start_line,
                        bool(re.search(r"\bconstant\b", decl)),
                        bool(re.search(r"\bimmutable\b", decl)),
                    )
                )

        storage_vars = {v.name: v.type for v in contract.state_vars if not v.constant}
        all_types = known_types | set(contract.structs)
        for fn, b_start, b_end, param_types in pending:
            body = stripped[b_start:b_end]
            local_types = dict(param_types)
            for lm in re.finditer(rf"\b({IDENT})\s+(?:memory\s+|storage\s+|calldata\s+)?({IDENT})\s*[=;]", body):
                if lm.group(1)[0].isupper():
                    local_types[lm.group(2)] = lm.group(1)
            _analyze_body(
                fn, body, b_start, lines, storage_vars, all_types - set(contract.structs), libraries, local_types
            )

        if ERC1967_SLOT in text.lower():
            contract.proxy_hints.append("erc1967-slot")
        for fn in contract.functions:
            if "delegatecall" in fn.flags and any(f.kind == "fallback" for f in contract.functions):
                contract.proxy_hints.append("delegating-fallback")
            if fn.name in ("upgradeTo", "upgradeToAndCall", "_authorizeUpgrade"):
                contract.proxy_hints.append(f"upgrade-function:{fn.name}")
            if fn.name in ("initialize", "init", "__init") or fn.name.startswith("initialize"):
                contract.proxy_hints.append(f"initializer:{fn.name}")
        contract.proxy_hints = sorted(set(contract.proxy_hints))
        contracts.append(contract)

    role = classify_path(rel)
    if role == "production" and contracts and all(c.kind == "interface" for c in contracts):
        role = "interface"
    return SourceFile(
        path=rel.as_posix(),
        role=role,
        sha256=hashlib.sha256(text.encode()).hexdigest(),
        lines=text.count("\n") + 1,
        pragmas=sorted({p.strip() for p in PRAGMA_RE.findall(stripped)}),
        imports=IMPORT_RE.findall(text_without_comments(text)),
        contracts=contracts,
    )


def text_without_comments(text: str) -> str:
    """Remove comments but keep string literals (needed for import paths and pragmas)."""
    return re.sub(r"//[^\n]*|/\*.*?\*/", lambda m: blank(m.group(0)), text, flags=re.DOTALL)


def _before_initializer(header: str) -> str:
    """Declaration text before a top-level '=' (ignores the '=>' inside mapping types)."""
    depth = 0
    for i, ch in enumerate(header):
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        elif ch == "=" and depth == 0 and header[i + 1 : i + 2] != ">":
            return header[:i]
    return header


def _looks_like_interface(name: str) -> bool:
    return len(name) > 1 and name[0] == "I" and name[1].isupper()


def _receiver(body: str, dot_idx: int) -> str:
    """Best-effort text of the expression before a '.call' style member access."""
    j = dot_idx
    depth = 0
    while j > 0:
        ch = body[j - 1]
        if ch in ")]":
            depth += 1
        elif ch in "([":
            if depth == 0:
                break
            depth -= 1
        elif depth == 0 and not (ch.isalnum() or ch in "_$."):
            break
        j -= 1
    return " ".join(body[j:dot_idx].split()) or "?"


def resolve_access(files: list[SourceFile]) -> None:
    """Classify each function's caller restriction using in-scope modifier definitions."""
    modifiers: dict[str, bool] = {}
    for f in files:
        for c in f.contracts:
            for mod in c.modifiers:
                modifiers[mod.name] = modifiers.get(mod.name, False) or mod.checks_sender
    for f in files:
        for c in f.contracts:
            for fn in c.functions:
                if fn.access == "inline-check":
                    continue
                for mod in fn.modifiers:
                    if mod in modifiers:
                        if modifiers[mod]:
                            fn.access = "modifier"
                            break
                    elif ACCESS_MODIFIER_RE.search(mod) and mod not in c.bases:
                        fn.access = "unresolved-modifier"


def detect_build(root: Path) -> dict:
    info: dict = {
        "system": None,
        "config": None,
        "compiler": None,
        "src": None,
        "artifacts": [],
        "warnings": [],
        "remappings": [],
    }
    foundry = root / "foundry.toml"
    if foundry.is_file():
        info["system"], info["config"] = "foundry", "foundry.toml"
        try:
            profile = tomllib.loads(foundry.read_text(encoding="utf-8")).get("profile", {}).get("default", {})
        except tomllib.TOMLDecodeError as exc:
            info["warnings"].append(f"foundry.toml does not parse: {exc}")
            profile = {}
        info["compiler"] = profile.get("solc_version") or profile.get("solc")
        info["src"] = profile.get("src", "src")
        info["remappings"] = list(profile.get("remappings", []))
        if profile.get("ffi"):
            info["warnings"].append("foundry.toml enables ffi: tests can run arbitrary commands")
    for name, system in (
        ("hardhat.config.ts", "hardhat"),
        ("hardhat.config.js", "hardhat"),
        ("hardhat.config.cjs", "hardhat"),
        ("truffle-config.js", "truffle"),
        ("brownie-config.yaml", "brownie"),
        ("ape-config.yaml", "ape"),
    ):
        if (root / name).is_file():
            info["system"] = info["system"] or system
            info["config"] = info["config"] or name
            if name.endswith((".js", ".ts", ".cjs")):
                info["warnings"].append(f"{name} is executable code: compiling through it runs project JavaScript")
    remap_file = root / "remappings.txt"
    if remap_file.is_file():
        info["remappings"] += [r.strip() for r in remap_file.read_text(encoding="utf-8").splitlines() if r.strip()]
    for art in ("out", "artifacts", "build"):
        if (root / art).is_dir():
            info["artifacts"].append(art)
    return info


def _resolve_import(imp: str, file_rel: Path, root: Path, remappings: list[str]) -> bool:
    if imp.startswith("."):
        return (root / file_rel.parent / imp).resolve().is_file()
    for r in remappings:
        prefix, _, target = r.partition("=")
        prefix = prefix.split(":")[-1]
        if imp.startswith(prefix) and (root / target / imp[len(prefix) :]).is_file():
            return True
    return any((root / base / imp).is_file() for base in ("", "lib", "node_modules"))


def walk(target: Path, include_vendored: bool = False) -> tuple[Path, list[Path], list[dict]]:
    """Return (root, solidity files, skipped entries) for a file or directory target."""
    target = target.resolve()
    root = target if target.is_dir() else target.parent
    if target.is_file():
        return root, [target], []
    files, skipped = [], []
    for path in sorted(target.rglob("*.sol")):
        if not path.is_file():  # Foundry artifacts are directories named after the source file
            continue
        rel_parts = path.relative_to(target).parts
        if any(p in SKIP_DIRS for p in rel_parts[:-1]):
            continue
        if not include_vendored and any(p in VENDOR_DIRS for p in rel_parts[:-1]):
            continue
        if path.stat().st_size > MAX_FILE_BYTES:
            skipped.append({"path": Path(*rel_parts).as_posix(), "reason": "larger than 1 MB"})
            continue
        if len(files) >= MAX_FILES:
            skipped.append({"path": Path(*rel_parts).as_posix(), "reason": f"file limit {MAX_FILES} reached"})
            continue
        files.append(path)
    return root, files, skipped


def inventory(target: Path, include_vendored: bool = False, project_root: Path | None = None) -> dict:
    """Scan a file or directory. Paths are reported relative to project_root (detected if not given)."""
    root, paths, skipped = walk(target, include_vendored)
    project_root = project_root.resolve() if project_root else _project_root(root)
    build = detect_build(project_root)
    texts = {p: p.read_text(encoding="utf-8", errors="replace") for p in paths}
    known: set[str] = set()
    libs: set[str] = set()
    for text in texts.values():
        names, lib_names = declared_names(text)
        known |= names
        libs |= lib_names
    files = [scan_source(text, p.relative_to(project_root).as_posix(), known, libs) for p, text in texts.items()]
    resolve_access(files)
    unresolved = sorted(
        {
            f"{f.path}: {imp}"
            for f in files
            for imp in f.imports
            if not _resolve_import(imp, Path(f.path), project_root, build["remappings"])
        }
    )
    vendored_count = 0
    if not include_vendored and target.is_dir():
        vendored_count = sum(
            1 for p in target.rglob("*.sol") if any(part in VENDOR_DIRS for part in p.relative_to(target).parts[:-1])
        )
    return {
        "root": project_root.as_posix(),
        "target": Path(target).resolve().relative_to(project_root).as_posix() or ".",
        "build": build,
        "files": [asdict(f) for f in files],
        "entry_points": [
            _entry(fn)
            for f in files
            if f.role in ("production", "interface")
            for c in f.contracts
            if c.kind != "interface"
            for fn in c.functions
            if fn.entry_point
        ],
        "unresolved_imports": unresolved,
        "skipped": skipped,
        "vendored_files_not_scanned": vendored_count,
    }


def _entry(fn: Function) -> dict:
    return {
        "id": f"{fn.contract}.{fn.name or fn.kind}",
        "location": f"{fn.location.file}:{fn.location.start_line}-{fn.location.end_line}",
        "visibility": fn.visibility,
        "mutability": fn.mutability,
        "modifiers": fn.modifiers,
        "access": fn.access,
        "state_writes": fn.state_writes,
        "external_calls": [f"{c.kind}:{c.target}@{c.line}" for c in fn.external_calls],
        "flags": sorted(fn.flags),
    }


def _project_root(start: Path) -> Path:
    """Nearest ancestor with a build config or .git, else the start directory."""
    markers = ("foundry.toml", "hardhat.config.ts", "hardhat.config.js", "truffle-config.js", ".git")
    for candidate in (start, *start.parents):
        if any((candidate / m).exists() for m in markers):
            return candidate
    return start


TEXT_LIMITS = {"contracts": 250, "entry points": 200, "other functions": 100}
ACCESS_RISK = {"none-detected": 0, "unresolved-modifier": 1, "inline-check": 2, "modifier": 3}


def _capped(lines: list[str], what: str) -> list[str]:
    limit = TEXT_LIMITS[what]
    if len(lines) <= limit:
        return lines
    return [*lines[:limit], f"  ... {len(lines) - limit} more {what} lines omitted; see inventory.json"]


def format_text(inv: dict) -> str:
    """Compact listing for the model's context. Long sections are capped; the JSON has everything."""
    out = [f"root: {inv['root']}", f"target: {inv['target']}"]
    b = inv["build"]
    out.append(
        f"build: {b['system'] or 'none detected'} config={b['config']} compiler={b['compiler']} "
        f"artifacts={','.join(b['artifacts']) or 'none'}"
    )
    out += [f"warning: {w}" for w in b["warnings"]]
    roles: dict[str, int] = {}
    for f in inv["files"]:
        roles[f["role"]] = roles.get(f["role"], 0) + 1
    out.append(
        "files: "
        + ", ".join(f"{k}={v}" for k, v in sorted(roles.items()))
        + f", vendored-not-scanned={inv['vendored_files_not_scanned']}"
    )
    pragmas = sorted({p for f in inv["files"] for p in f["pragmas"]})
    out.append(f"pragmas: {', '.join(pragmas) or 'none'}")
    details: list[str] = []
    for f in inv["files"]:
        if f["role"] not in ("production", "interface"):
            continue
        for c in f["contracts"]:
            bases = f" is {', '.join(c['bases'])}" if c["bases"] else ""
            hints = f" [{'; '.join(c['proxy_hints'])}]" if c["proxy_hints"] else ""
            details.append(
                f"{c['kind']} {c['name']}{bases} ({f['path']}:{c['location']['start_line']}"
                f"-{c['location']['end_line']}){hints}"
            )
            for v in c["state_vars"]:
                tag = " constant" if v["constant"] else " immutable" if v["immutable"] else ""
                details.append(f"  var {v['type']} {v['name']}{tag} @{v['line']}")
            for m in c["modifiers"]:
                details.append(
                    f"  modifier {m['name']} @{m['location']['start_line']} checks_sender={m['checks_sender']}"
                )
    out += _capped(details, "contracts")
    out.append("entry points (state-changing, least protected first):")
    entries: list[str] = []
    for e in sorted(inv["entry_points"], key=lambda e: (ACCESS_RISK.get(e["access"], 0), e["id"])):
        extra = []
        if e["modifiers"]:
            extra.append("mods=" + ",".join(e["modifiers"]))
        if e["state_writes"]:
            extra.append("writes=" + ",".join(e["state_writes"]))
        if e["external_calls"]:
            extra.append("calls=" + ";".join(e["external_calls"]))
        if e["flags"]:
            extra.append("flags=" + ",".join(e["flags"]))
        entries.append(
            f"  {e['id']} {e['visibility']} {e['mutability']} access={e['access']} "
            f"{e['location']} {' '.join(extra)}".rstrip()
        )
    out += _capped(entries, "entry points")
    notable = [
        (f, c, fn)
        for f in inv["files"]
        if f["role"] == "production"
        for c in f["contracts"]
        for fn in c["functions"]
        if fn["has_body"]
        and (fn["flags"] or fn["external_calls"])
        and f"{c['name']}.{fn['name'] or fn['kind']}" not in {e["id"] for e in inv["entry_points"]}
    ]
    if notable:
        out.append("other functions with external calls or flags:")
    others: list[str] = []
    for f, c, fn in notable:
        calls = ";".join(f"{x['kind']}:{x['target']}@{x['line']}" for x in fn["external_calls"])
        others.append(
            f"  {c['name']}.{fn['name'] or fn['kind']} {fn['visibility']} {fn['mutability']} "
            f"{f['path']}:{fn['location']['start_line']}-{fn['location']['end_line']}"
            + (f" calls={calls}" if calls else "")
            + (f" flags={','.join(sorted(fn['flags']))}" if fn["flags"] else "")
        )
    out += _capped(others, "other functions")
    out += [f"unresolved import: {u}" for u in inv["unresolved_imports"]]
    out += [f"skipped: {s['path']} ({s['reason']})" for s in inv["skipped"]]
    return "\n".join(out)
