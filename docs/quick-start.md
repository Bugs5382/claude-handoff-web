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

Without flags the script asks once for each value. Add `--example` to copy the fake demo folders too (with
no `--owner`/`--folders`, it uses the example's `site.json`). The script refuses a target inside a git
work tree and never runs `git init`.

## 2. Run the server

```bash
cd ~/handoff-site
nohup python3 -u _site/serve.py --directory . >> server.log 2>&1 &
```

Open `http://127.0.0.1:8000/`. The server refuses to start inside a git work tree.

## 3. Publish a page

1. Write `app/design-review.html` from a skeleton in [page-types.md](page-types.md).
2. Add it to `app/_status.json`:

   ```json
   { "design-review.html": { "state": "needs-you", "note": "Three sections to approve." } }
   ```

3. Rebuild the indexes and the folder's unified review page:

   ```bash
   python3 _site/build-review.py app
   python3 gen-index.py
   ```

The owner's open tabs update by themselves. Answers are saved on the server; the owner presses More, Copy
results and pastes the result back to you.

## 4. Teach your agents

- Each instance carries `CLAUDE.md` and `AGENTS.md` with the operating rules.
- Copy [`memory/handoff-web.md`](../memory/handoff-web.md) into a Claude session's memory folder.
- More: [operating.md](operating.md), [`_site/README.md`](../template/_site/README.md) and
  [`SAVE-API.md`](../template/_site/SAVE-API.md).
