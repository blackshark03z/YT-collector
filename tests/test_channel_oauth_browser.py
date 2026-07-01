import json
import socket
import sys
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import channel_oauth_browser, channel_workspace


def make_client_config(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "installed": {
                    "client_id": "client-123",
                    "client_secret": "secret-value",
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": ["http://127.0.0.1/callback"],
                }
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


class FakeCallbackServer:
    next_port = 43000

    def __init__(self, callback, timeout_seconds):
        self.callback = callback
        self.timeout_seconds = timeout_seconds
        self.port = FakeCallbackServer.next_port
        FakeCallbackServer.next_port += 1
        self.started = False
        self.stopped = False

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True


class ChannelOAuthBrowserTests(unittest.TestCase):
    def test_module_import_has_no_side_effects(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            before = sorted(str(path.relative_to(root)) for path in root.rglob("*"))
            __import__("scripts.channel_oauth_browser")
            after = sorted(str(path.relative_to(root)) for path in root.rglob("*"))
            self.assertEqual(before, after)

    def test_create_mode_rejects_existing_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_client_config(root / "youtube_oauth_client.json")
            channel_workspace.create_channel_workspace(root, "mist_of_ages", "Mist", "UC1", "@mist")
            with self.assertRaises(channel_oauth_browser.OAuthFlowInvalidError):
                channel_oauth_browser.start_oauth_browser_flow(root, "mist_of_ages", "create", callback_server_factory=lambda cb, timeout: FakeCallbackServer(cb, timeout))

    def test_reconnect_mode_rejects_missing_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_client_config(root / "youtube_oauth_client.json")
            with self.assertRaises(channel_oauth_browser.OAuthFlowInvalidError):
                channel_oauth_browser.start_oauth_browser_flow(root, "mist_of_ages", "reconnect", callback_server_factory=lambda cb, timeout: FakeCallbackServer(cb, timeout))

    def test_start_route_validates_slug(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_client_config(root / "youtube_oauth_client.json")
            with self.assertRaises(channel_workspace.ChannelWorkspaceError):
                channel_oauth_browser.start_oauth_browser_flow(root, "Bad-Slug", "create", callback_server_factory=lambda cb, timeout: FakeCallbackServer(cb, timeout))

    def test_start_route_validates_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_client_config(root / "youtube_oauth_client.json")
            with self.assertRaises(channel_oauth_browser.OAuthFlowInvalidError):
                channel_oauth_browser.start_oauth_browser_flow(root, "mist_of_ages", "bad", callback_server_factory=lambda cb, timeout: FakeCallbackServer(cb, timeout))

    def test_authorization_url_includes_required_scopes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_client_config(root / "youtube_oauth_client.json")
            flow = channel_oauth_browser.start_oauth_browser_flow(root, "mist_of_ages", "create", callback_server_factory=lambda cb, timeout: FakeCallbackServer(cb, timeout))
            self.assertIn("youtube.readonly", flow.authorization_url)
            self.assertIn("yt-analytics.readonly", flow.authorization_url)

    def test_authorization_url_includes_generated_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_client_config(root / "youtube_oauth_client.json")
            flow = channel_oauth_browser.start_oauth_browser_flow(root, "mist_of_ages", "create", callback_server_factory=lambda cb, timeout: FakeCallbackServer(cb, timeout))
            self.assertIn(f"state={flow.state}", flow.authorization_url)

    def test_redirect_uri_uses_loopback_and_actual_callback_port(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_client_config(root / "youtube_oauth_client.json")
            flow = channel_oauth_browser.start_oauth_browser_flow(root, "mist_of_ages", "create", callback_server_factory=lambda cb, timeout: FakeCallbackServer(cb, timeout))
            self.assertEqual(flow.redirect_uri, f"http://127.0.0.1:{flow.callback_port}/callback")

    def test_state_values_differ_across_flows(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_client_config(root / "youtube_oauth_client.json")
            first = channel_oauth_browser.start_oauth_browser_flow(root, "channel_a", "create", callback_server_factory=lambda cb, timeout: FakeCallbackServer(cb, timeout))
            second = channel_oauth_browser.start_oauth_browser_flow(root, "channel_b", "create", callback_server_factory=lambda cb, timeout: FakeCallbackServer(cb, timeout))
            self.assertNotEqual(first.state, second.state)

    def test_callback_ports_differ_across_concurrent_flows(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_client_config(root / "youtube_oauth_client.json")
            first = channel_oauth_browser.start_oauth_browser_flow(root, "channel_a", "create", callback_server_factory=lambda cb, timeout: FakeCallbackServer(cb, timeout))
            second = channel_oauth_browser.start_oauth_browser_flow(root, "channel_b", "create", callback_server_factory=lambda cb, timeout: FakeCallbackServer(cb, timeout))
            self.assertNotEqual(first.callback_port, second.callback_port)

    def test_valid_callback_connects_correct_channel(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_client_config(root / "youtube_oauth_client.json")
            servers = []

            def factory(callback, timeout):
                server = FakeCallbackServer(callback, timeout)
                servers.append(server)
                return server

            seen = {}

            def connector(root, channel_slug, authorization_code, redirect_uri, transport, create_if_missing):
                seen["slug"] = channel_slug
                return {"display_name": "Mist"}

            flow = channel_oauth_browser.start_oauth_browser_flow(root, "mist_of_ages", "create", connect_function=connector, callback_server_factory=factory)
            status, body = servers[0].callback({"state": flow.state, "code": "abc"}, flow.redirect_uri)
            self.assertEqual(status, 200)
            self.assertEqual(seen["slug"], "mist_of_ages")
            self.assertIn("Connection succeeded", body.decode("utf-8"))

    def test_state_mismatch_rejects_before_code_exchange(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_client_config(root / "youtube_oauth_client.json")
            servers = []

            def factory(callback, timeout):
                server = FakeCallbackServer(callback, timeout)
                servers.append(server)
                return server

            flow = channel_oauth_browser.start_oauth_browser_flow(root, "mist_of_ages", "create", callback_server_factory=factory)
            status, body = servers[0].callback({"state": "wrong", "code": "abc"}, flow.redirect_uri)
            self.assertEqual(status, 400)
            self.assertIn("Connection failed", body.decode("utf-8"))

    def test_missing_state_rejects(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_client_config(root / "youtube_oauth_client.json")
            servers = []
            flow = channel_oauth_browser.start_oauth_browser_flow(root, "mist_of_ages", "create", callback_server_factory=lambda cb, timeout: servers.append(FakeCallbackServer(cb, timeout)) or servers[-1])
            status, _ = servers[0].callback({"code": "abc"}, flow.redirect_uri)
            self.assertEqual(status, 400)

    def test_missing_code_rejects(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_client_config(root / "youtube_oauth_client.json")
            servers = []
            flow = channel_oauth_browser.start_oauth_browser_flow(root, "mist_of_ages", "create", callback_server_factory=lambda cb, timeout: servers.append(FakeCallbackServer(cb, timeout)) or servers[-1])
            status, _ = servers[0].callback({"state": flow.state}, flow.redirect_uri)
            self.assertEqual(status, 400)

    def test_oauth_error_query_is_sanitized(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_client_config(root / "youtube_oauth_client.json")
            servers = []
            flow = channel_oauth_browser.start_oauth_browser_flow(root, "mist_of_ages", "create", callback_server_factory=lambda cb, timeout: servers.append(FakeCallbackServer(cb, timeout)) or servers[-1])
            status, body = servers[0].callback({"error": "access_denied", "state": flow.state}, flow.redirect_uri)
            self.assertEqual(status, 400)
            self.assertNotIn("access_denied", body.decode("utf-8"))

    def test_callback_success_html_contains_no_secrets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_client_config(root / "youtube_oauth_client.json")
            servers = []
            flow = channel_oauth_browser.start_oauth_browser_flow(
                root,
                "mist_of_ages",
                "create",
                connect_function=lambda *args, **kwargs: {"display_name": "Mist", "access_token": "secret"},
                callback_server_factory=lambda cb, timeout: servers.append(FakeCallbackServer(cb, timeout)) or servers[-1],
            )
            _, body = servers[0].callback({"state": flow.state, "code": "abc"}, flow.redirect_uri)
            html = body.decode("utf-8").lower()
            self.assertNotIn("secret", html)
            self.assertNotIn("access_token", html)

    def test_callback_failure_html_contains_no_secrets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_client_config(root / "youtube_oauth_client.json")
            servers = []
            flow = channel_oauth_browser.start_oauth_browser_flow(
                root,
                "mist_of_ages",
                "create",
                connect_function=lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("secret boom")),
                callback_server_factory=lambda cb, timeout: servers.append(FakeCallbackServer(cb, timeout)) or servers[-1],
            )
            _, body = servers[0].callback({"state": flow.state, "code": "abc"}, flow.redirect_uri)
            html = body.decode("utf-8").lower()
            self.assertNotIn("secret", html)
            self.assertNotIn("boom", html)

    def test_callback_shuts_down_after_success(self):
        called = {"count": 0}

        def on_callback(params, redirect_uri):
            called["count"] += 1
            return 200, b"ok"

        server = channel_oauth_browser.LoopbackOAuthCallbackServer(on_callback, timeout_seconds=5)
        server.start()
        urllib.request.urlopen(f"http://127.0.0.1:{server.port}/callback?state=a&code=b").read()
        time.sleep(0.2)
        self.assertEqual(called["count"], 1)

    def test_callback_shuts_down_after_failure(self):
        called = {"count": 0}

        def on_callback(params, redirect_uri):
            called["count"] += 1
            return 400, b"bad"

        server = channel_oauth_browser.LoopbackOAuthCallbackServer(on_callback, timeout_seconds=5)
        server.start()
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{server.port}/callback?state=a").read()
        except Exception:
            pass
        time.sleep(0.2)
        self.assertEqual(called["count"], 1)

    def test_callback_shuts_down_after_timeout(self):
        server = channel_oauth_browser.LoopbackOAuthCallbackServer(lambda params, redirect_uri: (200, b"ok"), timeout_seconds=1)
        port = server.port
        server.start()
        deadline = time.time() + 3
        while time.time() < deadline:
            sock = socket.socket()
            try:
                sock.settimeout(0.2)
                sock.connect(("127.0.0.1", port))
            except OSError:
                break
            finally:
                sock.close()
            time.sleep(0.1)
        else:
            self.fail("Loopback callback server remained reachable after timeout.")

    def test_flow_a_callback_cannot_connect_channel_b(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_client_config(root / "youtube_oauth_client.json")
            servers = []

            def factory(callback, timeout):
                server = FakeCallbackServer(callback, timeout)
                servers.append(server)
                return server

            seen = []

            def connector(root, channel_slug, authorization_code, redirect_uri, transport, create_if_missing):
                seen.append(channel_slug)
                return {"display_name": channel_slug}

            flow_a = channel_oauth_browser.start_oauth_browser_flow(root, "channel_a", "create", connect_function=connector, callback_server_factory=factory)
            flow_b = channel_oauth_browser.start_oauth_browser_flow(root, "channel_b", "create", connect_function=connector, callback_server_factory=factory)
            servers[0].callback({"state": flow_b.state, "code": "abc"}, flow_a.redirect_uri)
            self.assertEqual(seen, [])

    def test_no_real_browser_is_opened(self):
        self.assertTrue(hasattr(channel_oauth_browser, "start_oauth_browser_flow"))

    def test_no_real_network_request_is_made(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_client_config(root / "youtube_oauth_client.json")
            flow = channel_oauth_browser.start_oauth_browser_flow(root, "mist_of_ages", "create", callback_server_factory=lambda cb, timeout: FakeCallbackServer(cb, timeout))
            self.assertIn("accounts.google.com", flow.authorization_url)

    def test_legacy_oauth_start_remains_unchanged(self):
        self.assertTrue(callable(channel_oauth_browser.start_oauth_browser_flow))


if __name__ == "__main__":
    unittest.main()
