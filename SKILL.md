---
name: agent-history
description: Look up what the user already did and decided in their OTHER coding agents - Claude Code, opencode, MiMo Code and Codex - for the current project - curated memories (Claude memory/*.md, MiMo project MEMORY.md, project AGENTS.md/PROMPT.md), recent sessions, keyword search across past conversations (Unicode and Arabic included), and the text of one session. Use at the start of work in a project, when the user refers to earlier work ("like last time", "we decided", "the run from yesterday", "the other session"), before re-deriving a decision, or when a number or rule needs its origin. Also use it to diagnose a missing source (doctor) or to add a new agent to the registry.
compatibility: Python 3.8+ stdlib only (sqlite3, json). Reads ~/.claude/projects, ~/.local/share/opencode/opencode.db, ~/.local/share/mimocode, ~/.codex and any configured override (all read-only).
---

# Other agents' history

The user works in several coding agents and switches between them. Their memories and transcripts already
contain decisions, corrections, run results and gotchas for most projects. Look before re-deriving, and cite
what you found.

```bash
H="python3 <skill_dir>/scripts/agent_history.py"
$H memories                        # curated memories for this project (cheap; do this first)
$H memories --print --max-chars 4000
$H sessions                        # recent sessions in every agent for this directory
$H search "self-destroy"           # keyword search, this project (add --all for everywhere, --days 14)
$H search "voice studio" --source codex     # one agent only
$H show claude <session-id> --grep "self-destroy"     # just the relevant turns of one session
$H show codex <thread-id> --grep "supabase"
$H doctor                          # which sources exist, where, and why one is missing
```

Output is deliberately short (snippets, caps) to save context. `doctor` is the first thing to run whenever a
source is missing or a search returns nothing unexpectedly.

## Scope: what "this project" means

Run from the project directory. From a repository root the whole repository counts. From a subdirectory you
get that subtree plus sessions that were started at the repository root, so a sibling project under the same
parent does not leak in; add `--repo` for the whole repository, `--all` for every project on the machine.

## Where things live

| Agent | Curated (read first) | Raw history (search only) |
|---|---|---|
| Claude Code | `~/.claude/projects/<slug>/memory/*.md`. Slug = absolute path with every non-alphanumeric char → `-`; Arabic folder names collapse to dashes (equal-length Arabic names can collide) | `~/.claude/projects/<slug>/*.jsonl` transcripts |
| MiMo Code | `~/.local/share/mimocode/memory/projects/<project-id>/MEMORY*.md`, `.../global/MEMORY.md` | `mimocode.db` (FTS5 index; MiMo imports Claude sessions, so hits can repeat and are deduped) |
| opencode | the project's own `AGENTS.md` / `PROMPT.md` | `opencode.db`: `session` → `message` → `part` (JSON, `$.type='text'`) |
| Codex | `~/.codex/AGENTS.md` (global) | `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl` (authoritative); `state_*.sqlite → threads` and `thread_history_*.sqlite → thread_items` are the fast indexes |

Non-git folders (Documents, Arabic book folders) live in a catch-all project in MiMo/opencode, so sessions are
matched by their recorded working directory rather than by project id.

## Codex specifics worth knowing

- **Versioned filenames.** `state_5.sqlite`, `thread_history_1.sqlite`: the number changes on upgrade, so the
  script globs and takes the highest, then falls back to scanning the rollout files.
- **Most threads are not the user's.** `thread_source` is `user`, `subagent` or `guardian_review` (automated
  security reviews). Guardian threads are hidden unless `--include-automated`.
- **A rollout is not a chat log.** Only `response_item`/`message` lines are conversation; `event_msg` mirrors
  them and `developer` is the system prompt. User turns are prefixed with `<environment_context>` wrappers.
- **Forked threads.** One conversation can appear as several threads (main plus teammate spawns); subagent
  threads are tagged `[subagent]`.

## Rules

- **Curated before raw.** Memories are small and deliberate; transcripts are huge. Read `memories` first, then
  `search` with a specific term. Never load a whole transcript; use `show --grep`.
- **Memories are background, not truth.** They describe what was true when written. Verify file paths, flags
  and numbers against the current code or data, and say when a memory is stale.
- **User corrections found there are binding** (for example "never commit without asking", "no co-author
  lines", project rules about data use). Follow them as if the user had just said them.
- **Read-only.** Never write to these databases or memory folders, and never open an agent's credential files
  (`auth.json`, `.credentials.json`, `account.json`, `config.toml`).
- **Say where it came from**: "Claude memory `feedback_commits.md`: …", "MiMo session ses_… on 2026-10-05: …",
  "Codex thread 01a1ca2b on 2026-11-11: …".

## When a source is missing

Follow `references/discovery.md`: run `doctor --json`, ask the user rather than guessing a path, use bounded
`--discover` only on roots they name, verify with `config --set` (it probes before saving), then re-run the
original lookup. Never invent a path and never write inside another agent's directory.

## Adding an agent

Sources are modular: one file in `scripts/sources/` with a `NAME` is registered automatically (see
`references/adding-agents.md`). Contributions need a fixture under `tests/fixtures/` and a row in the README.
