# elevenlabs-webui-client

Standalone ElevenLabs TTS client extracted from a working WebUI-authenticated implementation.

It uses the same auth path as the ElevenLabs browser app:

1. Exchange Firebase refresh tokens for short-lived bearer tokens
2. Call ElevenLabs endpoints with `Authorization: Bearer ***`
3. Optionally fall back to classic `xi-api-key` auth if enabled

This repo is intentionally small. It packages the reusable ElevenLabs WebUI auth and TTS logic.

## Requirements

- Python 3.11+
- No runtime dependencies for core functionality
- Optional: [Playwright](https://playwright.dev/python/) for browser-profile auth extraction

## Features

- **WebUI-style auth** with `ELEVENLABS_FIREBASE_REFRESH_TOKENS`
- **Browser profile extraction** from an already logged-in Chromium or Firefox profile
- **Stable credential rotation** across multiple refresh tokens or API keys
- **TTS to MP3**, including `with-timestamps` support with alignment data
- **Lightweight CLI** for synthesis, subscription checks, voice listing, and profile token extraction
- **No bundled secrets** — no profiles, state files, or machine-specific config

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
export ELEVENLABS_AUTH_MODE=auto
export ELEVENLABS_DISABLE_API_KEY_FALLBACK=0
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

## CLI Reference

### `tts` — Synthesize speech

```bash
elevenlabs-webui tts \
  --voice-id <voice_id> \
  --text "some text" \
  --out out.mp3
```

| Flag | Required | Description |
|------|----------|-------------|
| `--voice-id` | Yes | ElevenLabs voice ID |
| `--text` | One of | Text to synthesize (mutually exclusive with `--text-file`) |
| `--text-file` | One of | Read text from a file |
| `--out` | Yes | Output MP3 file path |
| `--model-id` | No | Override the default model |
| `--language-code` | No | Language code for multilingual models (e.g. `es`) |
| `--alignment-out` | No | Write timestamp alignment JSON to this path |
| `--salt` | No | Influence stable credential rotation order (default: `cli:tts`) |
| `--json` | No | Print JSON result instead of just the output path |

### `subscription` — Check subscription

Fetches `GET /v1/user/subscription` using the same auth flow. Useful as a cheap auth check.

```bash
elevenlabs-webui subscription
```

### `voices` — List available voices

Fetches `GET /v1/voices` and prints a compact list. Use `--json` for the full payload.

```bash
elevenlabs-webui voices
elevenlabs-webui voices --json
```

### `extract-profile-auth` — Extract browser tokens

Reads ElevenLabs auth state from a logged-in browser profile. By default prints counts only, not raw secrets.

```bash
# Show token counts only
elevenlabs-webui extract-profile-auth --profile-dir /path/to/profile

# Print ELEVENLABS_FIREBASE_REFRESH_TOKENS=... for .env
elevenlabs-webui extract-profile-auth --profile-dir /path/to/profile --print-env

# Print raw refresh tokens (one per line)
elevenlabs-webui extract-profile-auth --profile-dir /path/to/profile --show-refresh-tokens

# Print raw bearer tokens (one per line)
elevenlabs-webui extract-profile-auth --profile-dir /path/to/profile --show-bearer-tokens
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

The package can also be invoked as a module:

```bash
python -m elevenlabs_webui_client tts --voice-id RXtWW6etvimS8QJ5nhVk --text "test" --out test.mp3
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ELEVENLABS_FIREBASE_REFRESH_TOKENS` | — | Comma-separated Firebase refresh tokens |
| `ELEVENLABS_FIREBASE_REFRESH_TOKEN` | — | Single legacy refresh token |
| `ELEVENLABS_WEBUI_PROFILE_DIR` | — | Browser profile path for auto-extraction |
| `ELEVENLABS_WEBUI_PROFILE_REFRESH_SECONDS` | `900` | Profile auth cache TTL |
| `ELEVENLABS_AUTH_MODE` | `auto` | Auth mode: `auto`, `webui`, `bearer`, `firebase`, or `api` |
| `ELEVENLABS_DISABLE_API_KEY_FALLBACK` | `0` | Set to `1` to force WebUI auth only |
| `ELEVENLABS_API_KEYS` / `ELEVENLABS_API_KEY` | — | Optional classic API key fallback |
| `ELEVENLABS_MODEL_ID` | `eleven_v3` | Default TTS model |
| `ELEVENLABS_MODEL_ID_ES` | `eleven_multilingual_v2` | Spanish override when default is `eleven_v3` |
| `ELEVENLABS_DEBUG` | — | Set to `1` for debug logging |

## Project Structure

```text
elevenlabs-webui-client/
├── pyproject.toml
├── README.md
├── INSTALL.md
├── src/
│   └── elevenlabs_webui_client/
│       ├── __init__.py      # Public API exports
│       ├── __main__.py      # Module entry point
│       ├── cli.py           # CLI argument parsing
│       └── client.py        # Core auth + TTS logic
└── tests/
    └── test_client.py
```

## Troubleshooting

**"Playwright is required for browser profile extraction"**
Install the optional browser extra: `pip install '.[browser]'`

**"ElevenLabs WebUI auth failed and API-key fallback is disabled"**
Check that your refresh tokens are valid and not expired. You can extract fresh tokens from a logged-in browser profile using `extract-profile-auth`.

**"ElevenLabs request failed after rotating credentials"**
All configured credentials (tokens + API keys) were exhausted. Check your subscription status with `elevenlabs-webui subscription`.

## Security

- No tokens, cookies, browser profiles, or state files are included in this repo
- `.env` and local output paths are in `.gitignore`
- The token extraction command only reveals secrets when you explicitly request it (`--print-env`, `--show-refresh-tokens`, `--show-bearer-tokens`)
- Firebase API keys are public (embedded in the ElevenLabs web app) and are not secrets

## License

This project is provided as-is. See repository for license details.
