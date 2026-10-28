#!/usr/bin/env bash
# Install the hand-off site into a working folder.
#
#   ./install.sh <target-dir> [options]
#
# Options (asked for once when missing and a terminal is attached):
#   --title <text>        site title (default: "Pages for <owner>")
#   --owner <name>        the person who answers the pages
#   --host <addr>         bind address (default 127.0.0.1)
#   --port <n>            port (default 8000)
#   --tz <zone>           IANA timezone for times on the site (default UTC)
#   --tz-label <text>     short label shown after times (default: the zone)
#   --windows <list>      review windows, comma separated HH:MM (default 09:00,16:00)
#   --folders <list>      comma separated id:Name:blurb (default ops:Operator:Coordination)
#   --key-prefix <text>   answer storage key prefix (default review:)
#   --blocker-to <text>   who blockers are pasted to (default "the operator session")
#   --example             also copy the fake example folders and start from its site.json; any option
#                         given is applied on top of it (--folders adds folders next to the example ones)
#   --force               overwrite an existing site.json
#
# The target is scratch memory and is never committed: the script refuses to install inside a git
# work tree and never runs git init.
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET=""; TITLE=""; OWNER=""; HOST=""; PORT=""; TZONE=""; TZLABEL=""; WINDOWS=""; FOLDERS=""
KEYPREFIX=""; BLOCKERTO=""; EXAMPLE=0; FORCE=0
while [ $# -gt 0 ]; do
  case "$1" in
    --title) TITLE="$2"; shift ;;
    --owner) OWNER="$2"; shift ;;
    --host) HOST="$2"; shift ;;
    --port) PORT="$2"; shift ;;
    --tz) TZONE="$2"; shift ;;
    --tz-label) TZLABEL="$2"; shift ;;
    --windows) WINDOWS="$2"; shift ;;
    --folders) FOLDERS="$2"; shift ;;
    --key-prefix) KEYPREFIX="$2"; shift ;;
    --blocker-to) BLOCKERTO="$2"; shift ;;
    --example) EXAMPLE=1 ;;
    --force) FORCE=1 ;;
    -h|--help) sed -n '2,22p' "$0"; exit 0 ;;
    -*) echo "unknown option: $1" >&2; exit 2 ;;
    *) if [ -z "$TARGET" ]; then TARGET="$1"; else echo "unexpected argument: $1" >&2; exit 2; fi ;;
  esac
  shift
done
[ -n "$TARGET" ] || { echo "usage: install.sh <target-dir> [--owner <name>] [--example] ..." >&2; exit 2; }

# Refuse anywhere inside a git work tree (checked from the nearest existing parent).
probe="$TARGET"
while [ ! -d "$probe" ]; do probe="$(dirname "$probe")"; done
if git -C "$probe" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "refusing: $TARGET is inside a git work tree ($(git -C "$probe" rev-parse --show-toplevel))." >&2
  echo "The site folder is working memory and is never committed; pick a folder outside any repository." >&2
  exit 1
fi

ask() {  # ask <var> <prompt> <default>
  local cur="${!1}"
  if [ -z "$cur" ] && [ -t 0 ]; then read -r -p "$2 [$3]: " cur || true; fi
  printf -v "$1" '%s' "${cur:-$3}"
}
if [ "$EXAMPLE" -eq 0 ]; then
  ask OWNER "Owner (the person who answers)" "owner"
  ask TITLE "Site title" "Pages for $OWNER"
  ask HOST "Bind address" "127.0.0.1"
  ask PORT "Port" "8000"
  ask TZONE "Timezone (IANA)" "UTC"
  ask TZLABEL "Time label" "$TZONE"
  ask WINDOWS "Review windows (HH:MM,...)" "09:00,16:00"
  ask FOLDERS "Folders (id:Name:blurb,...)" "ops:Operator:Coordination"
  ask KEYPREFIX "Answer key prefix" "review:"
  ask BLOCKERTO "Blockers are pasted to" "the operator session"
fi

mkdir -p "$TARGET"
TARGET="$(cd "$TARGET" && pwd)"
cp -R "$SRC/template/." "$TARGET/"
mkdir -p "$TARGET/_saved" "$TARGET/_old"

