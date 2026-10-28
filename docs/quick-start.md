# Quick start

Install by copying the template into a working folder; the working folder is scratch memory and is never
committed.

## 1. Install

```bash
git clone https://github.com/Bugs5382/claude-handoff-web.git
cd claude-handoff-web
./install.sh ~/handoff-site --owner "Alex" --host 127.0.0.1 --port 8000 --tz UTC \
  --folders "ops:Operator:Coordination,app:My app:Reviews for the app"
```

Without flags the script asks once for each value. Add `--example` to copy the fake demo folders too: it
starts from the example's `site.json` and asks nothing, applying any option you give on top of it
(`--owner`, `--port` and so on; `--folders` adds folders next to `demo` and `guide`). The script refuses a
target inside a git work tree and never runs `git init`.

## 2. Run the server

```bash
cd ~/handoff-site
nohup python3 -u _site/serve.py --directory . >> server.log 2>&1 &
```

Open `http://127.0.0.1:8000/`. The server refuses to start inside a git work tree.

## 3. Publish a page

1. Write the page's definition, `design.json`:

   ```json
   {"schema": "handoff.page/v1", "kind": "review", "title": "Settings screen: design review",
    "items": [{"id": "s1", "title": "Purpose", "body": [{"p": "Change your display name and theme."}]},
              {"id": "s2", "title": "Layout", "body": [{"p": "Tabs across the top."}]}]}
   ```

2. Create the page in your folder:

   ```bash
   python3 _site/page.py new app/design-review --from design.json
   ```

3. Open `http://127.0.0.1:8000/app/design-review`. The page is on the folder and root indexes already; there
   is no manifest to edit and no index to rebuild.

Answers are saved in the page file as they are given. When the owner presses Send, the
result lands in `_inbox/<agent>/` for the page's route. Run `python3 _site/page.py wait <agent>` in the
background to hear about it the moment it arrives. Every kind of page, with examples: [page-types.md](page-types.md).

## 4. Teach your agents

- Each instance carries `CLAUDE.md` and `AGENTS.md` with the operating rules.
- Copy [`memory/handoff-web.md`](../memory/handoff-web.md) into a Claude session's memory folder.
- More: [operating.md](operating.md), [`_site/README.md`](../template/_site/README.md),
  [`PAGE-FILE.md`](../template/_site/PAGE-FILE.md) and [`PAGE-API.md`](../template/_site/PAGE-API.md).
