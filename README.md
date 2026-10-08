# claude-handoff-web 🐍

> 🧭 A small self-updating review and sign-off site for handing work to a human: chips, live updates, Yes/No/Changes reviews, checklists with blockers

## 📦 Install

```bash
pip install claude-handoff-web
```

## 🚀 Usage

```python
from claude_handoff_web import hello

hello("world")  # "Hello, world!"
```

## 🛠 Develop

This project uses [uv](https://docs.astral.sh/uv/).

```bash
uv sync                  # create the env and install dev deps
uv run ruff check        # lint
uv run mypy              # type-check
uv run pytest --cov      # test
uv build                 # build wheel + sdist
```

## ⚖️ License

MIT (c) 2026 The claude-handoff-web Authors
