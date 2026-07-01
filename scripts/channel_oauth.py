from __future__ import annotations

import json
import os
import tempfile
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from scripts import channel_workspace


Transport = Callable[..., dict[str, Any]]


class OAuthServiceError(Exception):
    pass


class OAuthConfigurationError(OAuthServiceError):
    pass


class TokenMissingError(OAuthServiceError):
    pass


class ReconnectRequiredError(OAuthServiceError):
    pass


class OAuthExchangeError(OAuthServiceError):
    pass


class AuthenticatedChannelMissingError(OAuthServiceError):
    pass


class ChannelIdentityMismatchError(OAuthServiceError):
    pass


class ChannelAlreadyExistsError(OAuthServiceError):
    pass


class MalformedTokenError(OAuthServiceError):
    pass


class OAuthNetworkError(OAuthServiceError):
    pass


class ChannelWorkspaceMissingError(OAuthServiceError):
    pass


@dataclass(frozen=True)
class OAuthClientConfig:
    client_id: str
    client_secret: str
    auth_uri: str
    token_uri: str
    redirect_uris: tuple[str, ...]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def oauth_client_file(root: Path | str) -> Path:
    return Path(root).resolve() / "youtube_oauth_client.json"


def load_oauth_client_config(root: Path | str) -> OAuthClientConfig:
    path = oauth_client_file(root)
    if not path.exists():
        raise OAuthConfigurationError("OAuth client configuration file is missing.")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise OAuthConfigurationError("OAuth client configuration is malformed JSON.") from exc

    installed = payload.get("installed")
    if not isinstance(installed, dict):
        if "web" in payload:
            raise OAuthConfigurationError("OAuth client configuration must use the Desktop installed format.")
        raise OAuthConfigurationError("OAuth client configuration is missing the installed section.")

    required = ("client_id", "client_secret", "auth_uri", "token_uri")
    missing = [field for field in required if not isinstance(installed.get(field), str) or not installed.get(field).strip()]
    if missing:
        raise OAuthConfigurationError("OAuth client configuration is missing required Desktop client fields.")

    redirect_uris = installed.get("redirect_uris")
    if not isinstance(redirect_uris, list) or not any(isinstance(item, str) and item.strip() for item in redirect_uris):
        raise OAuthConfigurationError("OAuth client configuration must include redirect URI support.")

    return OAuthClientConfig(
        client_id=installed["client_id"].strip(),
        client_secret=installed["client_secret"].strip(),
        auth_uri=installed["auth_uri"].strip(),
        token_uri=installed["token_uri"].strip(),
        redirect_uris=tuple(item.strip() for item in redirect_uris if isinstance(item, str) and item.strip()),
    )


def _call_transport(transport: Transport, *, method: str, url: str, headers: dict[str, str] | None = None, data: bytes | None = None) -> dict[str, Any]:
    try:
        return transport(method=method, url=url, headers=headers or {}, data=data)
    except OAuthServiceError:
        raise
    except Exception as exc:
        raise OAuthNetworkError(str(exc)) from exc


def _expires_at_from_now(expires_in: Any) -> str:
    try:
        seconds = int(expires_in)
    except (TypeError, ValueError) as exc:
        raise MalformedTokenError("Token payload is missing a valid expires_in value.") from exc
    return (utc_now() + timedelta(seconds=seconds)).replace(microsecond=0).isoformat()


def _validate_token_payload(data: dict[str, Any], *, require_refresh_token: bool = False) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise MalformedTokenError("Token payload is malformed.")
    access_token = data.get("access_token")
    token_type = data.get("token_type")
    if not isinstance(access_token, str) or not access_token.strip():
        raise MalformedTokenError("Token payload is missing access_token.")
    if not isinstance(token_type, str) or not token_type.strip():
        raise MalformedTokenError("Token payload is missing token_type.")
    if require_refresh_token and not isinstance(data.get("refresh_token"), str):
        raise ReconnectRequiredError("Token refresh requires reconnect because no refresh token is stored.")
    if "expires_at" in data:
        parsed = datetime.fromisoformat(data["expires_at"])
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise MalformedTokenError("Token expires_at must be timezone-aware.")
    return data


