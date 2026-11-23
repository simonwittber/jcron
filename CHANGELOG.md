# Changelog

All notable changes to jcron are listed here.
Each release on GitHub also has notes generated from its commits.

## Unreleased

### Added
- Shared jobs: `jcron add --shared` (and `shared=true` on the MCP `add` tool) saves a job in the repo's `.jcron/` folder, to be committed with the branch so another dev can pick it up.
- A finished shared job keeps its file. Session start lists it as ready to delete, once the user has committed the done state.

## 0.2.0 (2026-11-16)

### Changed
- Jobs belong to a git repo: its main checkout, worktrees, branches and subfolders. Outside git, a job belongs to its exact folder.
- The hook and `due` list only the current repo's jobs and TODOs. Sessions in other repos are no longer told about them.
- Jobs record the repo they were added in (`repo`). Older jobs without it are matched through their folder.

### Added
- A weekly cleanup report at session start lists stale jobs from every repo: folder gone, branch gone, more than 14 days overdue, or an expired TODO. The user decides what to do with each one.
- `jcron due --all`, and `all_folders` on the MCP `due` tool, list due jobs from every repo and folder.

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
