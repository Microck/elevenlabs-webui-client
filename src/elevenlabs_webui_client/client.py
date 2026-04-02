from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

FIREBASE_API_KEY = "AIzaSyBSsRE_1Os04-bxpd5JTLIniy3UK4OqKys"
FIREBASE_GMP_ID = "1:351805251172:web:35c6c5d4e1d9a55a6f4b8f"
FIREBASE_TOKEN_URL = (
    f"https://securetoken.googleapis.com/v1/token?key={FIREBASE_API_KEY}"
)
ELEVENLABS_API_BASE_URL = "https://api.elevenlabs.io/v1"

_bearer_cache: dict[str, dict[str, object]] = {}
_webui_profile_auth_cache: dict[str, dict[str, object]] = {}


def _debug(message: str) -> None:
    if os.environ.get("ELEVENLABS_DEBUG", "").strip() == "1":
        print(message)


def _token_cache_key(refresh_token: str) -> str:
    return hashlib.sha256(refresh_token.encode("utf-8")).hexdigest()


def _refresh_bearer_token(refresh_token: str) -> tuple[str, float]:
    data = urllib.parse.urlencode(
        {"grant_type": "refresh_token", "refresh_token": refresh_token}
    ).encode("utf-8")

    request = urllib.request.Request(
        FIREBASE_TOKEN_URL,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": "https://elevenlabs.io/",
            "Origin": "https://elevenlabs.io",
            "User-Agent": "Mozilla/5.0",
            "X-Client-Version": "Firefox/JsCore/11.0.2/FirebaseCore-web",
            "X-Firebase-gmpid": FIREBASE_GMP_ID,
        },
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        result = json.loads(response.read().decode("utf-8"))

    id_token = str(result["id_token"])
    expires_in = int(result.get("expires_in", 3600))
    expires_at = time.time() + expires_in - 120
    return id_token, expires_at


def _auth_mode() -> str:
    mode = os.environ.get("ELEVENLABS_AUTH_MODE", "auto").strip().lower()
    if mode in {"auto", "webui", "bearer", "firebase", "api"}:
        return mode
    return "auto"


def _web_session_auth_enabled() -> bool:
    return _auth_mode() in {"auto", "webui", "bearer", "firebase"}


def _get_profile_refresh_interval_seconds() -> int:
    raw = os.environ.get("ELEVENLABS_WEBUI_PROFILE_REFRESH_SECONDS", "").strip()
    if not raw:
        return 900
    try:
        value = int(raw)
    except ValueError:
        return 900
    return max(0, min(value, 86400))


def _profile_cache_get(
    profile_dir: str, *, force_refresh: bool = False
) -> dict[str, object] | None:
    now = time.time()
    refresh_every = _get_profile_refresh_interval_seconds()
    cached = _webui_profile_auth_cache.get(profile_dir)
    if cached is None or force_refresh:
        return None

    fetched_at_raw = cached.get("fetched_at", 0.0)
    fetched_at = (
        float(fetched_at_raw) if isinstance(fetched_at_raw, (int, float)) else 0.0
    )
    if refresh_every == 0 or (now - fetched_at) <= refresh_every:
        return cached
    return None


def _profile_cache_put(
    profile_dir: str,
    *,
    refresh_tokens: list[str],
    bearer_tokens: list[dict[str, object]],
) -> None:
    _webui_profile_auth_cache[profile_dir] = {
        "refresh_tokens": list(refresh_tokens),
        "bearer_tokens": list(bearer_tokens),
        "fetched_at": time.time(),
    }


def _launch_profile_context(playwright, profile_dir: str):
    if os.path.exists(os.path.join(profile_dir, "cookies.sqlite")):
        return playwright.firefox.launch_persistent_context(
            user_data_dir=profile_dir,
            headless=True,
        )

    return playwright.chromium.launch_persistent_context(
        user_data_dir=profile_dir,
        headless=True,
        args=["--no-sandbox", "--disable-dev-shm-usage"],
    )


def _decode_jwt_exp(token: str) -> float:
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return 0.0
        payload_b64 = parts[1] + "=" * (-len(parts[1]) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64.encode("utf-8")))
        exp = payload.get("exp")
        if isinstance(exp, (int, float)):
            return max(0.0, float(exp) - 120.0)
    except Exception:
        return 0.0
    return 0.0