def _sanitize_identity_item(item: dict[str, Any]) -> dict[str, Any]:
    channel_id = item.get("id")
    if not isinstance(channel_id, str) or not channel_id.strip():
        raise AuthenticatedChannelMissingError("Authenticated channel response is missing a YouTube channel ID.")
    snippet = item.get("snippet") or {}
    display_name = snippet.get("title")
    if not isinstance(display_name, str) or not display_name.strip():
        raise AuthenticatedChannelMissingError("Authenticated channel response is missing a channel title.")
    handle = snippet.get("customUrl")
    if isinstance(handle, str) and handle.strip():
        normalized_handle = handle.strip()
        if not normalized_handle.startswith("@"):
            normalized_handle = "@" + normalized_handle
    else:
        normalized_handle = None
    return {
        "youtube_channel_id": channel_id.strip(),
        "display_name": display_name.strip(),
        "youtube_handle": normalized_handle,
    }


def exchange_authorization_code(
    root: Path | str,
    authorization_code: str,
    redirect_uri: str,
    transport: Transport,
) -> dict[str, Any]:
    config = load_oauth_client_config(root)
    payload = urllib.parse.urlencode(
        {
            "code": authorization_code,
            "client_id": config.client_id,
            "client_secret": config.client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }
    ).encode("utf-8")
    response = _call_transport(
        transport,
        method="POST",
        url=config.token_uri,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data=payload,
    )
    if "error" in response:
        raise OAuthExchangeError("Authorization code exchange failed.")
    token = dict(response)
    token["expires_at"] = _expires_at_from_now(token.get("expires_in"))
    return _validate_token_payload(token, require_refresh_token=False)


def fetch_authenticated_channel_identity(access_token: str, transport: Transport) -> dict[str, Any]:
    params = urllib.parse.urlencode({"part": "id,snippet,contentDetails", "mine": "true"})
    response = _call_transport(
        transport,
        method="GET",
        url=f"https://www.googleapis.com/youtube/v3/channels?{params}",
        headers={"Authorization": f"Bearer {access_token}"},
        data=None,
    )
    items = response.get("items")
    if not isinstance(items, list) or not items:
        raise AuthenticatedChannelMissingError("No authenticated YouTube channel was returned.")
    if len(items) != 1:
        raise AuthenticatedChannelMissingError("Authenticated YouTube identity is ambiguous.")
    return _sanitize_identity_item(items[0])


