# jcron

Scheduling for agent sessions: work that waits for your next session, in whichever tool you open.

jcron lets an LLM schedule reminders, repeating tasks, condition checks and TODOs, then pick them up in a later session.
Jobs are plain YAML files in `~/.jcron/`, so people can read and edit them too.

## Why

Most coding work now happens inside an agent tool such as Claude Code or opencode.
Sessions are short, several run side by side, and each one starts with no memory of the others.
Follow-up work gets lost between them: "check CI tomorrow", "delete the branch once PR 42 merges", "write the standup notes every weekday".

Other schedulers belong to one place.
A calendar or phone reminder tells you, not the agent.
Chat app tasks stay in that app.
Cloud routines start a fresh, unattended agent run.
Scheduled prompts inside a session end when the session closes.

jcron jobs live outside every session and every tool:

- **Across sessions:** a job added today shows up in whichever session you open when it falls due.
- **Across tools:** any tool that supports MCP can read and act on the same jobs.
- **With the right tools at hand:** the session that picks up "check whether PR 42 is merged" can run `gh` itself, then do the follow-up work.
- **Scoped to your work:** each job belongs to a git repo, so a session only hears about jobs for the repo it is in. Other sessions stay undisturbed.
- **You stay in charge:** a session tells you what is due and asks before taking a job on.

There is no background process.
A Claude Code hook reports due jobs before each prompt, and an MCP server gives the LLM tools to act on them.

What jcron does not do:

- Nothing runs while no session is open. A job waits until you next start one. For work that should run unattended, use a cloud routine instead.
- Jobs live on one machine, in `~/.jcron/`.

## Where jobs belong

- A job belongs to the git repo it was added in: the main checkout, all its worktrees, every branch and every subfolder.
- Outside git, a job belongs to its exact folder only.
- The folder and branch a job was added from are recorded and shown, for information only.
- The hook and `due` list only the jobs for the repo the session is in. Jobs for other repos stay silent.
- Global TODOs show in every session.
- `jcron list` and `jcron due --all` still show everything.

## Shared jobs

Some jobs belong to a branch, not to one person, and another dev may pick them up later.
Add one with `--shared` (or `shared=true` on the MCP `add` tool) and it is saved in the repo's `.jcron/` folder instead of `~/.jcron/`.

- You commit the file with the branch. Anyone who checks out the branch sees the job when it is due.
- A shared job is listed only for the checkout that holds the file. Each worktree has its own.
- It does not record the folder or repo, since those are paths on one machine.
- There is no claim for a shared job. The session tells you what is due and asks before working on it.
- `done` marks the file as done and keeps it. You commit that change, so the other dev sees it is finished.
- At session start, finished shared jobs are listed as ready to delete. Once the done state is committed, delete the file and commit that.
- jcron and the LLM never commit. You do.
- Shared check jobs do not expire on their own. Cancel one that is no longer needed.

## Weekly cleanup

Jobs that only show in their own repo can be forgotten, so once a week jcron lists the stale ones from every repo and folder.
The first session start more than 7 days after the last report shows the list, wherever that session is.
A job is stale when:

- its folder is gone,
- its branch is gone, both locally and as a remote-tracking branch (no network is used),
- it is more than 14 days overdue, or was claimed more than 14 days ago and never finished,
- or it is an expired TODO.

The LLM shows you the list and asks about each job: cancel it, edit it, or keep it.
Nothing changes without your answer. A report you ignore still counts, so the next one comes a week later.

## How a due job is handled

1. The hook (or a `due` call) lists this repo's jobs whose time has come.
2. The LLM tells you about each one, reading its notes with `show`, and asks whether to take it on now.
3. Only if you say yes does it `claim` the job. The claim stops other open sessions from taking the same job.
4. When the work is finished, it calls `done`. A repeat job moves to its next run.
5. If you say not now, it can `snooze` the job, or leave it for another session.

Check jobs are the exception for step 2: the LLM tests the condition without asking, since testing changes nothing.
Once the condition is met, the job becomes a normal task and the LLM asks before acting on it.

## Install

jcron needs Python 3.11 or newer.

```
uv tool install git+https://github.com/simonwittber/jcron
```

This puts the `jcron` command on your PATH.
From a clone of this repo, `uv tool install .` or `pip install .` works too.

## Set up Claude Code

Register the MCP server for all projects:

```
claude mcp add --scope user jcron jcron mcp
```

Check it with `claude mcp get jcron`: the command should be `jcron` with the argument `mcp`.
On Windows PowerShell, avoid writing `claude mcp add ... -- jcron mcp`. PowerShell can drop the `--` and the arguments after it, which registers the server with no arguments.

Add the hook that reports due jobs (it shows the change and asks before writing `~/.claude/settings.json`):

```
jcron install-hook
```

