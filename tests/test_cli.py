"""Tests for the elevenlabs-webui CLI."""

from __future__ import annotations

import unittest

from elevenlabs_webui_client import cli


class CLITests(unittest.TestCase):
    def test_build_parser_returns_valid_parser(self) -> None:
        parser = cli.build_parser()
        self.assertIsNotNone(parser)

    def test_build_parser_has_subcommands(self) -> None:
        parser = cli.build_parser()
        # The parser should have subcommands configured
        self.assertIsNotNone(parser._subparsers)

    def test_parse_tts_subcommand(self) -> None:
        parser = cli.build_parser()
        args = parser.parse_args([
            "tts",
            "--text", "hello",
            "--voice-id", "voice123",
            "--out", "/tmp/out.mp3",
        ])
        self.assertEqual(args.command, "tts")
        self.assertEqual(args.text, "hello")
        self.assertEqual(args.voice_id, "voice123")
        self.assertEqual(args.out, "/tmp/out.mp3")

    def test_parse_subscription_subcommand(self) -> None:
        parser = cli.build_parser()
        args = parser.parse_args(["subscription"])
        self.assertEqual(args.command, "subscription")

    def test_parse_voices_subcommand(self) -> None:
        parser = cli.build_parser()
        args = parser.parse_args(["voices"])
        self.assertEqual(args.command, "voices")

    def test_parse_extract_profile_auth_subcommand(self) -> None:
        parser = cli.build_parser()
        args = parser.parse_args([
            "extract-profile-auth",
            "--profile-dir", "/tmp/profile",
        ])
        self.assertEqual(args.command, "extract-profile-auth")
        self.assertEqual(args.profile_dir, "/tmp/profile")

    def test_tts_requires_voice_id(self) -> None:
        parser = cli.build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args([
                "tts",
                "--text", "hello",
                # missing --voice-id
                "--out", "/tmp/out.mp3",
            ])

    def test_tts_requires_text_or_text_file(self) -> None:
        parser = cli.build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args([
                "tts",
                "--voice-id", "voice123",
                "--out", "/tmp/out.mp3",
                # missing --text or --text-file
            ])

    def test_extract_profile_auth_requires_profile_dir(self) -> None:
        parser = cli.build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["extract-profile-auth"])


if __name__ == "__main__":
    unittest.main()