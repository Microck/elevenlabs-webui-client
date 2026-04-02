"""ElevenLabs WebUI client — TTS synthesis via Firebase/WebUI authentication.

Public API:

- :func:`tts_to_mp3` — synthesize text to an MP3 file
- :func:`get_subscription` — fetch subscription details
- :func:`list_voices` — list available voices
- :func:`extract_profile_auth` — extract tokens from a browser profile
- :func:`sanitize_tts_text` — strip markdown from text before TTS
- :func:`format_refresh_tokens_env_line` — format tokens as an env export line
"""

from .client import (
    extract_profile_auth,
    format_refresh_tokens_env_line,
    get_subscription,
    list_voices,
    sanitize_tts_text,
    tts_to_mp3,
)

__all__ = [
    "extract_profile_auth",
    "format_refresh_tokens_env_line",
    "get_subscription",
    "list_voices",
    "sanitize_tts_text",
    "tts_to_mp3",
]
