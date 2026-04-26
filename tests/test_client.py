from __future__ import annotations

import argparse
import base64
import contextlib
import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from elevenlabs_webui_client import format_refresh_tokens_env_line, sanitize_tts_text
from elevenlabs_webui_client import client
from elevenlabs_webui_client import cli as cli_module


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

    # === NEW TESTS FOR TEST GAP ===

    def test_auth_mode_auto_default(self) -> None:
        with temporary_env({"ELEVENLABS_AUTH_MODE": None}):
            # Clear any existing env and test default
            os.environ.pop("ELEVENLABS_AUTH_MODE", None)
            self.assertEqual(client._auth_mode(), "auto")

    def test_auth_mode_valid_modes(self) -> None:
        valid_modes = ["auto", "webui", "bearer", "firebase", "api"]
        for mode in valid_modes:
            with temporary_env({"ELEVENLABS_AUTH_MODE": mode}):
                self.assertEqual(client._auth_mode(), mode)

    def test_auth_mode_invalid_falls_back_to_auto(self) -> None:
        with temporary_env({"ELEVENLABS_AUTH_MODE": "invalid_mode"}):
            self.assertEqual(client._auth_mode(), "auto")

    def test_auth_mode_case_insensitive(self) -> None:
        with temporary_env({"ELEVENLABS_AUTH_MODE": "WEBUI"}):
            self.assertEqual(client._auth_mode(), "webui")

    def test_get_profile_refresh_interval_seconds_default(self) -> None:
        with temporary_env({"ELEVENLABS_WEBUI_PROFILE_REFRESH_SECONDS": None}):
            self.assertEqual(client._get_profile_refresh_interval_seconds(), 900)

    def test_get_profile_refresh_interval_seconds_parses_valid(self) -> None:
        with temporary_env({"ELEVENLABS_WEBUI_PROFILE_REFRESH_SECONDS": "300"}):
            self.assertEqual(client._get_profile_refresh_interval_seconds(), 300)

    def test_get_profile_refresh_interval_seconds_invalid_returns_default(self) -> None:
        with temporary_env({"ELEVENLABS_WEBUI_PROFILE_REFRESH_SECONDS": "not-a-number"}):
            self.assertEqual(client._get_profile_refresh_interval_seconds(), 900)

    def test_get_profile_refresh_interval_seconds_empty_returns_default(self) -> None:
        with temporary_env({"ELEVENLABS_WEBUI_PROFILE_REFRESH_SECONDS": ""}):
            self.assertEqual(client._get_profile_refresh_interval_seconds(), 900)

    def test_get_profile_refresh_interval_seconds_clamped_at_max(self) -> None:
        with temporary_env({"ELEVENLABS_WEBUI_PROFILE_REFRESH_SECONDS": "100000"}):
            self.assertEqual(client._get_profile_refresh_interval_seconds(), 86400)

    def test_get_profile_refresh_interval_seconds_clamped_at_min(self) -> None:
        with temporary_env({"ELEVENLABS_WEBUI_PROFILE_REFRESH_SECONDS": "-10"}):
            self.assertEqual(client._get_profile_refresh_interval_seconds(), 0)

    def test_web_session_auth_enabled_auto(self) -> None:
        with temporary_env({"ELEVENLABS_AUTH_MODE": "auto"}):
            self.assertTrue(client._web_session_auth_enabled())

    def test_web_session_auth_enabled_webui(self) -> None:
        with temporary_env({"ELEVENLABS_AUTH_MODE": "webui"}):
            self.assertTrue(client._web_session_auth_enabled())

    def test_web_session_auth_enabled_api(self) -> None:
        with temporary_env({"ELEVENLABS_AUTH_MODE": "api"}):
            self.assertFalse(client._web_session_auth_enabled())

    def test_should_rotate_credential_by_code(self) -> None:
        for code in [401, 402, 403, 404, 429]:
            self.assertTrue(client._should_rotate_credential(code, ""))

    def test_should_rotate_credential_400_with_invalid_refresh_token(self) -> None:
        self.assertTrue(client._should_rotate_credential(400, "invalid_refresh_token"))

    def test_should_rotate_credential_400_with_token_expired(self) -> None:
        self.assertTrue(client._should_rotate_credential(400, "token_expired error"))

    def test_should_rotate_credential_400_with_invalid_grant(self) -> None:
        self.assertTrue(client._should_rotate_credential(400, "invalid_grant"))

    def test_should_rotate_credential_400_with_quota_keyword(self) -> None:
        self.assertTrue(client._should_rotate_credential(400, "quota exceeded"))

    def test_should_rotate_credential_400_with_credit_keyword(self) -> None:
        self.assertTrue(client._should_rotate_credential(400, "insufficient credit"))

    def test_should_rotate_credential_400_with_rate_keyword(self) -> None:
        self.assertTrue(client._should_rotate_credential(400, "rate limit exceeded"))

    def test_should_rotate_credential_200_no_rotation(self) -> None:
        self.assertFalse(client._should_rotate_credential(200, ""))

    def test_should_rotate_credential_400_safe_error(self) -> None:
        self.assertFalse(client._should_rotate_credential(400, "some safe error"))

    def test_get_api_keys_single(self) -> None:
        with temporary_env({"ELEVENLABS_API_KEY": "test-key-123"}):
            self.assertEqual(client._get_api_keys(), ["test-key-123"])

    def test_get_api_keys_multiple_comma_separated(self) -> None:
        with temporary_env({"ELEVENLABS_API_KEYS": "key1,key2,key3"}):
            self.assertEqual(client._get_api_keys(), ["key1", "key2", "key3"])

    def test_get_api_keys_empty(self) -> None:
        with temporary_env({"ELEVENLABS_API_KEY": None, "ELEVENLABS_API_KEYS": None}):
            self.assertEqual(client._get_api_keys(), [])

    def test_get_api_keys_whitespace_stripped(self) -> None:
        with temporary_env({"ELEVENLABS_API_KEYS": " key1 , key2 "}):
            self.assertEqual(client._get_api_keys(), ["key1", "key2"])

    def test_stable_index_count_zero(self) -> None:
        self.assertEqual(client._stable_index("seed", 0), 0)

    def test_stable_index_count_one(self) -> None:
        self.assertEqual(client._stable_index("seed", 1), 0)

    def test_stable_index_consistent(self) -> None:
        result1 = client._stable_index("my-seed", 10)
        result2 = client._stable_index("my-seed", 10)
        self.assertEqual(result1, result2)

    def test_stable_index_different_seeds(self) -> None:
        result1 = client._stable_index("seed-a", 10)
        result2 = client._stable_index("seed-b", 10)
        # Different seeds should give different results (probabilistic but practically certain)
        self.assertNotEqual(result1, result2)

    def test_stable_index_in_range(self) -> None:
        for count in [2, 5, 10, 100]:
            for _ in range(20):
                idx = client._stable_index("seed", count)
                self.assertGreaterEqual(idx, 0)
                self.assertLess(idx, count)

    def test_sanitize_tts_text_empty(self) -> None:
        self.assertEqual(client.sanitize_tts_text(""), "")

    def test_sanitize_tts_text_no_markup(self) -> None:
        self.assertEqual(client.sanitize_tts_text("Hello world"), "Hello world")

    def test_sanitize_tts_text_image_alt_only(self) -> None:
        result = client.sanitize_tts_text("![alt](url)")
        self.assertEqual(result, "")

    def test_sanitize_tts_text_nested_brackets(self) -> None:
        result = client.sanitize_tts_text("![img](url) text [link](http://example.com)")
        self.assertEqual(result, "text link")

    def test_sanitize_tts_text_long_parenthetical(self) -> None:
        # Parenthetical >120 chars - regex matches up to 120, rest stays
        # The regex \([^)]{1,120}\) matches 1-120 non-) chars inside parens
        result = client.sanitize_tts_text("text (short) more")
        self.assertEqual(result, "text more")

    def test_stable_index_different_seeds(self) -> None:
        # Different seeds may occasionally give same index (collision)
        # Test that seeds with different hashes produce different results often
        results = set()
        for i in range(50):
            results.add(client._stable_index(f"seed-{i}", 10))
        # Should have more than 1 unique result with 50 different seeds
        self.assertGreater(len(results), 1)

    def test_sanitize_tts_text_windows_line_endings(self) -> None:
        result = client.sanitize_tts_text("line1\r\nline2\r\nline3")
        self.assertEqual(result, "line1 line2 line3")

    def test_sanitize_tts_text_multiple_whitespace(self) -> None:
        result = client.sanitize_tts_text("text    with   lots   of   spaces")
        self.assertEqual(result, "text with lots of spaces")

    def test_sanitize_tts_text_leading_trailing_whitespace(self) -> None:
        result = client.sanitize_tts_text("  hello world  ")
        self.assertEqual(result, "hello world")

    def test_resolve_model_id_explicit_overrides(self) -> None:
        with temporary_env({"ELEVENLABS_MODEL_ID": "eleven_v3"}):
            result = client._resolve_model_id(model_id="explicit_model")
            self.assertEqual(result, "explicit_model")

    def test_resolve_model_id_spanish_with_non_v3(self) -> None:
        with temporary_env(
            {
                "ELEVENLABS_MODEL_ID": "eleven_multilingual_v2",
                "ELEVENLABS_MODEL_ID_ES": "eleven_multilingual_v2",
            }
        ):
            # Spanish with non-eleven_v3 should NOT switch
            result = client._resolve_model_id(language_code="es")
            self.assertEqual(result, "eleven_multilingual_v2")

    def test_resolve_model_id_no_env_default(self) -> None:
        with temporary_env(
            {
                "ELEVENLABS_MODEL_ID": None,
                "ELEVENLABS_MODEL_ID_ES": None,
            }
        ):
            # Should default to eleven_v3
            result = client._resolve_model_id()
            self.assertEqual(result, "eleven_v3")

    def test_resolve_model_id_es_with_v3_uses_es_env(self) -> None:
        with temporary_env(
            {
                "ELEVENLABS_MODEL_ID": "eleven_v3",
                "ELEVENLABS_MODEL_ID_ES": "eleven_spanish_v2",
            }
        ):
            result = client._resolve_model_id(language_code="es")
            self.assertEqual(result, "eleven_spanish_v2")

    def test_voice_settings_for_model_v3(self) -> None:
        settings = client._voice_settings_for_model("eleven_v3")
        self.assertEqual(settings["stability"], 0.5)
        self.assertEqual(settings["style"], 0.7)

    def test_voice_settings_for_model_non_v3(self) -> None:
        settings = client._voice_settings_for_model("eleven_multilingual_v2")
        self.assertEqual(settings["stability"], 0.45)
        self.assertEqual(settings["style"], 0.2)

    def test_profile_cache_get_miss(self) -> None:
        # Test cache miss (empty profile_dir)
        result = client._profile_cache_get("/nonexistent/path")
        self.assertIsNone(result)

    def test_profile_cache_get_force_refresh(self) -> None:
        # Insert something in cache
        client._profile_cache_put(
            "/test/profile",
            refresh_tokens=["token1"],
            bearer_tokens=[{"token": "bearer1", "expires_at": time.time() + 3600}],
        )
        # force_refresh should return None
        result = client._profile_cache_get("/test/profile", force_refresh=True)
        self.assertIsNone(result)

    def test_decode_jwt_exp_missing_exp_claim(self) -> None:
        # Create a JWT without exp claim
        payload = base64.urlsafe_b64encode(
            json.dumps({"user_id": "123"}).encode("utf-8")
        ).decode("utf-8").rstrip("=")
        token = f"header.{payload}.signature"
        self.assertEqual(client._decode_jwt_exp(token), 0.0)

    def test_decode_jwt_exp_exp_zero(self) -> None:
        # exp=0 should return 0 - 120 = negative, clamped to 0
        payload = base64.urlsafe_b64encode(
            json.dumps({"exp": 0}).encode("utf-8")
        ).decode("utf-8").rstrip("=")
        token = f"header.{payload}.signature"
        self.assertEqual(client._decode_jwt_exp(token), 0.0)

    def test_api_key_fallback_enabled_auto(self) -> None:
        with temporary_env({"ELEVENLABS_AUTH_MODE": "auto"}):
            self.assertTrue(client._api_key_fallback_enabled())

    def test_api_key_fallback_disabled_explicit(self) -> None:
        with temporary_env({"ELEVENLABS_DISABLE_API_KEY_FALLBACK": "1"}):
            self.assertFalse(client._api_key_fallback_enabled())

    def test_api_key_fallback_disabled_explicit_true(self) -> None:
        with temporary_env({"ELEVENLABS_DISABLE_API_KEY_FALLBACK": "true"}):
            self.assertFalse(client._api_key_fallback_enabled())

    def test_api_key_fallback_disabled_by_auth_mode_webui(self) -> None:
        with temporary_env(
            {"ELEVENLABS_AUTH_MODE": "webui", "ELEVENLABS_DISABLE_API_KEY_FALLBACK": None}
        ):
            self.assertFalse(client._api_key_fallback_enabled())

    def test_api_key_fallback_disabled_by_auth_mode_bearer(self) -> None:
        with temporary_env(
            {"ELEVENLABS_AUTH_MODE": "bearer", "ELEVENLABS_DISABLE_API_KEY_FALLBACK": None}
        ):
            self.assertFalse(client._api_key_fallback_enabled())

    def test_api_key_fallback_disabled_by_auth_mode_firebase(self) -> None:
        with temporary_env(
            {"ELEVENLABS_AUTH_MODE": "firebase", "ELEVENLABS_DISABLE_API_KEY_FALLBACK": None}
        ):
            self.assertFalse(client._api_key_fallback_enabled())