def extract_profile_auth(profile_dir: str) -> tuple[list[str], list[dict[str, object]]]:
    """Extract Firebase auth tokens from a logged-in browser profile.

    Launches a headless browser (Chromium or Firefox, depending on profile
    contents), navigates to the ElevenLabs speech synthesis page, and reads
    refresh tokens and bearer tokens from ``localStorage``.

    Requires the ``browser`` optional dependency (``pip install '.[browser]'``)
    and a Playwright browser installation.

    Args:
        profile_dir: Path to the browser profile directory.

    Returns:
        A tuple of ``(refresh_tokens, bearer_tokens)``.  Bearer tokens
        include ``"token"`` and ``"expires_at"`` keys.

    Raises:
        RuntimeError: If Playwright is not installed.
    """
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise RuntimeError(
            "Playwright is required for browser profile extraction. "
            "Install the optional browser extra with `pip install '.[browser]'`."
        ) from exc

    refresh_tokens: list[str] = []
    bearer_tokens: list[dict[str, object]] = []
    with sync_playwright() as playwright:
        context = _launch_profile_context(playwright, profile_dir)
        try:
            page = context.new_page()
            page.goto(
                "https://elevenlabs.io/app/speech-synthesis",
                wait_until="domcontentloaded",
                timeout=30000,
            )
            page.wait_for_timeout(1200)
            extracted = page.evaluate(
                """
                () => {
                  const refreshTokens = [];
                  const bearerTokens = [];
                  const seenRefresh = new Set();
                  const seenBearer = new Set();

                  const addRefresh = (value) => {
                    if (!value || typeof value !== "string") return;
                    const normalized = value.trim();
                    if (!normalized || seenRefresh.has(normalized)) return;
                    seenRefresh.add(normalized);
                    refreshTokens.push(normalized);
                  };

                  const addBearer = (value) => {
                    if (!value || typeof value !== "string") return;
                    const normalized = value.trim();
                    if (!normalized || seenBearer.has(normalized)) return;
                    seenBearer.add(normalized);
                    bearerTokens.push(normalized);
                  };

                  for (const key of Object.keys(localStorage)) {
                    const raw = localStorage.getItem(key);
                    if (!raw) continue;
                    try {
                      const parsed = JSON.parse(raw);
                      addRefresh(parsed?.stsTokenManager?.refreshToken);
                      addRefresh(parsed?.user?.stsTokenManager?.refreshToken);
                      addRefresh(parsed?.authUser?.stsTokenManager?.refreshToken);
                      addBearer(parsed?.stsTokenManager?.accessToken);
                      addBearer(parsed?.user?.stsTokenManager?.accessToken);
                      addBearer(parsed?.authUser?.stsTokenManager?.accessToken);
                    } catch (_) {
                      // ignore malformed rows
                    }
                  }

                  return { refreshTokens, bearerTokens };
                }
                """
            )
        finally:
            context.close()

    if isinstance(extracted, dict):
        refresh_raw = extracted.get("refreshTokens")
        bearer_raw = extracted.get("bearerTokens")
        if isinstance(refresh_raw, list):
            refresh_tokens = [str(item).strip() for item in refresh_raw if str(item).strip()]
        if isinstance(bearer_raw, list):
            for raw_token in bearer_raw:
                token = str(raw_token).strip()
                if not token:
                    continue
                expires_at = _decode_jwt_exp(token)
                if expires_at > time.time():
                    bearer_tokens.append({"token": token, "expires_at": expires_at})

    return refresh_tokens, bearer_tokens


def _get_profile_refresh_tokens(
    profile_dir: str, *, force_refresh: bool = False
) -> list[str]:
    cached = _profile_cache_get(profile_dir, force_refresh=force_refresh)
    if cached is not None:
        tokens_raw = cached.get("refresh_tokens")
        if isinstance(tokens_raw, list):
            return [str(item).strip() for item in tokens_raw if str(item).strip()]

    refresh_tokens, bearer_tokens = extract_profile_auth(profile_dir)
    _profile_cache_put(
        profile_dir,
        refresh_tokens=refresh_tokens,
        bearer_tokens=bearer_tokens,
    )
    return refresh_tokens