def _write_token_atomic(path: Path, token: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(token, indent=2, ensure_ascii=False) + "\n"
    fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def load_channel_token(root: Path | str, channel_slug: str) -> dict[str, Any]:
    paths = channel_workspace.canonical_channel_paths(root, channel_slug)
    if not paths.oauth_token_file.exists():
        raise TokenMissingError("Selected channel token file does not exist.")
    try:
        token = json.loads(paths.oauth_token_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise MalformedTokenError("Selected channel token file is malformed JSON.") from exc
    return _validate_token_payload(token, require_refresh_token=False)


def save_channel_token(root: Path | str, channel_slug: str, token: dict[str, Any]) -> Path:
    paths = channel_workspace.canonical_channel_paths(root, channel_slug)
    validated = _validate_token_payload(dict(token), require_refresh_token=False)
    _write_token_atomic(paths.oauth_token_file, validated)
    return paths.oauth_token_file


def _restore_token_bytes(path: Path, previous_bytes: bytes | None) -> None:
    if previous_bytes is None:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(previous_bytes)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def token_needs_refresh(token: dict[str, Any], *, safety_margin_seconds: int = 300) -> bool:
    expires_at = token.get("expires_at")
    if not isinstance(expires_at, str):
        raise MalformedTokenError("Token payload is missing expires_at.")
    parsed = datetime.fromisoformat(expires_at)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise MalformedTokenError("Token expires_at must be timezone-aware.")
    return parsed <= utc_now() + timedelta(seconds=safety_margin_seconds)


def refresh_channel_token(
    root: Path | str,
    channel_slug: str,
    transport: Transport,
    *,
    safety_margin_seconds: int = 300,
    force: bool = False,
) -> dict[str, Any]:
    channel_workspace.load_channel(root, channel_slug)
    existing = load_channel_token(root, channel_slug)
    if not force and not token_needs_refresh(existing, safety_margin_seconds=safety_margin_seconds):
        return existing
    refresh_token = existing.get("refresh_token")
    if not isinstance(refresh_token, str) or not refresh_token.strip():
        raise ReconnectRequiredError("Selected channel token cannot be refreshed without a refresh token.")
    config = load_oauth_client_config(root)
    payload = urllib.parse.urlencode(
        {
            "client_id": config.client_id,
            "client_secret": config.client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }
    ).encode("utf-8")
    response = _call_transport(
        transport,
        method="POST",
        url=config.token_uri,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data=payload,
    )
    if "error" in response:
        raise OAuthExchangeError("Token refresh failed.")
    merged = dict(existing)
    merged.update(response)
    if not response.get("refresh_token"):
        merged["refresh_token"] = refresh_token
    merged["expires_at"] = _expires_at_from_now(merged.get("expires_in"))
    validated = _validate_token_payload(merged, require_refresh_token=False)
    save_channel_token(root, channel_slug, validated)
    return validated


def get_access_token_for_channel(
    root: Path | str,
    channel_slug: str,
    transport: Transport,
    *,
    safety_margin_seconds: int = 300,
) -> str:
    token = refresh_channel_token(
        root,
        channel_slug,
        transport,
        safety_margin_seconds=safety_margin_seconds,
        force=False,
    )
    return token["access_token"]


def connect_channel_from_authorization_code(
    root: Path | str,
    channel_slug: str,
    authorization_code: str,
    redirect_uri: str,
    transport: Transport,
    *,
    create_if_missing: bool,
) -> dict[str, Any]:
    slug = channel_workspace.validate_channel_slug(channel_slug)
    token = exchange_authorization_code(root, authorization_code, redirect_uri, transport)
    identity = fetch_authenticated_channel_identity(token["access_token"], transport)

    try:
        existing = channel_workspace.load_channel(root, slug)
    except channel_workspace.ChannelWorkspaceError as exc:
        if "does not exist" not in str(exc):
            raise
        existing = None

    if existing is None:
        if not create_if_missing:
            raise ChannelWorkspaceMissingError(
                "Channel workspace does not exist and create_if_missing is false."
            )
        try:
            channel_workspace.create_channel_workspace(
                root=root,
                slug=slug,
                display_name=identity["display_name"],
                youtube_channel_id=identity["youtube_channel_id"],
                youtube_handle=identity["youtube_handle"] or "",
            )
        except channel_workspace.ChannelWorkspaceError as exc:
            if "youtube_channel_id already exists" in str(exc):
                raise ChannelAlreadyExistsError("Authenticated YouTube channel already exists under another slug.") from exc
            raise
    else:
        if existing["youtube_channel_id"] != identity["youtube_channel_id"]:
            raise ChannelIdentityMismatchError("Authenticated YouTube channel does not match the selected workspace.")

    token_path = channel_workspace.canonical_channel_paths(root, slug).oauth_token_file
    previous_token_bytes = token_path.read_bytes() if token_path.exists() else None
    save_channel_token(root, slug, token)
    try:
        updated = channel_workspace.update_channel_connection_metadata(
            root=root,
            slug=slug,
            youtube_channel_id=identity["youtube_channel_id"],
            display_name=identity["display_name"],
            youtube_handle=identity["youtube_handle"],
            status="CONNECTED",
            last_connected_at=utc_now().replace(microsecond=0).isoformat(),
        )
    except Exception:
        _restore_token_bytes(token_path, previous_token_bytes)
        raise
    return {
        "channel_slug": updated["channel_slug"],
        "youtube_channel_id": updated["youtube_channel_id"],
        "display_name": updated["display_name"],
        "youtube_handle": updated["youtube_handle"] or None,
        "status": updated["status"],
        "connected_at": updated["last_connected_at"],
        "token_path": str(token_path),
    }
