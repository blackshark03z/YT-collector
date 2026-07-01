from __future__ import annotations

import hmac
import html
import secrets
import threading
import urllib.parse
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable

from scripts import channel_oauth, channel_workspace


ConnectFunction = Callable[..., dict]


class OAuthBrowserFlowError(Exception):
    pass


class OAuthFlowInvalidError(OAuthBrowserFlowError):
    pass


class OAuthStateMismatchError(OAuthBrowserFlowError):
    pass


class OAuthCallbackTimeoutError(OAuthBrowserFlowError):
    pass


class OAuthConnectionFailedError(OAuthBrowserFlowError):
    pass


@dataclass(frozen=True)
class OAuthBrowserFlow:
    channel_slug: str
    mode: str
    state: str
    redirect_uri: str
    authorization_url: str
    callback_port: int


def _success_html(display_name: str) -> bytes:
    return (
        "<html><body><h1>Connection succeeded</h1>"
        f"<p>{html.escape(display_name)}</p>"
        "<p>Return to the local tool.</p>"
        "<script>window.close && window.close();</script>"
        "</body></html>"
    ).encode("utf-8")


def _failure_html(message: str) -> bytes:
    return (
        "<html><body><h1>Connection failed</h1>"
        f"<p>{html.escape(message)}</p>"
        "</body></html>"
    ).encode("utf-8")


def build_authorization_url(client_config: channel_oauth.OAuthClientConfig, state: str, redirect_uri: str) -> str:
    params = {
        "client_id": client_config.client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "https://www.googleapis.com/auth/youtube.readonly https://www.googleapis.com/auth/yt-analytics.readonly",
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return client_config.auth_uri + "?" + urllib.parse.urlencode(params)


class LoopbackOAuthCallbackServer:
    def __init__(self, on_callback: Callable[[dict[str, str], str], tuple[int, bytes]], timeout_seconds: int = 120):
        self.on_callback = on_callback
        self.timeout_seconds = timeout_seconds
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), self._build_handler())
        self.thread: threading.Thread | None = None
        self.timer: threading.Timer | None = None
        self._stop_lock = threading.Lock()
        self._stopped = False

    @property
    def port(self) -> int:
        return self.httpd.server_address[1]

    def _build_handler(self):
        server = self

        class CallbackHandler(BaseHTTPRequestHandler):
            def log_message(self, fmt: str, *args) -> None:
                pass

            def do_GET(self) -> None:
                parsed = urllib.parse.urlparse(self.path)
                params = {key: values[0] for key, values in urllib.parse.parse_qs(parsed.query).items() if values}
                status, body = server.on_callback(params, f"http://127.0.0.1:{server.port}/callback")
                self.send_response(status)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                server.stop()

        return CallbackHandler

    def start(self) -> None:
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.timer = threading.Timer(self.timeout_seconds, self.stop)
        self.timer.daemon = True
        self.timer.start()

    def stop(self) -> None:
        with self._stop_lock:
            if self._stopped:
                return
            self._stopped = True
            timer = self.timer
            thread = self.thread
        if timer:
            timer.cancel()
        try:
            self.httpd.shutdown()
        except Exception:
            pass
        try:
            self.httpd.server_close()
        except Exception:
            pass
        if thread and thread.is_alive() and threading.current_thread() is not thread:
            thread.join(timeout=1)


def start_oauth_browser_flow(
    root: Path | str,
    channel_slug: str,
    mode: str,
    *,
    transport=None,
    connect_function: ConnectFunction | None = None,
    authorization_url_builder: Callable[[channel_oauth.OAuthClientConfig, str, str], str] | None = None,
    callback_server_factory: Callable[[Callable[[dict[str, str], str], tuple[int, bytes]], int], object] | None = None,
    timeout_seconds: int = 120,
) -> OAuthBrowserFlow:
    slug = channel_workspace.validate_channel_slug(channel_slug)
    if mode not in {"create", "reconnect"}:
        raise OAuthFlowInvalidError("OAuth mode must be create or reconnect.")

    exists = channel_workspace.channel_exists(root, slug)
    if mode == "create" and exists:
        raise OAuthFlowInvalidError("Channel workspace already exists.")
    if mode == "reconnect" and not exists:
        raise OAuthFlowInvalidError("Channel workspace does not exist for reconnect.")

    client_config = channel_oauth.load_oauth_client_config(root)
    state = secrets.token_urlsafe(32)
    connector = connect_function or channel_oauth.connect_channel_from_authorization_code

    def on_callback(params: dict[str, str], redirect_uri: str) -> tuple[int, bytes]:
        if params.get("error"):
            return 400, _failure_html("OAuth provider returned an error.")
        callback_state = params.get("state")
        if not callback_state:
            return 400, _failure_html("Missing OAuth state.")
        if not hmac.compare_digest(callback_state, state):
            return 400, _failure_html("OAuth state mismatch.")
        code = params.get("code")
        if not code:
            return 400, _failure_html("OAuth callback did not include a code.")
        try:
            result = connector(
                root,
                slug,
                code,
                redirect_uri,
                transport,
                create_if_missing=(mode == "create"),
            )
        except TypeError:
            try:
                result = connector(
                    root=root,
                    channel_slug=slug,
                    authorization_code=code,
                    redirect_uri=redirect_uri,
                    transport=transport,
                    create_if_missing=(mode == "create"),
                )
            except Exception:
                return 500, _failure_html("OAuth connection failed.")
        except Exception:
            return 500, _failure_html("OAuth connection failed.")
        return 200, _success_html(result.get("display_name", slug))

    factory = callback_server_factory or (lambda callback, timeout: LoopbackOAuthCallbackServer(callback, timeout))
    server = factory(on_callback, timeout_seconds)
    server.start()
    redirect_uri = f"http://127.0.0.1:{server.port}/callback"
    auth_builder = authorization_url_builder or build_authorization_url
    authorization_url = auth_builder(client_config, state, redirect_uri)
    return OAuthBrowserFlow(
        channel_slug=slug,
        mode=mode,
        state=state,
        redirect_uri=redirect_uri,
        authorization_url=authorization_url,
        callback_port=server.port,
    )
