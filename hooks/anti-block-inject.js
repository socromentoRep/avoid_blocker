#!/usr/bin/env node
/**
 * Claude Code hook — injects a project-specific cheat-sheet into agent
 * sessions when CWD matches a configured prefix.
 *
 * Designed to be wired to either `SessionStart` or `SubagentStart`. The
 * `hookEventName` field is read from the input JSON and echoed back so a
 * single hook file works for both events without changes.
 *
 * Configuration via env vars:
 *   ANTI_BLOCK_HOOK_CHEATSHEET   path to a markdown file whose contents
 *                                 are injected as `additionalContext`.
 *                                 Required.
 *   ANTI_BLOCK_HOOK_CWD_PREFIX   only fire when input cwd starts with this
 *                                 prefix. Optional. If unset, fires for any
 *                                 cwd.
 *   ANTI_BLOCK_HOOK_PROBE_PATH   optional sanity-check path. If set and the
 *                                 path does not exist, the hook exits silently
 *                                 (useful as a "framework not installed" guard).
 *
 * Failure modes are silent (`process.exit(0)` with empty stdout) so a broken
 * hook never blocks Claude Code startup.
 */

const fs = require('fs');

const CHEATSHEET_PATH = process.env.ANTI_BLOCK_HOOK_CHEATSHEET || '';
const CWD_PREFIX = process.env.ANTI_BLOCK_HOOK_CWD_PREFIX || '';
const PROBE_PATH = process.env.ANTI_BLOCK_HOOK_PROBE_PATH || '';

async function main() {
  let hookData;
  try {
    let input = '';
    for await (const chunk of process.stdin) { input += chunk; }
    if (!input.trim()) process.exit(0);
    hookData = JSON.parse(input);
  } catch { process.exit(0); }

  try {
    if (!CHEATSHEET_PATH) process.exit(0);

    const cwd = hookData?.cwd || '';
    if (CWD_PREFIX && !cwd.startsWith(CWD_PREFIX)) process.exit(0);

    if (PROBE_PATH) {
      try { fs.accessSync(PROBE_PATH); } catch { process.exit(0); }
    }

    let cheatsheet;
    try {
      cheatsheet = fs.readFileSync(CHEATSHEET_PATH, 'utf-8');
    } catch { process.exit(0); }

    const eventName = hookData?.hook_event_name || 'SessionStart';

    process.stdout.write(JSON.stringify({
      hookSpecificOutput: {
        hookEventName: eventName,
        additionalContext: cheatsheet,
      },
    }));
    process.exit(0);
  } catch { process.exit(0); }
}

main();