BASE=""
if [ "$EXAMPLE" -eq 1 ]; then
  # BSD cp (macOS) copies a source ending in "/" as its contents, so strip the slash to copy the folder itself.
  for d in "$SRC/example"/*/; do cp -R "${d%/}" "$TARGET/"; done
  BASE="$SRC/example/site.json"
fi

if [ -e "$TARGET/site.json" ] && [ "$FORCE" -eq 0 ]; then
  echo "kept the existing $TARGET/site.json (use --force to rewrite it)"
else
  BASE="$BASE" TITLE="$TITLE" OWNER="$OWNER" HOST="$HOST" PORT="$PORT" TZONE="$TZONE" TZLABEL="$TZLABEL" \
  WINDOWS="$WINDOWS" FOLDERS="$FOLDERS" KEYPREFIX="$KEYPREFIX" BLOCKERTO="$BLOCKERTO" \
  python3 - "$TARGET/site.json" <<'PY'
import json, os, sys
env = os.environ
folders = []
for part in filter(None, (p.strip() for p in env["FOLDERS"].split(","))):
    fid, _, rest = part.partition(":")
    name, _, blurb = rest.partition(":")
    folders.append({"id": fid.strip(), "name": (name or fid).strip(), "blurb": blurb.strip()})
if env["BASE"]:
    # --example: the example site.json, with only the options actually given applied on top.
    with open(env["BASE"]) as f:
        cfg = json.load(f)
    if env["OWNER"]:
        cfg["owner"] = env["OWNER"]
        cfg["title"] = env["TITLE"] or "Pages for " + env["OWNER"]
    for key, var in (("title", "TITLE"), ("host", "HOST"), ("timezone", "TZONE"), ("key_prefix", "KEYPREFIX"),
                     ("blocker_to", "BLOCKERTO")):
        if env[var]:
            cfg[key] = env[var]
    if env["PORT"]:
        cfg["port"] = int(env["PORT"])
    if env["TZONE"] or env["TZLABEL"]:
        cfg["tz_label"] = env["TZLABEL"] or env["TZONE"]
    if env["WINDOWS"]:
        cfg["review_windows"] = [w.strip() for w in env["WINDOWS"].split(",") if w.strip()]
    for fo in folders:
        cfg["folders"] = [x for x in cfg["folders"] if x["id"] != fo["id"]] + [fo]
        if fo["id"] not in cfg["order"]:
            cfg["order"].append(fo["id"])
    with open(sys.argv[1], "w") as f:
        json.dump(cfg, f, indent=2)
        f.write("\n")
    sys.exit(0)
cfg = {
    "title": env["TITLE"], "owner": env["OWNER"],
    "subtitle": "Everything waiting on you is at the top. Pages update themselves.",
    "host": env["HOST"], "port": int(env["PORT"]), "timezone": env["TZONE"], "tz_label": env["TZLABEL"],
    "review_windows": [w.strip() for w in env["WINDOWS"].split(",") if w.strip()],
    "key_prefix": env["KEYPREFIX"], "blocker_to": env["BLOCKERTO"],
    "folders": folders, "order": [f["id"] for f in folders],
    "protected": [], "builders": {}, "prune_old": True, "prune_old_days": 7,
}
with open(sys.argv[1], "w") as f:
    json.dump(cfg, f, indent=2)
    f.write("\n")
PY
fi

# Stamp the per-install constants into review.js from site.json.
python3 - "$TARGET" <<'PY'
import json, re, sys, pathlib
root = pathlib.Path(sys.argv[1])
cfg = json.loads((root / "site.json").read_text())
js = root / "_site" / "review.js"
s = js.read_text()
s = re.sub(r'const KEY_PREFIX = ".*?";', "const KEY_PREFIX = " + json.dumps(cfg.get("key_prefix", "review:")) + ";", s, count=1)
s = re.sub(r'const BLOCKER_TO = ".*?";', "const BLOCKER_TO = " + json.dumps(cfg.get("blocker_to", "the operator session")) + ";", s, count=1)
js.write_text(s)
for f in cfg.get("folders", []):
    (root / f["id"]).mkdir(exist_ok=True)
PY

cd "$TARGET"
python3 gen-index.py >/dev/null
for d in */; do
  d="${d%/}"
  case "$d" in _*) continue ;; esac
  if [ -f "$d/_status.json" ] && grep -q '"needs-you"' "$d/_status.json"; then
    python3 _site/build-review.py "$d" >/dev/null || true
  fi
done
python3 gen-index.py >/dev/null

HOSTV="$(python3 -c 'import json;print(json.load(open("site.json")).get("host","127.0.0.1"))')"
PORTV="$(python3 -c 'import json;print(json.load(open("site.json")).get("port",8000))')"
echo "Installed into $TARGET (working memory: never commit it)."
echo "Start the server:"
echo "  cd \"$TARGET\" && nohup python3 -u _site/serve.py --directory . >> server.log 2>&1 &"
echo "Then open http://$HOSTV:$PORTV/"
