# claude-handoff-web 🗂️

> 🤝 A small self-updating review and sign-off site for handing work to a human: chips, live updates, Yes/No/Changes reviews, checklists with blockers.

Agents (Claude sessions or any others) write JSON page files into their own folder; the owner opens one
site, sees everything waiting on them at the top, and answers each item Yes, No or Changes. Answers and
reply threads are saved on the server, round by round, and Send delivers them straight to the agent's
inbox (Blocker sends a single item at once), with Copy results as a paste-back for agents that aren't
listening. 🔌 **Python standard library only:** no build step, no framework, no database.

## ✨ Highlights

- 🧭 **One place to look:** folder indexes and a root "Needs you now" list, built from the page files on every request.
- ✅ **Reviews that stick:** Yes / No / Changes per section, approved items hidden, reopened ones marked with the reason, and More, Mark unanswered Yes (or No) to fill in the rest at once.
- 🎛️ **Your own choices:** a page can swap Yes / No / Changes for its own answers and a default, such as a backlog of Start or Hold.
- 🧪 **Sign-off checklists:** ordered tests, How to test pop-outs with Copy buttons, dependencies, blockers, Skipped.
- 🪟 **Links open in a new window:** a link to another page never replaces the one you're reviewing; `#` anchors stay on the page.
- 🖼️ **Pictures in one pop-out:** click a picture and it opens in one reused window; the next one swaps in, no pile of tabs.
- 🧷 **A bar that tells you where you are:** Previous, Next, an Open IDs picker with a filter, and More; it turns green when every item is answered and points you back to the folder.
- 🌗 **Light and dark:** IBM Plex type, self-hosted with no font CDN, and an Auto / Light / Dark toggle on every page.
- 🔢 **Cards in order:** numbered pages list 1, 2, ... 10, never reshuffled by the last edit.
- 🔄 **Live:** pages refresh themselves, never while the owner is typing.
- 💾 **Saved on the server:** answers and reply threads live in the page file, round by round, so they survive browsers and machines.
- 📨 **Send and Blocker:** Send delivers the answers to the agent's inbox, shows whether the agent took them and replied, and Blocker sends one item at once.
- 🧹 **Stale:** the owner removes a page that no longer matters with one button.

## 📦 Install

Install by copying the template into a working folder; the working folder is scratch memory and is never
committed.

```bash
git clone https://github.com/Bugs5382/claude-handoff-web.git
./claude-handoff-web/install.sh ~/handoff-site --owner "Alex" --folders "ops:Operator:Coordination"
```

`install.sh` asks for anything you leave out, writes `site.json`, and refuses to install inside a git work
tree. Add `--example` for the fake demo folders; it starts from the example `site.json` and applies any
option you give on top.

## 🚀 Run

```bash
cd ~/handoff-site
nohup python3 -u _site/serve.py --directory . >> server.log 2>&1 &
```

Then open `http://127.0.0.1:8000/` (host and port come from `site.json`).

## 📚 Docs

- 🏁 **[Quick start](docs/quick-start.md):** install, run, publish a first page.
- 🧱 **[Page types](docs/page-types.md):** every kind of page an agent makes, with a JSON example of each.
- 🛠️ **[Operating the site](docs/operating.md):** config, endpoints, Stale, `_old/` pruning, the no-git rule.
- 🗂️ **[Page files](template/_site/PAGE-FILE.md):** the JSON page format, the writer, `page.py` and the renderer.
- 🔌 **[Page API](template/_site/PAGE-API.md):** page files over HTTP, Send and Blocker, and the agent's inbox.
- 💾 **[Save API](template/_site/SAVE-API.md):** how HTML pages that aren't converted yet store answers.
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
