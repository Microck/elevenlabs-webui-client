# elevenlabs-webui-client

Standalone ElevenLabs TTS client extracted from a working WebUI-authenticated implementation.

It uses the same auth path as the ElevenLabs browser app:

1. Exchange Firebase refresh tokens for short-lived bearer tokens
2. Call ElevenLabs endpoints with `Authorization: Bearer <id_token>`
3. Optionally fall back to classic `xi-api-key` auth if enabled

This repo is intentionally small. It packages the reusable ElevenLabs WebUI auth and TTS logic without ArchieTok-specific pipeline code or any local secrets.

## Features

- WebUI-style auth with `ELEVENLABS_FIREBASE_REFRESH_TOKENS`
- Optional auth extraction from an already logged-in Chromium or Firefox profile
- Stable credential rotation across multiple refresh tokens or API keys
- TTS to MP3, including `with-timestamps` support
- Lightweight CLI for synthesis, subscription checks, voice listing, and profile token extraction
- No bundled secrets, profiles, state files, or machine-specific config

## Quick Start

Create a virtualenv and install the package:

```bash
uv venv
. .venv/bin/activate
uv pip install -e .
```

If you want browser-profile extraction, install the browser extra:

```bash
uv pip install -e '.[browser]'
python -m playwright install chromium
```

Copy `.env.example` to `.env` or export variables manually:

```bash
export ELEVENLABS_AUTH_MODE=webui
export ELEVENLABS_DISABLE_API_KEY_FALLBACK=1
export ELEVENLABS_FIREBASE_REFRESH_TOKENS="refresh_token_1,refresh_token_2"
```

Generate speech:

```bash
elevenlabs-webui tts \
  --voice-id RXtWW6etvimS8QJ5nhVk \
  --text "Hello from the ElevenLabs WebUI client." \
  --out outputs/hello.mp3
```

Check auth without generating audio:

```bash
elevenlabs-webui subscription
elevenlabs-webui voices
```

Extract refresh tokens from a logged-in browser profile:

```bash
elevenlabs-webui extract-profile-auth \
  --profile-dir /path/to/profile \
  --print-env
```

## Environment

Primary variables:

- `ELEVENLABS_FIREBASE_REFRESH_TOKENS` - comma-separated Firebase refresh tokens
- `ELEVENLABS_FIREBASE_REFRESH_TOKEN` - single legacy token
- `ELEVENLABS_WEBUI_PROFILE_DIR` - optional browser profile path for auto-extraction
- `ELEVENLABS_WEBUI_PROFILE_REFRESH_SECONDS` - profile auth cache TTL, default `900`
- `ELEVENLABS_AUTH_MODE` - `auto`, `webui`, or `api`
- `ELEVENLABS_DISABLE_API_KEY_FALLBACK` - set to `1` to force WebUI auth only
- `ELEVENLABS_API_KEYS` / `ELEVENLABS_API_KEY` - optional classic fallback auth
- `ELEVENLABS_MODEL_ID` - default model, default `eleven_v3`
- `ELEVENLABS_MODEL_ID_ES` - Spanish override when default model is `eleven_v3`
- `ELEVENLABS_DEBUG` - set to `1` for debug logging

## CLI

### `tts`

```bash
elevenlabs-webui tts \
  --voice-id <voice_id> \
  --text "some text" \
  --out out.mp3
```

Useful flags:

- `--text-file` - load text from a file instead of `--text`
- `--language-code` - pass language code for multilingual models
- `--model-id` - override the default model
- `--alignment-out` - write timestamp alignment JSON
- `--salt` - influence stable credential rotation order

### `subscription`

Fetches `GET /v1/user/subscription` using the same auth flow. Useful as a cheap auth check.

### `voices`

Fetches `GET /v1/voices` and prints a compact list by default.

### `extract-profile-auth`

By default this prints counts only, not raw secrets. Raw tokens are only printed when explicitly requested.

Examples:

```bash
elevenlabs-webui extract-profile-auth --profile-dir /path/to/profile
elevenlabs-webui extract-profile-auth --profile-dir /path/to/profile --print-env
elevenlabs-webui extract-profile-auth --profile-dir /path/to/profile --show-refresh-tokens
```

## Python API

```python
from elevenlabs_webui_client import get_subscription, list_voices, tts_to_mp3

print(get_subscription()["tier"])
print(len(list_voices().get("voices", [])))

tts_to_mp3(
    voice_id="RXtWW6etvimS8QJ5nhVk",
    text="Hello from Python.",
    out_path="outputs/hello.mp3",
)
```

## Project Structure

```text
elevenlabs-webui-client/
├── .env.example
├── .gitignore
├── pyproject.toml
├── README.md
├── src/
│   └── elevenlabs_webui_client/
│       ├── __init__.py
│       ├── __main__.py
│       ├── cli.py
│       └── client.py
└── tests/
    └── test_client.py
```

## Security

- No tokens, cookies, browser profiles, or state files are included here
- `.env` and local output paths are ignored
- The token extraction command only reveals secrets when you explicitly ask it to
