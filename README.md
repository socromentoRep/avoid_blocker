# avoid_blocker

Two small pieces of Claude Code infrastructure that make long-running
agent sessions more resilient against blockers.

1. **Cheatsheet hook** — `hooks/anti-block-inject.js`. A Claude Code hook
   that injects an arbitrary markdown file into agent sessions as
   `additionalContext`. Use it to give the agent a project-specific
   reference of ready-made tools (proxies, captcha solvers, scrapers,
   antidetect browsers) so it does not reinvent them under pressure.

2. **Account-fallback wrapper** — `wrapper/claude-with-fallback.sh`.
   Runs the `claude` CLI against one of two `CLAUDE_CONFIG_DIR` profiles.
   On rate-limit detection it sets a flag file and retries on the other
   account in the same invocation. Subsequent runs skip an account whose
   flag has not yet expired.

The two pieces are independent and can be deployed separately.

## Why hooks instead of editing the system prompt

Hooks attach to lifecycle events (`SessionStart`, `SubagentStart`, …) and
add `additionalContext` to the session without touching the project's
prompt files. That makes the cheatsheet:

- **Versionable separately** from prompt history
- **Easy to disable** (single hook entry in `settings.json`)
- **Project-agnostic** — the same hook binary serves any project, the
  cheatsheet content lives in a file you point at via env

## Hook usage

The hook reads its config from environment variables:

| var                              | required | meaning                                                  |
|----------------------------------|----------|----------------------------------------------------------|
| `ANTI_BLOCK_HOOK_CHEATSHEET`     | yes      | path to a markdown file injected as `additionalContext`  |
| `ANTI_BLOCK_HOOK_CWD_PREFIX`     | no       | only fire when `cwd` starts with this prefix             |
| `ANTI_BLOCK_HOOK_PROBE_PATH`     | no       | sanity-check path; hook skips if it does not exist       |

The hook is event-agnostic: the `hookEventName` in the response echoes
the input event, so the same file can be wired to `SessionStart`
**or** `SubagentStart` (or both — duplicate `additionalContext` is
harmless).

### settings.json wiring

Minimal example, see `examples/settings.minimal.json`:

```json
{
  "hooks": {
    "SessionStart": [{
      "matcher": "*",
      "hooks": [
        {
          "type": "command",
          "command": "node /path/to/hooks/anti-block-inject.js",
          "timeout": 3
        }
      ]
    }]
  }
}
```

Set the env vars in the shell that launches `claude` (e.g. in a wrapper
script, systemd unit, or `.env` loaded by your orchestrator).

### Cheatsheet format

Plain markdown. Anything that fits in ~1–2k tokens. Typical sections:

- **Tools available** — short table of shortcut scripts and what they
  solve, with stable identifiers (e.g. captcha IDs that do not rotate).
- **Decision tree** — "if you see error X, run tool Y first instead of
  retrying manually 10 times."
- **Pre-fetched hints** — locations where the agent can find prior probe
  results before making fresh requests.

Keep it terse — every line costs context. See
`examples/cheatsheet.example.md` for the structure.

## Wrapper usage

The wrapper expects two `CLAUDE_CONFIG_DIR` profiles already set up
locally (e.g. via `claude /login` for each).

```bash
export CLAUDE_CONFIG_DIR_1=/path/to/account1-config
export CLAUDE_CONFIG_DIR_2=/path/to/account2-config
export CLAUDE_ACCOUNT2_TOKEN=sk-ant-oat01-...        # OAuth token for acc2
export CLAUDE_PRIMARY_ACCOUNT=2                       # 1 or 2
export CLAUDE_RL_DURATION_SEC=18000                   # 5h flag default
export CLAUDE_NOTIFY_CMD=/usr/local/bin/notify.sh     # optional

./wrapper/claude-with-fallback.sh -p "your prompt" --output-format json
```

Flag files live in `/tmp/claude-acc{1,2}-ratelimited` and contain a
Unix epoch when the account becomes available again. Wrapper removes
expired flags automatically.

stdout from the underlying CLI is forwarded directly (no buffering),
so a SIGKILL on the wrapper does not lose the in-progress streaming
response.

### Why not always trust the wrapper's flag

The wrapper sets a flag based on its own 5h timer when it sees a
rate-limit error in stderr. This is a conservative default — if the
real reset time is shorter, the wrapper waits too long; if the real
reset is longer (e.g. weekly Sonnet limit), the wrapper revives the
account too early and gets re-blocked.

For a more accurate flag, parse the actual `resetsAt` from the Claude
stream-json `rate_limit_event` and write that epoch to the flag file
before the wrapper notices the error. Example logic in your scan
runner:

```bash
RL_INFO=$(grep -E '"rate_limit_event"' "$CLAUDE_JSON" | tail -1)
RESET=$(printf '%s' "$RL_INFO" | python3 -c "import sys,json; d=json.loads(sys.stdin.read()); print(int(d.get('rate_limit_info',{}).get('resetsAt') or 0))")
if [ -n "$RESET" ] && [ "$RESET" -gt "$(date +%s)" ]; then
    echo "$RESET" > /tmp/claude-acc${ACC}-ratelimited
fi
```

## Install

```bash
git clone git@github.com:socromentoRep/avoid_blocker.git
cd avoid_blocker
bash deploy.sh                              # uses defaults
# or:
HOOKS_DIR=$HOME/.claude/hooks WRAPPER_DIR=$HOME/bin bash deploy.sh
```

`deploy.sh` is idempotent — re-run after pulling updates. It only
copies the hook and wrapper; it does not touch any `settings.json`.

## Files

```
avoid_blocker/
├── hooks/
│   └── anti-block-inject.js          # the hook itself
├── wrapper/
│   └── claude-with-fallback.sh       # account-fallback wrapper
├── examples/
│   ├── cheatsheet.example.md         # cheatsheet structure example
│   └── settings.minimal.json         # minimal hook wiring
├── deploy.sh
├── .gitignore
└── README.md
```

## License

Internal tooling. No license set — adopt one before sharing externally.
