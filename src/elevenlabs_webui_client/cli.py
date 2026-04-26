from __future__ import annotations

import argparse
import json
from pathlib import Path

from .client import (
    extract_profile_auth,
    format_refresh_tokens_env_line,
    get_subscription,
    list_voices,
    tts_to_mp3,
)


def _read_text(args: argparse.Namespace) -> str:
    """Read TTS input text from --text or --text-file."""
    if args.text is not None:
        return args.text
    if args.text_file is None:
        raise RuntimeError("Either --text or --text-file is required.")
    return Path(args.text_file).read_text(encoding="utf-8")


def _print_json(payload: object) -> None:
    """Pretty-print a Python object as indented JSON."""
    print(json.dumps(payload, indent=2, sort_keys=True))


def _cmd_tts(args: argparse.Namespace) -> int:
    """Handle the `tts` subcommand — synthesize speech to an MP3 file."""
    text = _read_text(args)
    tts_to_mp3(
        voice_id=args.voice_id,
        text=text,
        out_path=args.out,
        model_id=args.model_id,
        salt=args.salt,
        language_code=args.language_code,
        alignment_out_path=args.alignment_out,
    )
    if args.json:
        _print_json({"ok": True, "out_path": args.out, "alignment_out": args.alignment_out})
    else:
        print(args.out)
    return 0


def _cmd_subscription(args: argparse.Namespace) -> int:
    """Handle the `subscription` subcommand — fetch and print subscription info."""
    subscription = get_subscription(salt=args.salt)
    _print_json(subscription)
    return 0


def _cmd_voices(args: argparse.Namespace) -> int:
    """Handle the `voices` subcommand — list available voices."""
    payload = list_voices(salt=args.salt)
    if args.json:
        _print_json(payload)
        return 0

    voices_raw = payload.get("voices")
    if not isinstance(voices_raw, list):
        _print_json(payload)
        return 0

    compact_rows = []
    for voice in voices_raw:
        if not isinstance(voice, dict):
            continue
        compact_rows.append(
            {
                "name": voice.get("name"),
                "voice_id": voice.get("voice_id"),
                "category": voice.get("category"),
            }
        )

    _print_json({"voices": compact_rows})
    return 0


def _cmd_extract_profile_auth(args: argparse.Namespace) -> int:
    """Handle the `extract-profile-auth` subcommand — extract auth from a browser profile."""
    refresh_tokens, bearer_tokens = extract_profile_auth(args.profile_dir)

    if args.print_env:
        print(format_refresh_tokens_env_line(refresh_tokens))
        return 0

    if args.show_refresh_tokens:
        for token in refresh_tokens:
            print(token)
        return 0

    if args.show_bearer_tokens:
        for token_info in bearer_tokens:
            token = str(token_info.get("token") or "").strip()
            if token:
                print(token)
        return 0

    payload = {
        "refresh_token_count": len(refresh_tokens),
        "bearer_token_count": len(bearer_tokens),
    }
    _print_json(payload)
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the elevenlabs-webui CLI."""
    parser = argparse.ArgumentParser(prog="elevenlabs-webui")
    subparsers = parser.add_subparsers(dest="command", required=True)

    tts_parser = subparsers.add_parser("tts", help="Synthesize speech to an MP3 file.")
    tts_group = tts_parser.add_mutually_exclusive_group(required=True)
    tts_group.add_argument("--text")
    tts_group.add_argument("--text-file")
    tts_parser.add_argument("--voice-id", required=True)
    tts_parser.add_argument("--out", required=True)
    tts_parser.add_argument("--model-id")
    tts_parser.add_argument("--language-code")
    tts_parser.add_argument("--alignment-out")
    tts_parser.add_argument("--salt", default="cli:tts")
    tts_parser.add_argument("--json", action="store_true")
    tts_parser.set_defaults(func=_cmd_tts)

    subscription_parser = subparsers.add_parser(
        "subscription",
        help="Fetch the current ElevenLabs subscription payload.",
    )
    subscription_parser.add_argument("--salt", default="cli:subscription")
    subscription_parser.set_defaults(func=_cmd_subscription)

    voices_parser = subparsers.add_parser(
        "voices",
        help="Fetch available voices.",
    )
    voices_parser.add_argument("--salt", default="cli:voices")
    voices_parser.add_argument("--json", action="store_true")
    voices_parser.set_defaults(func=_cmd_voices)

    extract_parser = subparsers.add_parser(
        "extract-profile-auth",
        help="Read ElevenLabs auth state from a logged-in browser profile.",
    )
    extract_parser.add_argument("--profile-dir", required=True)
    extract_parser.add_argument("--print-env", action="store_true")
    extract_parser.add_argument("--show-refresh-tokens", action="store_true")
    extract_parser.add_argument("--show-bearer-tokens", action="store_true")
    extract_parser.set_defaults(func=_cmd_extract_profile_auth)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point for the elevenlabs-webui CLI."""
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))
