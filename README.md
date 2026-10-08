# claude-handoff-web 🗂️

> 🤝 A small self-updating review and sign-off site for handing work to a human: chips, live updates, Yes/No/Changes reviews, checklists with blockers.

Agents (Claude sessions or any others) write plain HTML pages into their own folder; the owner opens one
site, sees everything waiting on them at the top, and answers each item Yes, No or Changes. Answers are
saved on the server, and "Copy results" gives the agent a paste-back it can act on. 🔌 **Python standard
library only:** no build step, no framework, no database.

## ✨ Highlights

- 🧭 **One place to look:** folder indexes and a root "Needs you now" list, built from each folder's `_status.json`.
- ✅ **Reviews that stick:** Yes / No / Changes per section, approved items hidden, reopened ones marked with the reason.
- 🧪 **Sign-off checklists:** ordered tests, How to test pop-outs with Copy buttons, dependencies, blockers, Skipped.
- 🔄 **Live:** pages refresh themselves, never while the owner is typing.
- 💾 **Saved on the server:** answers go through a tiny save API, so they survive browsers and machines.
- 🧹 **Stale:** the owner removes a page that no longer matters with one button.

## 📦 Install

Install by copying the template into a working folder; the working folder is scratch memory and is never
committed.

```bash
git clone https://github.com/Bugs5382/claude-handoff-web.git
./claude-handoff-web/install.sh ~/handoff-site --owner "Alex" --folders "ops:Operator:Coordination"
```

`install.sh` asks for anything you leave out, writes `site.json`, and refuses to install inside a git work
tree. Add `--example` for the fake demo folders.

## 🚀 Run

```bash
cd ~/handoff-site
nohup python3 -u _site/serve.py --directory . >> server.log 2>&1 &
```

Then open `http://127.0.0.1:8000/` (host and port come from `site.json`).

## 📚 Docs

- 🏁 **[Quick start](docs/quick-start.md):** install, run, publish a first page.
- 🧱 **[Page types](docs/page-types.md):** the design and a working skeleton for every page an agent makes.
- 🛠️ **[Operating the site](docs/operating.md):** config, endpoints, Stale, `_old/` pruning, the no-git rule.
- 💾 **[Save API](template/_site/SAVE-API.md):** how pages store answers on the server.
- 🤖 **[Agent rules](template/AGENTS.md)** and a **[memory file](memory/handoff-web.md)** for Claude sessions.

## 🧪 Develop

```bash
uv sync
uv run ruff check .
uv run mypy
uv run pytest
```

## 🙏 Acknowledgements

Originally written by [@Bugs5382](https://github.com/Bugs5382).

## ⚖️ License

MIT © 2026 Shane