def _get_profile_bearer_tokens(
    profile_dir: str, *, force_refresh: bool = False
) -> list[str]:
    cached = _profile_cache_get(profile_dir, force_refresh=force_refresh)
    if cached is not None:
        bearer_tokens_raw = cached.get("bearer_tokens")
        if isinstance(bearer_tokens_raw, list):
            output: list[str] = []
            now = time.time()
            for item in bearer_tokens_raw:
                if not isinstance(item, dict):
                    continue
                token = str(item.get("token") or "").strip()
                expires_at_raw = item.get("expires_at")
                expires_at = (
                    float(expires_at_raw)
                    if isinstance(expires_at_raw, (int, float))
                    else 0.0
                )
                if token and now < expires_at:
                    output.append(token)
            return output

    refresh_tokens, bearer_tokens = extract_profile_auth(profile_dir)
    _profile_cache_put(
        profile_dir,
        refresh_tokens=refresh_tokens,
        bearer_tokens=bearer_tokens,
    )
    now = time.time()
    output: list[str] = []
    for item in bearer_tokens:
        token = str(item.get("token") or "").strip()
        expires_at_raw = item.get("expires_at")
        expires_at = (
            float(expires_at_raw) if isinstance(expires_at_raw, (int, float)) else 0.0
        )
        if token and now < expires_at:
            output.append(token)
    return output


def _get_refresh_tokens(*, force_profile_refresh: bool = False) -> list[str]:
    profile_dir = os.environ.get("ELEVENLABS_WEBUI_PROFILE_DIR", "").strip()
    profile_tokens: list[str] = []
    if profile_dir:
        profile_tokens = _get_profile_refresh_tokens(
            profile_dir,
            force_refresh=force_profile_refresh,
        )

    raw_many = os.environ.get("ELEVENLABS_FIREBASE_REFRESH_TOKENS", "")
    raw_one = os.environ.get("ELEVENLABS_FIREBASE_REFRESH_TOKEN", "")
    tokens: list[str] = []
    tokens.extend(profile_tokens)
    for raw in (raw_many, raw_one):
        tokens.extend(part.strip() for part in raw.split(",") if part.strip())

    seen: set[str] = set()
    output: list[str] = []
    for token in tokens:
        if token in seen:
            continue
        seen.add(token)
        output.append(token)
    return output


def _api_key_fallback_enabled() -> bool:
    disable = os.environ.get("ELEVENLABS_DISABLE_API_KEY_FALLBACK", "").strip().lower()
    if disable in {"1", "true", "yes", "on"}:
        return False
    return _auth_mode() not in {"webui", "bearer", "firebase"}


def _get_bearer_token_for(refresh_token: str, *, force_refresh: bool = False) -> str:
    cache_key = _token_cache_key(refresh_token)
    cached = _bearer_cache.get(cache_key)
    if not force_refresh and cached:
        token = cached.get("token")
        expires_at_raw = cached.get("expires_at", 0.0)
        expires_at = (
            float(expires_at_raw) if isinstance(expires_at_raw, (int, float)) else 0.0
        )
        if token and time.time() < expires_at:
            return str(token)

    token, expires_at = _refresh_bearer_token(refresh_token)
    _bearer_cache[cache_key] = {"token": token, "expires_at": expires_at}
    return token


def _stable_index(seed: str, count: int) -> int:
    if count <= 1:
        return 0
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") % count


def _get_api_keys() -> list[str]:
    raw = os.environ.get("ELEVENLABS_API_KEYS") or os.environ.get("ELEVENLABS_API_KEY") or ""
    return [value.strip() for value in raw.split(",") if value.strip()]


def _read_http_error_body(error: urllib.error.HTTPError) -> str:
    try:
        body = error.read()
    except Exception:
        return ""
    if isinstance(body, bytes):
        return body.decode("utf-8", "replace")
    return str(body)


def _should_rotate_credential(code: int, body_text: str) -> bool:
    if code in {401, 402, 403, 404, 429}:
        return True

    if code == 400:
        lowered = body_text.lower()
        if (
            "invalid_refresh_token" in lowered
            or "refresh_token" in lowered
            or "invalid_grant" in lowered
            or "token_expired" in lowered
        ):
            return True

    lowered = body_text.lower()
    keywords = (
        "quota",
        "credit",
        "limit",
        "exceeded",
        "payment_required",
        "insufficient",
        "rate",
    )
    return any(keyword in lowered for keyword in keywords)


