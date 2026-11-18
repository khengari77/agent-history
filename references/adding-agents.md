# Adding an agent

A source is one module in `scripts/sources/` that declares `NAME`. `sources/__init__.py` imports every such
module on start, so registration is automatic: no CLI changes, no list to update. A module that fails to
import is reported by `doctor` as `load_error` and does not affect the others.

## The contract

| Required | Purpose |
|---|---|
| `NAME` | registry key, also what `--source` and `config --set` use |
| `TITLE` | human name for docs and `doctor` |
| `CANDIDATES` | where the data usually lives, with `{home}` `{data}` `{config}` `{appsupport}` `{appdata}` `{localappdata}` tokens |
| `probe(path)` | `base.Probe(status, detail, counts)`; `ok` / `missing` / `unreadable` / `schema_mismatch` |
| `sessions(path, roots, limit, include_all)` | `list[base.Session]`, newest first is not required (the CLI sorts) |
| `search(path, roots, pat, query, since_ms, limit, include_all)` | `list[base.Hit]`; `pat` is the compiled regex for `query` |

Optional, with working defaults from `sources/base.py`:

| Optional | Default |
|---|---|
| `memories(path, roots, budget)` | raises `NotSupported` → "does not keep curated memory files" |
| `show(path, session_id)` | raises `NotSupported` → "cannot replay a session" |
| `ENV`, `from_env(value)` | none; the variable is treated as a path |
| `FIND`, `NEVER_OPEN`, `KINDS` | no discovery; no credential names; informational |

`roots` is `base.Roots(exact=[...], trees=[...])` or `None` for `--all`. Use `util.dir_clause(column, roots)`
for SQL and `roots.contains(path)` for file-based sources rather than inventing your own matching; that is
what keeps a subdirectory from swallowing sibling projects.

## Step by step

1. Copy `scripts/sources/_template.py` to `scripts/sources/<name>.py` (no leading underscore, or it stays
   unregistered).
2. Fill in the constants. Use `CANDIDATES` tokens, never a hardcoded home path.
3. **Implement `probe` first** and run `doctor --source <name>`. It is the fastest feedback loop and the only
   function the rest of the tool trusts to decide whether a path is real. Check the tables/files you need,
   not just that the file exists.
4. Implement `sessions`, then `search`, then `show`. Skip `memories`/`show` when the agent has no such
   concept; the CLI says so instead of failing.
5. Add a fixture: build a tiny synthetic copy of the agent's data under `tests/support.py` (see `_claude`,
   `_opencode`, `_mimo`, `_codex`) and assert discovery, ordering and search in a `tests/test_*.py`.
6. Add a row to the table in `README.md` and in `SKILL.md`.
7. `python3 -m unittest discover -s tests` must stay green.

## Checklist

- **Read-only.** `util.open_ro` for databases. Never create, migrate or write anything in the agent's folder.
- **Credentials.** List every credential/config filename in `NEVER_OPEN` and never read it.
- **Conversation only.** `show` returns user/assistant text; strip tool calls, tool results, system prompts
  and injected wrappers (see `codex.strip_wrappers`).
- **Short output.** Use `util.snip` and respect `limit`; the caller's context window is the scarce resource.
- **Dedupe in the CLI, not the module.** Some agents import each other's sessions; the CLI removes identical
  snippets across sources.
- **Time.** Normalise to epoch milliseconds for `Session.updated_ms` and to a printable string for
  `Hit.when` (`util.ts`, `util.iso_ms`).
- **Unicode.** Regex matching is case-insensitive but must not assume ASCII; Arabic queries must work.
  (SQLite `LIKE` is ASCII-only case-insensitive, which is harmless for Arabic.)
- **Performance.** Never load a whole transcript into memory per query. Stream jsonl, cap sqlite results,
  and skip files older than `since_ms` before opening them.
- **`probe` must be cheap** — it runs on every `doctor`, including in CI with no data present.

## When an agent changes its format

`probe` is the contract with reality. If an upgrade renames a table or moves a directory, `doctor` reports
`schema_mismatch` with the missing name, nothing silently returns zero rows, and the fix is usually confined
to the `REQUIRED` list and one query in that module. Keep version-specific handling in the module (Codex
globs `state_*.sqlite` and reads `pragma table_info` rather than assuming columns).
