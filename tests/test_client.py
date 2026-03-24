from __future__ import annotations

import base64
import contextlib
import json
import os
import time
import unittest

from elevenlabs_webui_client import format_refresh_tokens_env_line, sanitize_tts_text
from elevenlabs_webui_client import client


@contextlib.contextmanager
def temporary_env(updates: dict[str, str | None]):
    original = {key: os.environ.get(key) for key in updates}
    try:
        for key, value in updates.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        yield
    finally:
        for key, value in original.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


class ElevenLabsClientTests(unittest.TestCase):
    def test_sanitize_tts_text_removes_markup(self) -> None:
        source = "Read [carefully] [label](https://example.com) and ignore (stage direction)."
        self.assertEqual(
            sanitize_tts_text(source),
            "Read label and ignore .",
        )

    def test_format_refresh_tokens_env_line(self) -> None:
        self.assertEqual(
            format_refresh_tokens_env_line(["one", "two"]),
            "ELEVENLABS_FIREBASE_REFRESH_TOKENS=one,two",
        )

    def test_get_refresh_tokens_dedupes_env_sources(self) -> None:
        with temporary_env(
            {
                "ELEVENLABS_WEBUI_PROFILE_DIR": None,
                "ELEVENLABS_FIREBASE_REFRESH_TOKENS": "one,two,one",
                "ELEVENLABS_FIREBASE_REFRESH_TOKEN": "two,three",
            }
        ):
            self.assertEqual(client._get_refresh_tokens(), ["one", "two", "three"])

    def test_decode_jwt_exp_returns_zero_for_invalid_token(self) -> None:
        self.assertEqual(client._decode_jwt_exp("not-a-jwt"), 0.0)

    def test_resolve_model_switches_spanish_default(self) -> None:
        with temporary_env(
            {
                "ELEVENLABS_MODEL_ID": "eleven_v3",
                "ELEVENLABS_MODEL_ID_ES": "eleven_multilingual_v2",
            }
        ):
            self.assertEqual(
                client._resolve_model_id(language_code="es"),
                "eleven_multilingual_v2",
            )

    def test_decode_jwt_exp_accepts_valid_payload(self) -> None:
        payload = base64.urlsafe_b64encode(
            json.dumps({"exp": int(time.time()) + 3600}).encode("utf-8")
        ).decode("utf-8").rstrip("=")
        token = f"header.{payload}.signature"
        self.assertGreater(client._decode_jwt_exp(token), time.time())


if __name__ == "__main__":
    unittest.main()