def _http_request(
    url: str,
    *,
    method: str = "GET",
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 120,
) -> bytes:
    request = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers=headers or {},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def _request_with_auth(
    url: str,
    *,
    method: str = "GET",
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
    salt: str = "default",
    timeout: int = 120,
) -> bytes:
    base_headers = dict(headers or {})
    last_http: tuple[str, int, str] | None = None

    def perform(extra_headers: dict[str, str]) -> bytes:
        merged_headers = dict(base_headers)
        merged_headers.update(extra_headers)
        return _http_request(
            url,
            method=method,
            body=body,
            headers=merged_headers,
            timeout=timeout,
        )

    if _web_session_auth_enabled():
        profile_dir = os.environ.get("ELEVENLABS_WEBUI_PROFILE_DIR", "").strip()
        max_passes = 2 if profile_dir else 1
        for pass_index in range(max_passes):
            if profile_dir:
                profile_bearers = _get_profile_bearer_tokens(
                    profile_dir,
                    force_refresh=(pass_index > 0),
                )
                for bearer in profile_bearers:
                    try:
                        return perform({"Authorization": f"Bearer {bearer}"})
                    except urllib.error.HTTPError as error:
                        body_text = _read_http_error_body(error)
                        last_http = (
                            "profile_bearer",
                            int(getattr(error, "code", 0) or 0),
                            body_text,
                        )
                        if _should_rotate_credential(error.code, body_text):
                            _debug(
                                f"ElevenLabs profile bearer failed with HTTP {error.code}; trying next credential."
                            )
                            continue
                        raise RuntimeError(
                            f"ElevenLabs profile bearer request failed (HTTP {error.code}): {body_text[:400]}"
                        ) from error
                    except Exception as error:
                        _debug(
                            f"ElevenLabs profile bearer attempt failed ({type(error).__name__}); trying next credential."
                        )
                        continue

            refresh_tokens = _get_refresh_tokens(force_profile_refresh=(pass_index > 0))
            if not refresh_tokens:
                break

            start = _stable_index(salt, len(refresh_tokens))
            for index in range(len(refresh_tokens)):
                refresh_token = refresh_tokens[(start + index) % len(refresh_tokens)]
                try:
                    bearer = _get_bearer_token_for(refresh_token)
                    return perform({"Authorization": f"Bearer {bearer}"})
                except urllib.error.HTTPError as error:
                    body_text = _read_http_error_body(error)
                    last_http = (
                        "bearer",
                        int(getattr(error, "code", 0) or 0),
                        body_text,
                    )
                    if error.code == 401:
                        try:
                            refreshed_bearer = _get_bearer_token_for(
                                refresh_token,
                                force_refresh=True,
                            )
                            return perform({"Authorization": f"Bearer {refreshed_bearer}"})
                        except urllib.error.HTTPError as retry_error:
                            retry_body = _read_http_error_body(retry_error)
                            last_http = (
                                "bearer",
                                int(getattr(retry_error, "code", 0) or 0),
                                retry_body,
                            )

                    if _should_rotate_credential(error.code, body_text):
                        _debug(
                            f"ElevenLabs bearer credential failed with HTTP {error.code}; trying next credential."
                        )
                        continue
                    raise RuntimeError(
                        f"ElevenLabs bearer request failed (HTTP {error.code}): {body_text[:400]}"
                    ) from error
                except Exception as error:
                    _debug(
                        f"ElevenLabs bearer attempt failed ({type(error).__name__}); trying next credential."
                    )
                    continue

            if pass_index == 0 and max_passes > 1:
                _debug(
                    "ElevenLabs bearer auth failed for all credentials; refreshing browser-profile auth and retrying once."
                )

    if not _api_key_fallback_enabled():
        if last_http is not None:
            kind, code, body_text = last_http
            raise RuntimeError(
                "ElevenLabs WebUI auth failed and API-key fallback is disabled. "
                f"Last error: {kind} HTTP {code}: {body_text[:400]}"
            )
        raise RuntimeError(
            "ElevenLabs WebUI auth failed and API-key fallback is disabled. "
            "Set ELEVENLABS_FIREBASE_REFRESH_TOKEN(S) or provide ELEVENLABS_WEBUI_PROFILE_DIR."
        )

    api_keys = _get_api_keys()
    if api_keys:
        start = _stable_index(salt, len(api_keys))
        for index in range(len(api_keys)):
            api_key = api_keys[(start + index) % len(api_keys)]
            try:
                return perform({"xi-api-key": api_key})
            except urllib.error.HTTPError as error:
                body_text = _read_http_error_body(error)
                last_http = (
                    "api_key",
                    int(getattr(error, "code", 0) or 0),
                    body_text,
                )
                if _should_rotate_credential(error.code, body_text):
                    _debug(
                        f"ElevenLabs API key failed with HTTP {error.code}; trying next credential."
                    )
                    continue
                raise RuntimeError(
                    f"ElevenLabs API-key request failed (HTTP {error.code}): {body_text[:400]}"
                ) from error
            except Exception as error:
                _debug(
                    f"ElevenLabs API-key attempt failed ({type(error).__name__}); trying next credential."
                )
                continue

        if last_http is not None:
            kind, code, body_text = last_http
            raise RuntimeError(
                "ElevenLabs request failed after rotating credentials. "
                f"Last error: {kind} HTTP {code}: {body_text[:400]}"
            )
        raise RuntimeError("ElevenLabs request failed after rotating credentials.")

    if last_http is not None:
        kind, code, body_text = last_http
        raise RuntimeError(
            "ElevenLabs request failed and no API keys are configured. "
            f"Last error: {kind} HTTP {code}: {body_text[:400]}"
        )

    raise RuntimeError(
        "ElevenLabs request failed: no ELEVENLABS_FIREBASE_REFRESH_TOKENS/REFRESH_TOKEN "
        "and no ELEVENLABS_API_KEYS are configured."
    )


