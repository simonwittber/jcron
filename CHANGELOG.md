# Changelog

All notable changes to jcron are listed here.
Each release on GitHub also has notes generated from its commits.

## Unreleased

### Fixed
- A broken job file now gives a one-line error naming the file, instead of a traceback.
- Job ids may only contain letters, digits, `_` and `-`, so an id can no longer point at a file outside `~/.jcron/`.
- A check job's interval (`every`) must be longer than zero.

## 0.1.0 (2026-10-06)

### Added
- Reminders, repeating tasks and condition checks that LLM sessions pick up later.
- Jobs stored as YAML files in `~/.jcron/`, with a CLI, an MCP server and a session-start hook.
- Sessions ask the user before claiming a due job.
- TODOs: a job kind with no due time, tied to a folder (or global) and its git branch, expiring after 30 days by default.
- Session start lists TODOs for the current folder and warns about ones expiring soon or already expired.
- `todos` MCP tool, `jcron todos` command, and `jcron add todo --global`.
- A message starting with "todo:" asks the session to add a TODO.
- Release workflow: pushing a `v*` tag builds the package and creates a GitHub release.
