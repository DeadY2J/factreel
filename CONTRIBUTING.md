# Contributing to FactReel

Thanks for helping! Issues and pull requests are welcome **in English or Spanish** (también en español).

## Setup

```bash
git clone https://github.com/DeadY2J/factreel
cd factreel
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev,youtube]"
pytest            # needs ffmpeg for the end-to-end test (it is skipped otherwise)
ruff check .
```

Try your change on a real channel without spending API credits:

```bash
factreel init /tmp/test-channel --lang es
factreel make -c /tmp/test-channel --offline --voice dummy --no-history
```

## Good first contributions

- **A new language**: add an entry to `LANGS` in `src/factreel/lang.py` (prompts, month names, call-to-action
  regex, default Edge voice), a template in `src/factreel/templates/<lang>/` and a test.
- **A new voice or image provider**: see [docs/providers.md](docs/providers.md).
- **A new uploader** (TikTok, Instagram Reels…): mirror `src/factreel/youtube.py`.
- Anything in the [roadmap](ROADMAP.md) or labelled `good first issue`.

## Guidelines

- Keep the guarantees: never let the script state something that isn't in the facts, never block a video
  because one optional service is down, never put secrets in config files.
- New behaviour needs a test. Network calls must be mockable; tests must pass offline.
- Keep dependencies light: optional features go in an extra (`[project.optional-dependencies]`).
- Format with `ruff`. One topic per pull request, with a short description of the why.

By contributing you agree that your contributions are licensed under the MIT license.
