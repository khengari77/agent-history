"""Source registry: every module in this folder that declares NAME is a source.

Dropping a new file here is all it takes to add an agent. Import failures are captured rather than
raised, because one half-finished contribution must not take down the sources that already work; the
CLI reports them through `doctor`.
"""
from __future__ import annotations

import importlib
import pkgutil

from sources import base

# Preferred display/merge order. Anything not listed sorts alphabetically after these.
ORDER = {"claude": 0, "opencode": 1, "mimo": 2, "codex": 3}

_cache = None


def load_all():
    """(sources, errors): imported modules sorted for stable output, and modules that failed to load."""
    global _cache
    if _cache is not None:
        return _cache
    mods, errors = [], []
    for info in pkgutil.iter_modules(__path__):
        if info.name.startswith("_") or info.name == "base":
            continue
        try:
            mod = importlib.import_module(f"{__name__}.{info.name}")
        except Exception as exc:  # noqa: BLE001 - a broken source is data, not a crash
            errors.append((info.name, f"{type(exc).__name__}: {exc}"))
            continue
        if not getattr(mod, "NAME", None):
            errors.append((info.name, "missing NAME"))
            continue
        missing = [f for f in ("probe", "sessions", "search") if not hasattr(mod, f)]
        if missing:
            errors.append((info.name, "missing required function(s): " + ", ".join(missing)))
            continue
        for cap in ("memories", "show"):
            if not hasattr(mod, cap):
                setattr(mod, cap, getattr(base, cap))
        mods.append(mod)
    mods.sort(key=lambda m: (ORDER.get(m.NAME, len(ORDER)), m.NAME))
    _cache = (mods, errors)
    return _cache


def names():
    return [m.NAME for m in load_all()[0]]


def get(name):
    for mod in load_all()[0]:
        if mod.NAME == name:
            return mod
    return None


def parse(spec):
    """'all' or a comma-separated list of source names; unknown names are an error the caller reports."""
    known = names()
    wanted = known if spec in (None, "", "all") else [s.strip() for s in spec.split(",") if s.strip()]
    unknown = [s for s in wanted if s not in known]
    return wanted, unknown