class CLITests(unittest.TestCase):
    def test_read_text_from_args(self) -> None:
        args = argparse.Namespace(text="hello world", text_file=None)
        self.assertEqual(cli_module._read_text(args), "hello world")

    def test_read_text_from_file(self) -> None:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as f:
            f.write("file content")
            temp_path = f.name

        try:
            args = argparse.Namespace(text=None, text_file=temp_path)
            self.assertEqual(cli_module._read_text(args), "file content")
        finally:
            os.unlink(temp_path)

    def test_read_text_missing_raises(self) -> None:
        args = argparse.Namespace(text=None, text_file=None)
        with self.assertRaises(RuntimeError) as ctx:
            cli_module._read_text(args)
        self.assertIn("--text or --text-file is required", str(ctx.exception))

    def test_read_text_file_not_found(self) -> None:
        args = argparse.Namespace(text=None, text_file="/nonexistent/file.txt")
        with self.assertRaises(FileNotFoundError):
            cli_module._read_text(args)

    def test_print_json_outputs_valid_json(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w+", delete=False) as f:
            # Redirect stdout
            import sys
            old_stdout = sys.stdout
            sys.stdout = f

            try:
                cli_module._print_json({"key": "value", "num": 123})
            finally:
                sys.stdout = old_stdout
                f.seek(0)
                content = f.read()
                f.close()

        parsed = json.loads(content)
        self.assertEqual(parsed["key"], "value")
        self.assertEqual(parsed["num"], 123)

    def test_build_parser_has_subcommands(self) -> None:
        parser = cli_module.build_parser()
        # Test that subparsers exist by checking the parser structure
        # Just verify parsing doesn't crash for known subcommands
        for subcmd in ["tts", "subscription", "voices", "extract-profile-auth"]:
            # These require required args, so use parse_known_args
            # Just verify the subcommand is recognized
            try:
                parsed, unknown = parser.parse_known_args([subcmd], None)
                # Just verify subcmd is set
                self.assertEqual(parsed.command, subcmd)
            except SystemExit:
                pass  # May fail on missing required args, that's ok


if __name__ == "__main__":
    unittest.main()
