# agent-history

Look up what you already did and decided in your **other** coding agents — Claude Code, opencode, MiMo Code
and Codex — without leaving the one you are in.

Your memories and transcripts already contain the decisions, corrections, run results and gotchas for most
projects. This skill reads them read-only and returns short, cited snippets:

```
$ agent_history.py memories
[claude] ~/.claude/projects/-home-me-work-api/memory/feedback_commits.md  (847 B, scope /home/me/work/api)
[mimo]   ~/.local/share/mimocode/memory/projects/cc6f.../MEMORY.md       (8.7 KB, scope /home/me/work/api)
[mimo-global] .../memory/projects/global/MEMORY.md                       (3.4 KB, scope /)

$ agent_history.py search "retry budget" --days 30
2026-11-13 13:56  codex    01a1d4c1-ffe5-7f10-8b  assistant …the retry budget is 3 attempts with jitter, and it lives in…
2026-11-09 10:50  claude   b8a60721-d417-41e4-b2  user      we agreed the retry budget stays at 3, not 5
-- 2 hit(s); `show <source> <session>` for context

$ agent_history.py show codex 01a1d4c1 --grep "retry budget"
[assistant] …the retry budget is 3 attempts with jitter…
```

## Install

As a skill (Claude Code and compatible runtimes):

```bash
npx skills add khengari77/agent-history
```

Or copy the folder into your skills directory:

```bash
git clone https://github.com/khengari77/agent-history
cp -r agent-history ~/.claude/skills/
```

Requirements: Python 3.8+, standard library only. No network at runtime. Nothing is installed into your
agents' directories.

## Commands

| Command | Answers |
|---|---|
| `memories [--print] [--max-chars N]` | "what did we already decide here?" — curated memory and instruction files, cheap to read first |
| `sessions [--limit N] [--json]` | "what have I done in this project?" — recent sessions across every agent |
| `search QUERY [--all] [--days N] [--source LIST] [--json]` | "where did we discuss X?" — keyword search, Unicode/Arabic included, duplicate imports removed |
| `show SOURCE SESSION [--grep RE] [--max-chars N]` | the conversation text of one session, without tool calls or output |
| `doctor [--json] [--discover] [--search-root DIR] [--save]` | where each source lives, whether it is usable, and why not |
| `config [--show] [--set name=path] [--unset name]` | persistent overrides for unconventional installs |

`--dir` defaults to the current directory. `--include-automated` (alias `--codex-all`) includes automated
security-review threads in Codex.

## What "this project" means

From a repository root the whole repository counts. From a subdirectory you get that subtree plus sessions
started at the repository root, so a sibling project under the same parent does not leak in:

- `--repo` — the whole git repository
- `--all` — every project on the machine

## Sources

| Agent | Curated | Raw history |
|---|---|---|
| Claude Code | `~/.claude/projects/<slug>/memory/*.md` | `~/.claude/projects/<slug>/*.jsonl` |
| opencode | project `AGENTS.md` / `PROMPT.md` | `opencode.db`: session → message → part |
| MiMo Code | `.../mimocode/memory/projects/<id>/MEMORY*.md`, `global/` | `mimocode.db` with its FTS5 index |
| Codex | `~/.codex/AGENTS.md` | `sessions/YYYY/MM/DD/rollout-*.jsonl`, indexed by `state_*.sqlite` / `thread_history_*.sqlite` |

Paths resolve in this order: `AGENT_HISTORY_<NAME>` → the agent's own variable (`CLAUDE_CONFIG_DIR`,
`CODEX_HOME`, …) → `config.json` → platform default (XDG on Linux, Application Support on macOS,
`%APPDATA%` on Windows).

## When a source is missing

```bash
agent_history.py doctor                 # what is missing, and why
agent_history.py doctor --discover --search-root /mnt/data
agent_history.py config --set opencode=/mnt/data/opencode/opencode.db
```

`--discover` inspects names only, prunes build folders and caches, and never saves anything that `probe`
rejects. The full procedure — written for an agent to follow — is in
[`references/discovery.md`](references/discovery.md).

## Adding an agent

One file in `scripts/sources/`:

```python
NAME = "myagent"
CANDIDATES = ("{data}/myagent/sessions",)

def probe(path): ...      # does it exist, is it the shape I expect?
def sessions(path, roots, limit, include_all=False): ...
def search(path, roots, pat, query, since_ms, limit, include_all=False): ...
```

It is registered automatically, appears in `doctor`, and is accepted by `--source`. See
[`scripts/sources/_template.py`](scripts/sources/_template.py) and
[`references/adding-agents.md`](references/adding-agents.md).

## Privacy and safety

- Every database is opened `mode=ro`; nothing is written outside `$XDG_CONFIG_HOME/agent-history/config.json`.
- Credential files (`auth.json`, `.credentials.json`, `account.json`, `config.toml`) are never opened.
- No network access. No telemetry.
- Output is capped and snippets are short, because the caller's context window is the scarce resource.

## Development

```bash
python3 -m unittest discover -s tests
```

The suite builds a temporary HOME with synthetic Claude/opencode/MiMo/Codex data, so it never touches your
real history and proves the lookups work on a machine that is not yours.

## License

MIT
