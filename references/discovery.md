# When a source is missing

`agent_history.py doctor` answers three questions per source: where it looked, what it found, and whether
that thing has the shape this skill expects. Run it before concluding that another agent has no history.

```bash
python3 <skill_dir>/scripts/agent_history.py doctor
python3 <skill_dir>/scripts/agent_history.py doctor --json
```

| status | meaning | what to do |
|---|---|---|
| `ok` | path exists and the schema looks right | nothing |
| `missing` | no data at the resolved path | ask the user; then `--discover`, then `config --set` |
| `unreadable` | the file exists but cannot be opened | permissions, a mount that is not connected, or the agent is mid-upgrade |
| `schema_mismatch` | found the file, but not the tables/files expected | the agent changed its format; the source module needs updating (see `adding-agents.md`) |
| `load_error` | the source module itself failed to import | a broken contribution; the other sources still work |

## Discovery protocol

Work through these steps in order. Do not skip to step 3 with a guessed path: a wrong path persisted in the
config file defeats the whole point of `doctor`.

1. **Look first.** `doctor --json`. If the status is `ok`, stop; the problem was the query, not the path.
2. **Ask.** If a source is `missing` and the user mentioned that agent, ask where it keeps its data, offering
   the platform default from `doctor` as the first suggestion. Users who moved a data directory know it.
3. **Scan narrowly.** Only with a root the user named (or an obvious candidate such as another home, a
   mounted disk, `D:` on Windows):

   ```bash
   python3 <skill_dir>/scripts/agent_history.py doctor --discover --search-root /mnt/data
   ```

   Discovery looks at names only, never file contents, prunes `.git`, `node_modules`, caches and Trash, and
   stops at bounded depth. `strong` means the expected folder name is in the path; `weak` means only the file
   name matched.
4. **Verify before trusting.** `config --set <source>=<path>` probes the candidate and refuses a missing or
   mismatched one. If it refuses, report the exact detail (`schema_mismatch: missing tables: part`) instead of
   forcing it. `--force` exists for the rare case where the user knows better.
5. **Persist and retry.** `doctor --discover --save` stores the first verified `strong` candidate; or use
   `config --set`. Then re-run the lookup that failed so the user actually gets their answer.
6. **Record it.** Say what you configured and where the override lives
   (`$XDG_CONFIG_HOME/agent-history/config.json`); keep it in project memory so nobody is asked twice.

## Precedence

Highest wins:

1. `AGENT_HISTORY_<NAME>` (e.g. `AGENT_HISTORY_OPENCODE`, `AGENT_HISTORY_CODEX`)
2. the agent's own variable: `CLAUDE_CONFIG_DIR`, `CODEX_HOME`, `MIMOCODE_HOME`,
   `AGENT_HISTORY_OPENCODE_DB`, `AGENT_HISTORY_MIMO_DB`, `AGENT_HISTORY_MIMO_MEM`
3. `config.json` (written by `config --set`)
4. the platform default: `~/.claude`, `~/.codex`, `$XDG_DATA_HOME`, `~/Library/Application Support`,
   `%APPDATA%` / `%LOCALAPPDATA%`

Use an environment variable for a temporary or per-shell override; use `config --set` for a permanent one.
`config --unset <source>` returns to the platform default.

## Rules

- **Never invent a path.** A plausible-looking default that does not exist produces empty results that look
  like "no history", which is exactly the failure this command exists to prevent.
- **Never write inside another agent's directory.** The only file this skill writes is its own config.
- **Never open credentials** (`auth.json`, `.credentials.json`, `account.json`, `config.toml`) and never
  suggest reading them to "check" an installation.
- **Do not scan `/`, a network mount, or a whole disk** unless the user explicitly asks for that root. A scan
  is read-only, but it is slow and it is their machine.
- **Report what you found** even when it is a dead end: "no `opencode.db` under /mnt/data; is opencode
  installed elsewhere?" is more useful than silence.
