# Codex entry point

**Read `AGENT.md` in full before beginning work.** It is the shared operating guide for all coding assistants.

Then read **`RULES.md` in full** (the canonical technical specification) and **`PROGRESS.md`** (the cross-model handoff/status file). If `PROGRESS.md` is missing, create it using the template in `AGENT.md` before implementation.

**Git is part of the required workflow:** at session start inspect Git and run `git pull --ff-only` when the worktree is clean and an upstream is configured; after verified milestones update `PROGRESS.md`, commit intentional changes, and run `git push`. Follow the detailed safety/exception rules in `AGENT.md`; never discard work or force-push.

Follow the startup, verification, progress-update and handoff requirements in `AGENT.md`. Do not assume any work has been completed until verified against repository files and actual commands.