The hook runs `jcron due --hook` on `SessionStart` and `UserPromptSubmit`.
It reads local files and asks git which repo the session is in. It runs in a fraction of a second, and prints nothing when no new jobs are due for this repo.
Each due job is reported once per session, and again after a session start, resume or compaction.
When something is due, you see a one-line summary in the terminal straight away, and the LLM gets the full list.

## Set up opencode

Add the MCP server to `~/.config/opencode/opencode.json` (or `opencode.json` in a project):

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "jcron": {
      "type": "local",
      "command": ["jcron", "mcp"],
      "enabled": true
    }
  }
}
```

There is no hook for opencode yet.
The server instructions tell the model to call `due` at the start of a session, but nothing reminds it later in the session.
Ask "anything due in jcron?" to check by hand.

## Job kinds

- **reminder:** due once, at a set time.
- **repeat:** due on a cron rule, such as `0 9 * * 1-5` (9am on weekdays). Finishing one run schedules the next.
- **check:** a plain-text condition, such as "PR 42 is merged", checked on an interval. The LLM tests the condition with its own tools and reports back. Once the condition is met, the job becomes a normal due task.
- **todo:** something to do some time, with no due time. It belongs to a folder, or is global. It expires after 30 days unless you give another time.

## TODOs

Start a message with `todo:` and the LLM adds a TODO, for example:

```
todo: the hook test is flaky on Windows, look into it
todo: global, renew the code signing cert
```

- The LLM writes the title and notes from the conversation, so a later session knows what to do and why.
- A TODO belongs to the current repo, like any job (see [Where jobs belong](#where-jobs-belong)). It is global only when your wording says so, and then it shows in every folder.
- The git branch is always recorded, for context.
- At session start, the hook (or a `due` call) lists TODOs for the current repo, and global ones. With more than 3, it shows a count and the LLM asks whether to list them.
- TODOs that expire within 3 days are always listed, with a warning. The LLM offers to extend them.
- An expired TODO is never removed on its own. It is listed every session until you confirm, then the LLM cancels it (or extends it).
- Working on a TODO follows the same steps as any job: the LLM asks before claiming it.

## Commands

```
jcron add reminder "Look at CI" --at "tomorrow 9am" --notes "..."
jcron add repeat "Standup notes" --cron "0 9 * * 1-5"
jcron add check "Delete branch" --condition "PR 42 is merged" --every 30m --expires "in 2 weeks" --notes "..."
jcron add todo "Fix the flaky hook test" [--expires "in 2 weeks"] [--global] --notes "..."
jcron add reminder "Promote the build" --at "in 2 weeks" --shared --notes "..."
jcron list [--all] [--folder X]
jcron todos [--folder X] [--all]
jcron show <id>
jcron due [--all]
jcron claim <id>
jcron release <id> [--notes ...]
jcron done <id> [--notes ...]
jcron check <id> --met | --not-yet
jcron snooze <id> --until "in 1h"
jcron cancel <id>
jcron edit <id> [--title ...] [--append ...] [--at ...] ...
```

- An id can be shortened to any unique start, for example `jcron show look-at`.
- Times accept `in 2h`, `+30m`, `tomorrow 9am`, `friday 14:00` or ISO times, and are stored in local time with the UTC offset.
- `--notes-file path` (or `-` for stdin) reads long notes from a file.
- `add` records the current folder, git branch and repo. `--folder` and `--branch` override the folder and branch.
- `due` lists jobs for the current repo (or folder, outside git). `--all` lists them for every repo and folder.

The MCP server exposes the same actions as tools: `add`, `list`, `show`, `due`, `claim`, `release`, `done`, `check`, `snooze`, `cancel`, `edit` and `todos`.
Its instructions tell the LLM when to check for due jobs and how to work through them.

## Storage

```
~/.jcron/
  jobs/<id>.yaml      active jobs
  claimed/<id>.yaml   jobs a session is working on
  done/<id>.yaml      finished, cancelled or expired jobs
  seen/<session>.txt  jobs the hook already reported to a session
  log.txt             one line per action
```

Set `JCRON_HOME` to use a different folder.

- A session claims a job (after you agree) by renaming its file, so two sessions cannot take the same job.
- A claim older than 4 hours counts as abandoned, and the job shows up as due again.
- Check jobs past their expiry move to `done/` with status `expired`.
- Expired TODOs stay in `jobs/` until you confirm their removal.
- Unknown keys added by hand are kept when jcron saves a job.

Example job file:

```yaml
id: delete-branch-once-pr-42-merges-484d
kind: check
title: Delete branch once PR 42 merges
status: waiting
created: 2026-10-06T12:32:07+08:00
folder: /home/me/code/myproject
branch: feature/hooks
due: 2026-10-06T13:02:07+08:00
condition: PR 42 on jcron is merged
check_every: 30m
expires: 2026-10-20T12:32:07+08:00
notes: |
  Run git push origin --delete feature/hooks.
  Then update the changelog.
```

## Development

```
uv sync
uv run pytest
```

## License

MIT. See [LICENSE](LICENSE).
