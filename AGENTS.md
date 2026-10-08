# AGENTS.md - claude-handoff-web

Guide for AI agents working in this repository. Pair with `CLAUDE.md` (the working agreement and
hook-enforced rules). Keep this file current when the build, layout, or public API changes.

## What this is

A small self-updating review and sign-off site for handing work to a human: chips, live updates,
Yes/No/Changes reviews, checklists with blockers.

It ships a template (`template/`) that `install.sh` copies into a working folder, plus a fake `example/`.
The two things to know before changing it:

- **An instance is never a repository.** A running site is working memory. Never `git init` one, never
  commit one, and never copy a live page, `_status.json` or `_saved/` into this repo. The rules for agents
  running an instance are in `template/AGENTS.md` (copied as `CLAUDE.md` and `AGENTS.md` into every
  instance); read them before running one.
- **Nothing is hard-coded about people or projects.** Every name, folder, host, port and timezone comes from
  the instance's `site.json`. Keep the template and the example generic: no real names, hosts or addresses.

## Using claude-handoff-web

The contract a page relies on: `/_site/site.css`, `/_site/review.js` and `/_site/live.js` with the body
attributes in `template/_site/README.md`, the save API in `template/_site/SAVE-API.md`, and the
`_status.json` manifest per folder. Keep those stable; bump the `?v=` cache-buster when an asset changes.

## Layout

<!-- The directories that matter and what lives in each. Keep it short; point at the entry points. -->

- `template/` - what `install.sh` copies: `_site/` (assets, `serve.py`, `build-review.py`, docs),
  `gen-index.py`, and the instance `CLAUDE.md`/`AGENTS.md`
- `example/` - fake `site.json` and demo folders (a review page, a checklist, the guide copies)
- `docs/` - quick start, page types, operating notes
- `memory/` - the drop-in memory file for Claude sessions
- `install.sh` - installer (refuses git work trees)
- `tests/` - end-to-end tests against a real `serve.py` in a temp folder

## Build, test, lint

<!-- The exact commands. Pull these from package.json scripts (npm), the Taskfile (Go/Task), or
pyproject (Python) so they stay accurate. -->

- Build: none (plain files)
- Test: `uv run pytest` (starts `serve.py` on a free port in a temp folder)
- Lint: `uv run ruff check .` and `uv run mypy`
- Try it: `./install.sh /tmp/site --example && python3 /tmp/site/_site/serve.py --directory /tmp/site`
- License headers: `task license`

## Logging

Follow the logging rules in `CLAUDE.md`. In short:

- Log generously: entry and exit of significant operations, decisions and branches, retries, state
  changes, external calls (target, duration, outcome), and every error with its context.
- Levels: `trace` for step-by-step detail, `debug` for flow, `info` for lifecycle, `warn` and
  `error` for problems. The environment filters the volume, so err on the side of too much.
- Environments: local dev `trace` with `LOG_FORMAT=console` (never JSON), dev cluster `debug`,
  qa/staging `info`, production `error`. Every cluster environment logs JSON. Set levels through
  `LOG_LEVEL` and `LOG_FORMAT`, never in code; local settings live in the run target or
  `.env.example`.
- Never log secrets, tokens, or personal data, not even at `trace`. Log an opaque or keyed ID.

## Conventions and gotchas

- See `CLAUDE.md` for the branch/commit/PR rules; they are enforced by the git hooks in
  `.claude/hooks` (run `bash .claude/hooks/install.sh` once per clone).
- Open every PR as a draft. CI skips drafts, so run the full checks locally, push once they pass,
  and mark the PR ready when the work is finished; see CLAUDE.md "CI and Actions minutes".
- `review.js` stores answers under `KEY_PREFIX + page`; `install.sh` stamps `KEY_PREFIX` and `BLOCKER_TO`
  from `site.json`. Never rename an existing instance's prefix: its saved answers would be orphaned.
- Stale deletes files for real; keep `page_path()` in `serve.py` strict and tested.
