"""Where each agent keeps its data: platform defaults, environment overrides, saved overrides, discovery.

Resolution order, highest first:

1. AGENT_HISTORY_<NAME>          (portable, works for any source)
2. the source's own variable     (CLAUDE_CONFIG_DIR, CODEX_HOME, ...) via the module's ENV tuple
3. ~/.config/agent-history/config.json  (written by `config --set`, for unconventional installs)
4. the module's CANDIDATES for this platform

Nothing here writes outside the agent-history config file. Discovery only reads directory names and then
asks the source module to probe the candidate before anything is saved.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

APP = "agent-history"
CONFIG_VERSION = 1

# Directories that never contain agent data and can be enormous. Pruned during discovery.
PRUNE = {
    ".git", "node_modules", "__pycache__", ".cache", "Caches", "Trash", ".Trash",
    ".Trash-1000", "venv", ".venv", "env", "site-packages", "dist-packages", "target",
    "build", "dist", ".gradle", ".m2", ".npm", ".cargo", ".rustup", ".nvm", ".pyenv",
    "snap", ".local/share/Steam", "proc", "sys", "dev",
}
MAX_DEPTH = 6
MAX_VISITED = 200_000
MAX_CANDIDATES = 8


@dataclass
class Resolved:
    name: str
    path: Path | None
    origin: str  # env:VAR | config | default | none


@dataclass
class Candidate:
    path: Path
    confidence: str  # strong | weak
    note: str = ""


# ------------------------------------------------------------------ platform tokens
def _tokens():
    home = Path.home()
    if sys.platform == "darwin":
        support = home / "Library" / "Application Support"
        data = Path(os.environ.get("XDG_DATA_HOME") or support)
        config = Path(os.environ.get("XDG_CONFIG_HOME") or support)
        appdata = localappdata = None
    elif os.name == "nt":
        appdata = Path(os.environ.get("APPDATA") or home / "AppData" / "Roaming")
        localappdata = Path(os.environ.get("LOCALAPPDATA") or home / "AppData" / "Local")
        data, config, support = localappdata, appdata, None
    else:
        data = Path(os.environ.get("XDG_DATA_HOME") or home / ".local" / "share")
        config = Path(os.environ.get("XDG_CONFIG_HOME") or home / ".config")
        support = data
        appdata = localappdata = None
    return {
        "home": home,
        "data": data,
        "config": config,
        "appsupport": support,
        "appdata": appdata,
        "localappdata": localappdata,
    }


def expand(template):
    """'{home}/.codex' -> Path, filling platform tokens. None when the token cannot be resolved here."""
    if not template:
        return None
    out = template
    for key, value in _tokens().items():
        if value is None and "{" + key + "}" in out:
            return None
        if value is not None:
            out = out.replace("{" + key + "}", str(value))
    return None if "{" in out else Path(out)


def candidates(mod):
    return [p for p in (expand(t) for t in getattr(mod, "CANDIDATES", ())) if p is not None]


# ------------------------------------------------------------------ config file
def config_home():
    return expand("{config}") / APP


def config_path():
    return config_home() / "config.json"


def load_config():
    p = config_path()
    try:
        data = json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        return {"version": CONFIG_VERSION, "sources": {}}
    if not isinstance(data.get("sources"), dict):
        data["sources"] = {}
    return data


def save_config(data):
    p = config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    tmp.replace(p)
    return p


def set_source(name, path):
    data = load_config()
    data.setdefault("sources", {})[name] = {"path": str(Path(path).expanduser().resolve())}
    return save_config(data)


def unset_source(name):
    data = load_config()
    data.get("sources", {}).pop(name, None)
    return save_config(data)


# ------------------------------------------------------------------ resolution
def _from_env(mod, value):
    fn = getattr(mod, "from_env", None)
    return fn(value) if fn else Path(value).expanduser()


def resolve(mod):
    var = "AGENT_HISTORY_" + mod.NAME.upper().replace("-", "_")
    if os.environ.get(var):
        return Resolved(mod.NAME, _from_env(mod, os.environ[var]), f"env:{var}")
    for name in getattr(mod, "ENV", ()):
        if os.environ.get(name):
            return Resolved(mod.NAME, _from_env(mod, os.environ[name]), f"env:{name}")
    saved = load_config().get("sources", {}).get(mod.NAME, {}).get("path")
    if saved:
        return Resolved(mod.NAME, Path(saved).expanduser(), "config")
    found = candidates(mod)
    if found:
        existing = [p for p in found if p.exists()]
        return Resolved(mod.NAME, existing[0] if existing else found[0], "default")
    return Resolved(mod.NAME, None, "none")


def resolve_all(mods):
    return {mod.NAME: resolve(mod) for mod in mods}


# ------------------------------------------------------------------ discovery
def discover(mod, roots, max_depth=MAX_DEPTH, max_candidates=MAX_CANDIDATES):
    """Bounded scan for a source's data in non-standard locations.

    Only names are inspected, never file contents; a candidate is returned as `strong` when the source's
    hint appears in the path (e.g. an `opencode` directory holding opencode.db) and `weak` otherwise.
    Callers must probe before saving.
    """
    find = getattr(mod, "FIND", {}) or {}
    files = tuple(n.lower() for n in find.get("files", ()))
    dirs = tuple(n.lower() for n in find.get("dirs", ()))
    hint = (find.get("hint") or "").lower()
    if not files and not dirs:
        return []

    out, seen, visited = [], set(), 0
    for root in roots:
        root = Path(root).expanduser()
        if not root.is_dir():
            continue
        for cur, subdirs, filenames in os.walk(root):
            visited += 1
            if visited > MAX_VISITED:
                return out
            depth = len(Path(cur).relative_to(root).parts)
            if depth >= max_depth:
                subdirs[:] = []
            subdirs[:] = [d for d in subdirs if d not in PRUNE and not d.startswith(".venv")]
            entries = [(Path(cur) / f, "file") for f in filenames if f.lower() in files]
            entries += [(Path(cur) / d, "dir") for d in subdirs if d.lower() in dirs]
            for path, kind in entries:
                if path in seen:
                    continue
                seen.add(path)
                chain = {p.name.lower() for p in [path, *path.parents][:5]}
                strong = bool(hint) and hint in chain
                out.append(Candidate(path, "strong" if strong else "weak",
                                     "name + expected folder" if strong else "name match only"))
                if len(out) >= max_candidates:
                    return out
    return out