def _request_json(
    url: str,
    *,
    method: str = "GET",
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
    salt: str = "default",
    timeout: int = 120,
) -> dict[str, object]:
    response = _request_with_auth(
        url,
        method=method,
        body=body,
        headers=headers,
        salt=salt,
        timeout=timeout,
    )
    try:
        parsed = json.loads(response.decode("utf-8"))
    except Exception as exc:
        raise RuntimeError(
            f"ElevenLabs returned invalid JSON from {url}."
        ) from exc
    if not isinstance(parsed, dict):
        raise RuntimeError(f"ElevenLabs returned unexpected JSON from {url}.")
    return parsed


def sanitize_tts_text(text: str) -> str:
    """Strip markdown, brackets, and parentheses from text before sending to TTS.

    Markdown images ``![alt](url)`` become whitespace. Links ``[text](url)``
    become the label text. Remaining bracket/parenthesis groups are removed.
    Whitespace is normalised to single spaces.

    Args:
        text: Raw input text that may contain markdown or stage directions.

    Returns:
        Cleaned string safe for TTS synthesis.
    """
    sanitized = str(text or "")
    sanitized = re.sub(r"!\[[^\]]*\]\([^)]+\)", " ", sanitized)
    sanitized = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", sanitized)
    sanitized = re.sub(r"!\s*\([^)]+\)", " ", sanitized)
    sanitized = re.sub(r"\[[^\]]+\]", " ", sanitized)
    sanitized = re.sub(r"\([^)]{1,120}\)", " ", sanitized)
    return " ".join(sanitized.replace("\r", " ").replace("\n", " ").split())


def _resolve_model_id(
    *, model_id: str | None = None, language_code: str | None = None
) -> str:
    resolved = model_id or os.environ.get("ELEVENLABS_MODEL_ID") or "eleven_v3"
    language = (language_code or "").strip().lower()
    if language == "es" and resolved == "eleven_v3":
        return os.environ.get("ELEVENLABS_MODEL_ID_ES") or "eleven_multilingual_v2"
    return resolved


def _voice_settings_for_model(model_id: str) -> dict[str, object]:
    if model_id == "eleven_v3":
        return {
            "stability": 0.5,
            "similarity_boost": 0.8,
            "style": 0.7,
            "use_speaker_boost": True,
        }
    return {
        "stability": 0.45,
        "similarity_boost": 0.8,
        "style": 0.2,
        "use_speaker_boost": True,
    }


def format_refresh_tokens_env_line(tokens: list[str]) -> str:
    """Format refresh tokens as an ``ELEVENLABS_FIREBASE_REFRESH_TOKENS=...`` export line.

    Args:
        tokens: List of Firebase refresh tokens.

    Returns:
        A string suitable for shell evaluation or ``.env`` inclusion.
    """
    return f"ELEVENLABS_FIREBASE_REFRESH_TOKENS={','.join(tokens)}"


