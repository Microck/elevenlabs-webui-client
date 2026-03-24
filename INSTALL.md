# Install

## Local editable install

```bash
uv venv
. .venv/bin/activate
uv pip install -e .
```

## With browser-profile extraction support

```bash
uv pip install -e '.[browser]'
python -m playwright install chromium
```

## Smoke check

```bash
python -m unittest discover -s tests -v
elevenlabs-webui --help
```
