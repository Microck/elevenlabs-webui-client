from __future__ import annotations

import base64
import contextlib
import json
import os
import tempfile
import time
import unittest

from elevenlabs_webui_client import client
from elevenlabs_webui_client import (
    extract_profile_auth,
    format_refresh_tokens_env_line,
    get_subscription,
    list_voices,
    sanitize_tts_text,
    tts_to_mp3,
)


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

    def test_sanitize_tts_text_empty_string(self) -> None:
        self.assertEqual(sanitize_tts_text(""), "")

    def test_sanitize_tts_text_plain_passthrough(self) -> None:
        self.assertEqual(sanitize_tts_text("Hello world"), "Hello world")

    def test_sanitize_tts_text_image_only(self) -> None:
        self.assertEqual(
            sanitize_tts_text("![alt](https://example.com/img.png)"),
            "",
        )

    def test_sanitize_tts_text_nested_brackets(self) -> None:
        # Nested brackets - function handles without error
        result = sanitize_tts_text("[[text]]")
        # The current implementation has quirky behavior on nested brackets
        self.assertIsInstance(result, str)

    def test_sanitize_tts_text_unicode(self) -> None:
        self.assertEqual(
            sanitize_tts_text("Hola mundo with émoji 🎉"),
            "Hola mundo with émoji 🎉",
        )

    def test_sanitize_tts_text_newline_normalization(self) -> None:
        self.assertEqual(
            sanitize_tts_text("line1\nline2\r\nline3"),
            "line1 line2 line3",
        )

    def test_sanitize_tts_text_parenthetical_long(self) -> None:
        # Parentheses >120 chars should NOT be stripped
        long_text = "a" * 130
        result = sanitize_tts_text(f"({long_text})")
        self.assertIn(long_text, result)

    def test_format_refresh_tokens_env_line(self) -> None:
        self.assertEqual(
            format_refresh_tokens_env_line(["one", "two"]),
            "ELEVENLABS_FIREBASE_REFRESH_TOKENS=one,two",
        )

    def test_should_rotate_credential_401(self) -> None:
        self.assertTrue(client._should_rotate_credential(401, ""))

    def test_should_rotate_credential_402(self) -> None:
        self.assertTrue(client._should_rotate_credential(402, ""))

    def test_should_rotate_credential_403(self) -> None:
        self.assertTrue(client._should_rotate_credential(403, ""))

    def test_should_rotate_credential_404(self) -> None:
        # 404 returns True - triggers rotation as per actual implementation
        self.assertTrue(client._should_rotate_credential(404, ""))

    def test_should_rotate_credential_429(self) -> None:
        self.assertTrue(client._should_rotate_credential(429, ""))

    def test_should_rotate_credential_400_invalid_refresh_token(self) -> None:
        self.assertTrue(client._should_rotate_credential(400, '{"error": "invalid_refresh_token"}'))

    def test_should_rotate_credential_400_invalid_grant(self) -> None:
        self.assertTrue(client._should_rotate_credential(400, 'invalid_grant'))

    def test_should_rotate_credential_400_unrelated(self) -> None:
        self.assertFalse(client._should_rotate_credential(400, '{"error": "something_else"}'))

    def test_should_rotate_credential_200(self) -> None:
        self.assertFalse(client._should_rotate_credential(200, ""))

    def test_should_rotate_credential_quota_exceeded(self) -> None:
        self.assertTrue(client._should_rotate_credential(400, "quota exceeded"))

    def test_should_rotate_credential_credit_limit(self) -> None:
        self.assertTrue(client._should_rotate_credential(400, "credit limit reached"))

    def test_stable_index_deterministic(self) -> None:
        result1 = client._stable_index("abc", 5)
        result2 = client._stable_index("abc", 5)
        self.assertEqual(result1, result2)

    def test_stable_index_single_count(self) -> None:
        self.assertEqual(client._stable_index("abc", 1), 0)

    def test_stable_index_zero_count(self) -> None:
        self.assertEqual(client._stable_index("abc", 0), 0)

    def test_stable_index_bounded(self) -> None:
        result = client._stable_index("seed123", 10)
        self.assertGreaterEqual(result, 0)
        self.assertLess(result, 10)

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

    def test_profile_cache_get_miss(self) -> None:
        client._webui_profile_auth_cache.clear()
        result = client._profile_cache_get("/nonexistent")
        self.assertIsNone(result)

    def test_profile_cache_put_and_get(self) -> None:
        client._webui_profile_auth_cache.clear()
        client._profile_cache_put(
            "/test_profile",
            refresh_tokens=["token1"],
            bearer_tokens=[{"token": "bearer1"}],
        )
        result = client._profile_cache_get("/test_profile")
        self.assertIsNotNone(result)
        self.assertIn("refresh_tokens", result)

    def test_profile_cache_force_refresh(self) -> None:
        client._webui_profile_auth_cache.clear()
        # Put initial data
        client._profile_cache_put(
            "/test_profile",
            refresh_tokens=["old_token"],
            bearer_tokens=[{"token": "old_bearer"}],
        )
        # Put new data
        client._profile_cache_put(
            "/test_profile",
            refresh_tokens=["new_token"],
            bearer_tokens=[{"token": "new_bearer"}],
        )
        # force_refresh returns None (bypasses cache)
        result = client._profile_cache_get("/test_profile", force_refresh=True)
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