def tts_to_mp3(
    *,
    voice_id: str,
    text: str,
    out_path: str,
    model_id: str | None = None,
    salt: str = "default",
    language_code: str | None = None,
    alignment_out_path: str | None = None,
) -> None:
    """Synthesize text to an MP3 file using the ElevenLabs TTS API.

    Text is sanitised via :func:`sanitize_tts_text` before synthesis.
    The model defaults to ``eleven_v3`` unless overridden by
    ``ELEVENLABS_MODEL_ID`` or the *model_id* parameter.  When the resolved
    model is ``eleven_v3`` and *language_code* is ``es``, the model switches
    to ``eleven_multilingual_v2`` (or ``ELEVENLABS_MODEL_ID_ES``).

    Args:
        voice_id: ElevenLabs voice identifier.
        text: Text to synthesize (markdown is stripped automatically).
        out_path: Destination file path for the MP3 output.
        model_id: Optional model override (e.g. ``"eleven_multilingual_v2"``).
        salt: Influences stable credential rotation order.
        language_code: Optional language hint for multilingual models.
        alignment_out_path: If set, timestamp alignment JSON is written here.
    """
    resolved_model = _resolve_model_id(model_id=model_id, language_code=language_code)
    normalized_language = (language_code or "").strip().lower()
    use_timestamps = bool(str(alignment_out_path or "").strip())
    url = (
        f"{ELEVENLABS_API_BASE_URL}/text-to-speech/{voice_id}/with-timestamps"
        if use_timestamps
        else f"{ELEVENLABS_API_BASE_URL}/text-to-speech/{voice_id}"
    )

    payload: dict[str, object] = {
        "text": sanitize_tts_text(text),
        "model_id": resolved_model,
        "voice_settings": _voice_settings_for_model(resolved_model),
    }
    if normalized_language and resolved_model != "eleven_v3":
        payload["language_code"] = normalized_language

    response = _request_with_auth(
        url,
        method="POST",
        body=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json" if use_timestamps else "audio/mpeg",
        },
        salt=salt,
    )

    audio_bytes = response
    if use_timestamps:
        try:
            parsed = json.loads(response.decode("utf-8"))
        except Exception as exc:
            raise RuntimeError(
                "ElevenLabs with-timestamps response was not valid JSON."
            ) from exc
        if not isinstance(parsed, dict):
            raise RuntimeError("ElevenLabs with-timestamps response shape was invalid.")

        audio_base64 = str(parsed.get("audio_base64") or "").strip()
        if not audio_base64:
            raise RuntimeError("ElevenLabs with-timestamps response did not include audio_base64.")

        try:
            audio_bytes = base64.b64decode(audio_base64)
        except Exception as exc:
            raise RuntimeError(
                "ElevenLabs with-timestamps audio_base64 could not be decoded."
            ) from exc

        if alignment_out_path:
            alignment = parsed.get("normalized_alignment") or parsed.get("alignment") or {}
            os.makedirs(os.path.dirname(alignment_out_path) or ".", exist_ok=True)
            with open(alignment_out_path, "w", encoding="utf-8") as handle:
                json.dump(alignment if isinstance(alignment, dict) else {}, handle)
                handle.write("\n")

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "wb") as handle:
        handle.write(audio_bytes)


def get_subscription(*, salt: str = "subscription") -> dict[str, object]:
    """Fetch the current ElevenLabs subscription details.

    Calls ``GET /v1/user/subscription`` using the configured auth chain.

    Args:
        salt: Influences stable credential rotation order.

    Returns:
        Parsed JSON response from the ElevenLabs API.
    """
    return _request_json(
        f"{ELEVENLABS_API_BASE_URL}/user/subscription",
        headers={"Accept": "application/json"},
        salt=salt,
    )


def list_voices(*, salt: str = "voices") -> dict[str, object]:
    """Fetch available ElevenLabs voices.

    Calls ``GET /v1/voices`` using the configured auth chain.

    Args:
        salt: Influences stable credential rotation order.

    Returns:
        Parsed JSON response containing a ``"voices"`` list.
    """
    return _request_json(
        f"{ELEVENLABS_API_BASE_URL}/voices",
        headers={"Accept": "application/json"},
        salt=salt,
    )
