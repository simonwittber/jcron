# Shared jobs in source control: key notes

Status: first version implemented (manual delete, no git check).

## The need

- A job sometimes belongs to a branch, not to one person.
- Example: a promotion that must happen in the future, which another dev may handle.
- Today, jobs live in `~/.jcron/` on one machine, so a teammate never sees them.

## Decisions so far

- **Team size:** 1 or 2 devs. No crowd of duplicate reminders to worry about.
- **Scope:** jobs are specific to a branch.
- **Where jobs live:** a `.jcron/` folder in the repo, committed on the work branch.
- **No special branch.**
  A side branch would not follow the work branch, and it needs fetching and push access.
- **Handoff:** the other dev gets the job by checking out the branch.
- **Cleanup:** deleting the branch removes the job.

## Job lifecycle

1. `done` marks the job as done in its file.
2. The user commits that change. jcron and Claude only edit files and never commit.
3. A later commit deletes the file.

Why two steps: the other dev sees the job is done after pulling, and the history records the outcome.

## First version: fully manual

- jcron reads jobs from `~/.jcron/` and from the repo's `.jcron/` folder.
- At session start, done files in `.jcron/` are listed as "ready to delete".
- The user deletes the file and commits.

## Left out for now

- No git check for whether the done state is committed.
- No warning when a branch with a leftover `.jcron/` file is about to merge to main.
- Add these only if the manual version proves annoying.

## Open points

- Claim state stays local to one machine. Fine for 1 or 2 devs, but confirm this in real use.
- If a `.jcron/` file reaches main by accident, it stays there until deleted.
  Harmless, but untidy.
- Folder name and file format: reuse the existing job YAML as is, or add a field (for example an owner)?
- How a repo job is told apart from a personal job in `due`, `list` and `show`.
- How the existing repo ownership rule (a job belongs to a git repo) applies to a job stored inside that repo.
