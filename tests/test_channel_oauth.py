import importlib
import json
import sys
import tempfile
import unittest
import urllib.parse
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import channel_oauth, channel_workspace


def make_client_config(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "installed": {
                    "client_id": "client-123",
                    "client_secret": "super-secret-value",
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": ["http://127.0.0.1:8765/callback"],
                }
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


class FakeTransport:
    def __init__(self, handlers):
        self.handlers = handlers
        self.calls = []

    def __call__(self, *, method, url, headers, data):
        self.calls.append({"method": method, "url": url, "headers": headers, "data": data})
        for predicate, response in self.handlers:
            if predicate(method, url, headers, data):
                if isinstance(response, Exception):
                    raise response
                return response
        raise AssertionError(f"Unexpected transport call: {method} {url}")


def token_response(access_token="access-1", refresh_token="refresh-1", expires_in=3600):
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_in": expires_in,
        "scope": "scope-a",
        "token_type": "Bearer",
        "refresh_token_expires_in": 99999,
    }


def identity_response(channel_id="UC123", title="Mist of Ages", handle="@MistOfAges"):
    snippet = {"title": title}
    if handle is not None:
        snippet["customUrl"] = handle
    return {"items": [{"id": channel_id, "snippet": snippet, "contentDetails": {}}]}


class ChannelOAuthTests(unittest.TestCase):
    def test_module_import_creates_no_files_or_folders(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            before = sorted(str(path.relative_to(root)) for path in root.rglob("*"))
            importlib.reload(channel_oauth)
            after = sorted(str(path.relative_to(root)) for path in root.rglob("*"))
            self.assertEqual(before, after)

    def test_valid_desktop_oauth_client_config_loads(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_client_config(root / "youtube_oauth_client.json")
            config = channel_oauth.load_oauth_client_config(root)
            self.assertEqual(config.client_id, "client-123")
            self.assertEqual(config.token_uri, "https://oauth2.googleapis.com/token")

    def test_missing_client_config_fails_safely(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(channel_oauth.OAuthConfigurationError) as ctx:
                channel_oauth.load_oauth_client_config(tmp)
            self.assertNotIn("super-secret-value", str(ctx.exception))

    def test_top_level_web_config_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "youtube_oauth_client.json").write_text(
                json.dumps({"web": {"client_id": "a", "client_secret": "super-secret-value"}}),
                encoding="utf-8",
            )
            with self.assertRaises(channel_oauth.OAuthConfigurationError) as ctx:
                channel_oauth.load_oauth_client_config(root)
            self.assertNotIn("super-secret-value", str(ctx.exception))

    def test_client_secret_never_appears_in_error_messages(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "youtube_oauth_client.json").write_text(
                json.dumps({"installed": {"client_id": "a", "client_secret": "super-secret-value"}}),
                encoding="utf-8",
            )
            with self.assertRaises(channel_oauth.OAuthConfigurationError) as ctx:
                channel_oauth.load_oauth_client_config(root)
            self.assertNotIn("super-secret-value", str(ctx.exception))

    def test_authorization_code_exchange_uses_expected_client_and_redirect_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_client_config(root / "youtube_oauth_client.json")

            def match_token(method, url, headers, data):
                body = urllib.parse.parse_qs(data.decode("utf-8"))
                return (
                    method == "POST"
                    and url == "https://oauth2.googleapis.com/token"
                    and body["client_id"] == ["client-123"]
                    and body["client_secret"] == ["super-secret-value"]
                    and body["redirect_uri"] == ["http://127.0.0.1:8765/callback"]
                    and body["code"] == ["auth-code"]
                )

            transport = FakeTransport([(match_token, token_response())])
            token = channel_oauth.exchange_authorization_code(
                root, "auth-code", "http://127.0.0.1:8765/callback", transport
            )
            self.assertEqual(token["access_token"], "access-1")
            self.assertIn("expires_at", token)

    def test_new_channel_connection_creates_correct_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_client_config(root / "youtube_oauth_client.json")
            transport = FakeTransport(
                [
                    (lambda m, u, h, d: m == "POST", token_response()),
                    (lambda m, u, h, d: m == "GET", identity_response()),
                ]
            )
            result = channel_oauth.connect_channel_from_authorization_code(
                root,
                "mist_of_ages",
                "auth-code",
                "http://127.0.0.1:8765/callback",
                transport,
                create_if_missing=True,
            )
            self.assertEqual(result["channel_slug"], "mist_of_ages")
            self.assertTrue((root / "channels" / "mist_of_ages" / "channel.json").exists())

    def test_new_channel_connection_writes_token_to_correct_channel_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_client_config(root / "youtube_oauth_client.json")
            transport = FakeTransport(
                [
                    (lambda m, u, h, d: m == "POST", token_response()),
                    (lambda m, u, h, d: m == "GET", identity_response()),
                ]
            )
            result = channel_oauth.connect_channel_from_authorization_code(
                root,
                "mist_of_ages",
                "auth-code",
                "http://127.0.0.1:8765/callback",
                transport,
                create_if_missing=True,
            )
            expected = root / "secrets" / "youtube" / "mist_of_ages_oauth_token.json"
            self.assertEqual(Path(result["token_path"]), expected)
            self.assertTrue(expected.exists())

    def test_sanitized_result_contains_no_token_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_client_config(root / "youtube_oauth_client.json")
            transport = FakeTransport(
                [
                    (lambda m, u, h, d: m == "POST", token_response(access_token="token-a", refresh_token="refresh-a")),
                    (lambda m, u, h, d: m == "GET", identity_response()),
                ]
            )
            result = channel_oauth.connect_channel_from_authorization_code(
                root, "mist_of_ages", "auth-code", "http://127.0.0.1:8765/callback", transport, create_if_missing=True
            )
            dumped = json.dumps(result)
            self.assertNotIn("token-a", dumped)
            self.assertNotIn("refresh-a", dumped)

    def test_existing_matching_workspace_reconnect_succeeds(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_client_config(root / "youtube_oauth_client.json")
            channel_workspace.create_channel_workspace(root, "mist_of_ages", "Old Name", "UC123", "@Old")
            transport = FakeTransport(
                [
                    (lambda m, u, h, d: m == "POST", token_response()),
                    (lambda m, u, h, d: m == "GET", identity_response(channel_id="UC123", title="New Name", handle="@New")),
                ]
            )
            result = channel_oauth.connect_channel_from_authorization_code(
                root, "mist_of_ages", "auth-code", "http://127.0.0.1:8765/callback", transport, create_if_missing=False
            )
            loaded = channel_workspace.load_channel(root, "mist_of_ages")
            self.assertEqual(result["status"], "CONNECTED")
            self.assertEqual(loaded["display_name"], "New Name")
            self.assertEqual(loaded["youtube_channel_id"], "UC123")

    def test_missing_workspace_with_create_if_missing_false_fails_clearly(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_client_config(root / "youtube_oauth_client.json")
            transport = FakeTransport(
                [
                    (lambda m, u, h, d: m == "POST", token_response()),
                    (lambda m, u, h, d: m == "GET", identity_response()),
                ]
            )
            with self.assertRaises(channel_oauth.ChannelWorkspaceMissingError):
                channel_oauth.connect_channel_from_authorization_code(
                    root, "mist_of_ages", "auth-code", "http://127.0.0.1:8765/callback", transport, create_if_missing=False
                )

    def test_existing_mismatched_channel_id_reconnect_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_client_config(root / "youtube_oauth_client.json")
            channel_workspace.create_channel_workspace(root, "mist_of_ages", "Mist", "UC123", "@Mist")
            transport = FakeTransport(
                [
                    (lambda m, u, h, d: m == "POST", token_response()),
                    (lambda m, u, h, d: m == "GET", identity_response(channel_id="UC999")),
                ]
            )
            with self.assertRaises(channel_oauth.ChannelIdentityMismatchError):
                channel_oauth.connect_channel_from_authorization_code(
                    root, "mist_of_ages", "auth-code", "http://127.0.0.1:8765/callback", transport, create_if_missing=False
                )

    def test_identity_mismatch_preserves_existing_token_byte_for_byte(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_client_config(root / "youtube_oauth_client.json")
            channel_workspace.create_channel_workspace(root, "mist_of_ages", "Mist", "UC123", "@Mist")
            token_path = channel_workspace.canonical_channel_paths(root, "mist_of_ages").oauth_token_file
            token_path.parent.mkdir(parents=True, exist_ok=True)
            token_path.write_bytes(b'{"access_token":"old","refresh_token":"old-refresh","expires_in":3600,"expires_at":"2026-07-01T00:00:00+00:00","token_type":"Bearer"}\n')
            original = token_path.read_bytes()
            transport = FakeTransport(
                [
                    (lambda m, u, h, d: m == "POST", token_response()),
                    (lambda m, u, h, d: m == "GET", identity_response(channel_id="UC999")),
                ]
            )
            with self.assertRaises(channel_oauth.ChannelIdentityMismatchError):
                channel_oauth.connect_channel_from_authorization_code(
                    root, "mist_of_ages", "auth-code", "http://127.0.0.1:8765/callback", transport, create_if_missing=False
                )
            self.assertEqual(token_path.read_bytes(), original)

    def test_identity_mismatch_preserves_channel_json_byte_for_byte(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_client_config(root / "youtube_oauth_client.json")
            channel_workspace.create_channel_workspace(root, "mist_of_ages", "Mist", "UC123", "@Mist")
            channel_json = root / "channels" / "mist_of_ages" / "channel.json"
            original = channel_json.read_bytes()
            transport = FakeTransport(
                [
                    (lambda m, u, h, d: m == "POST", token_response()),
                    (lambda m, u, h, d: m == "GET", identity_response(channel_id="UC999")),
                ]
            )
            with self.assertRaises(channel_oauth.ChannelIdentityMismatchError):
                channel_oauth.connect_channel_from_authorization_code(
                    root, "mist_of_ages", "auth-code", "http://127.0.0.1:8765/callback", transport, create_if_missing=False
                )
            self.assertEqual(channel_json.read_bytes(), original)

    def test_metadata_update_failure_restores_previous_token_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_client_config(root / "youtube_oauth_client.json")
            channel_workspace.create_channel_workspace(root, "mist_of_ages", "Mist", "UC123", "@Mist")
            token_path = channel_workspace.canonical_channel_paths(root, "mist_of_ages").oauth_token_file
            token_path.parent.mkdir(parents=True, exist_ok=True)
            token_path.write_bytes(
                (json.dumps(token_response(access_token="old", refresh_token="old-refresh", expires_in=3600) | {"expires_at": "2026-07-01T00:00:00+00:00"}) + "\n").encode("utf-8")
            )
            original = token_path.read_bytes()
            transport = FakeTransport(
                [
                    (lambda m, u, h, d: m == "POST", token_response(access_token="new", refresh_token="new-refresh")),
                    (lambda m, u, h, d: m == "GET", identity_response(channel_id="UC123")),
                ]
            )
            with mock.patch("scripts.channel_workspace.update_channel_connection_metadata", side_effect=channel_workspace.ChannelWorkspaceError("boom")):
                with self.assertRaises(channel_workspace.ChannelWorkspaceError):
                    channel_oauth.connect_channel_from_authorization_code(
                        root, "mist_of_ages", "auth-code", "http://127.0.0.1:8765/callback", transport, create_if_missing=False
                    )
            self.assertEqual(token_path.read_bytes(), original)

    def test_token_preparation_failure_preserves_existing_token_and_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_client_config(root / "youtube_oauth_client.json")
            channel_workspace.create_channel_workspace(root, "mist_of_ages", "Mist", "UC123", "@Mist")
            token_path = channel_workspace.canonical_channel_paths(root, "mist_of_ages").oauth_token_file
            token_path.parent.mkdir(parents=True, exist_ok=True)
            token_path.write_bytes(
                (json.dumps(token_response(access_token="old", refresh_token="old-refresh", expires_in=3600) | {"expires_at": "2026-07-01T00:00:00+00:00"}) + "\n").encode("utf-8")
            )
            original_token = token_path.read_bytes()
            channel_json = (root / "channels" / "mist_of_ages" / "channel.json").read_bytes()
            with mock.patch("scripts.channel_oauth.save_channel_token", side_effect=RuntimeError("write failed")):
                transport = FakeTransport(
                    [
                        (lambda m, u, h, d: m == "POST", token_response(access_token="new", refresh_token="new-refresh")),
                        (lambda m, u, h, d: m == "GET", identity_response(channel_id="UC123")),
                    ]
                )
                with self.assertRaises(RuntimeError):
                    channel_oauth.connect_channel_from_authorization_code(
                        root, "mist_of_ages", "auth-code", "http://127.0.0.1:8765/callback", transport, create_if_missing=False
                    )
            self.assertEqual(token_path.read_bytes(), original_token)
            self.assertEqual((root / "channels" / "mist_of_ages" / "channel.json").read_bytes(), channel_json)

    def test_duplicate_youtube_identity_under_another_slug_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_client_config(root / "youtube_oauth_client.json")
            channel_workspace.create_channel_workspace(root, "mist_of_ages", "Mist", "UC123", "@Mist")
            transport = FakeTransport(
                [
                    (lambda m, u, h, d: m == "POST", token_response()),
                    (lambda m, u, h, d: m == "GET", identity_response(channel_id="UC123")),
                ]
            )
            with self.assertRaises(channel_oauth.ChannelAlreadyExistsError):
                channel_oauth.connect_channel_from_authorization_code(
                    root, "second_channel", "auth-code", "http://127.0.0.1:8765/callback", transport, create_if_missing=True
                )

    def test_new_workspace_connection_success_commits_all_required_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_client_config(root / "youtube_oauth_client.json")
            transport = FakeTransport(
                [
                    (lambda m, u, h, d: m == "POST", token_response()),
                    (lambda m, u, h, d: m == "GET", identity_response(channel_id="UC123")),
                ]
            )
            result = channel_oauth.connect_channel_from_authorization_code(
                root, "mist_of_ages", "auth-code", "http://127.0.0.1:8765/callback", transport, create_if_missing=True
            )
            self.assertTrue((root / "channels" / "mist_of_ages" / "channel.json").exists())
            self.assertTrue((root / "secrets" / "youtube" / "mist_of_ages_oauth_token.json").exists())
            self.assertEqual(result["status"], "CONNECTED")

    def test_new_workspace_failure_leaves_no_token(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_client_config(root / "youtube_oauth_client.json")
            transport = FakeTransport(
                [
                    (lambda m, u, h, d: m == "POST", token_response()),
                    (lambda m, u, h, d: m == "GET", identity_response(channel_id="UC123")),
                ]
            )
            with mock.patch("scripts.channel_workspace.update_channel_connection_metadata", side_effect=channel_workspace.ChannelWorkspaceError("boom")):
                with self.assertRaises(channel_workspace.ChannelWorkspaceError):
                    channel_oauth.connect_channel_from_authorization_code(
                        root, "mist_of_ages", "auth-code", "http://127.0.0.1:8765/callback", transport, create_if_missing=True
                    )
            self.assertFalse((root / "secrets" / "youtube" / "mist_of_ages_oauth_token.json").exists())

    def test_new_workspace_failure_removes_newly_created_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_client_config(root / "youtube_oauth_client.json")
            transport = FakeTransport(
                [
                    (lambda m, u, h, d: m == "POST", token_response()),
                    (lambda m, u, h, d: m == "GET", identity_response(channel_id="UC123")),
                ]
            )
            with mock.patch("scripts.channel_workspace.update_channel_connection_metadata", side_effect=channel_workspace.ChannelWorkspaceError("boom")):
                with self.assertRaises(channel_workspace.ChannelWorkspaceError):
                    channel_oauth.connect_channel_from_authorization_code(
                        root, "mist_of_ages", "auth-code", "http://127.0.0.1:8765/callback", transport, create_if_missing=True
                    )
            self.assertFalse((root / "channels" / "mist_of_ages").exists())

    def test_failure_does_not_remove_pre_existing_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_client_config(root / "youtube_oauth_client.json")
            channel_workspace.create_channel_workspace(root, "mist_of_ages", "Mist", "UC123", "@Mist")
            transport = FakeTransport(
                [
                    (lambda m, u, h, d: m == "POST", token_response()),
                    (lambda m, u, h, d: m == "GET", identity_response(channel_id="UC123")),
                ]
            )
            with mock.patch("scripts.channel_workspace.update_channel_connection_metadata", side_effect=channel_workspace.ChannelWorkspaceError("boom")):
                with self.assertRaises(channel_workspace.ChannelWorkspaceError):
                    channel_oauth.connect_channel_from_authorization_code(
                        root, "mist_of_ages", "auth-code", "http://127.0.0.1:8765/callback", transport, create_if_missing=False
                    )
            self.assertTrue((root / "channels" / "mist_of_ages").exists())

    def test_channel_a_failure_does_not_modify_channel_b(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_client_config(root / "youtube_oauth_client.json")
            channel_workspace.create_channel_workspace(root, "channel_a", "A", "UC123", "@A")
            channel_workspace.create_channel_workspace(root, "channel_b", "B", "UC456", "@B")
            b_json = (root / "channels" / "channel_b" / "channel.json").read_bytes()
            transport = FakeTransport(
                [
                    (lambda m, u, h, d: m == "POST", token_response()),
                    (lambda m, u, h, d: m == "GET", identity_response(channel_id="UC123")),
                ]
            )
            with mock.patch("scripts.channel_workspace.update_channel_connection_metadata", side_effect=channel_workspace.ChannelWorkspaceError("boom")):
                with self.assertRaises(channel_workspace.ChannelWorkspaceError):
                    channel_oauth.connect_channel_from_authorization_code(
                        root, "channel_a", "auth-code", "http://127.0.0.1:8765/callback", transport, create_if_missing=False
                    )
            self.assertEqual((root / "channels" / "channel_b" / "channel.json").read_bytes(), b_json)

    def test_zero_channel_api_response_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_client_config(root / "youtube_oauth_client.json")
            transport = FakeTransport([(lambda m, u, h, d: m == "GET", {"items": []})])
            with self.assertRaises(channel_oauth.AuthenticatedChannelMissingError):
                channel_oauth.fetch_authenticated_channel_identity("token", transport)

    def test_ambiguous_multiple_identity_response_fails(self):
        transport = FakeTransport([(lambda m, u, h, d: True, {"items": [{"id": "UC1", "snippet": {"title": "A"}}, {"id": "UC2", "snippet": {"title": "B"}}]})])
        with self.assertRaises(channel_oauth.AuthenticatedChannelMissingError):
            channel_oauth.fetch_authenticated_channel_identity("token", transport)

    def test_missing_channel_id_fails(self):
        transport = FakeTransport([(lambda m, u, h, d: True, {"items": [{"snippet": {"title": "A"}}]})])
        with self.assertRaises(channel_oauth.AuthenticatedChannelMissingError):
            channel_oauth.fetch_authenticated_channel_identity("token", transport)

    def test_token_files_for_channel_a_and_b_remain_separate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_client_config(root / "youtube_oauth_client.json")
            for slug, channel_id in [("mist_of_ages", "UC123"), ("tam_builds", "UC456")]:
                transport = FakeTransport(
                    [
                        (lambda m, u, h, d, cid=channel_id: m == "POST", token_response(access_token=f"token-{channel_id}", refresh_token=f"refresh-{channel_id}")),
                        (lambda m, u, h, d: m == "GET", identity_response(channel_id=channel_id, title=slug, handle="@" + slug)),
                    ]
                )
                channel_oauth.connect_channel_from_authorization_code(
                    root, slug, "auth-code", "http://127.0.0.1:8765/callback", transport, create_if_missing=True
                )
            a = channel_workspace.canonical_channel_paths(root, "mist_of_ages").oauth_token_file.read_text(encoding="utf-8")
            b = channel_workspace.canonical_channel_paths(root, "tam_builds").oauth_token_file.read_text(encoding="utf-8")
            self.assertNotEqual(a, b)

    def test_refresh_channel_a_does_not_modify_channel_b(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_client_config(root / "youtube_oauth_client.json")
            channel_workspace.create_channel_workspace(root, "mist_of_ages", "Mist", "UC123", "@Mist")
            channel_workspace.create_channel_workspace(root, "tam_builds", "Tam", "UC456", "@Tam")
            a_path = channel_workspace.canonical_channel_paths(root, "mist_of_ages").oauth_token_file
            b_path = channel_workspace.canonical_channel_paths(root, "tam_builds").oauth_token_file
            a_path.parent.mkdir(parents=True, exist_ok=True)
            b_path.parent.mkdir(parents=True, exist_ok=True)
            a_path.write_text(json.dumps(token_response(access_token="old-a", refresh_token="refresh-a", expires_in=1) | {"expires_at": "2000-01-01T00:00:00+00:00"}) + "\n", encoding="utf-8")
            b_path.write_text(json.dumps(token_response(access_token="old-b", refresh_token="refresh-b", expires_in=1) | {"expires_at": "2000-01-01T00:00:00+00:00"}) + "\n", encoding="utf-8")
            before_b = b_path.read_bytes()
            transport = FakeTransport([(lambda m, u, h, d: True, token_response(access_token="new-a", refresh_token="refresh-a", expires_in=3600))])
            channel_oauth.refresh_channel_token(root, "mist_of_ages", transport, force=True)
            self.assertEqual(b_path.read_bytes(), before_b)

    def test_refresh_response_without_refresh_token_preserves_previous_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_client_config(root / "youtube_oauth_client.json")
            channel_workspace.create_channel_workspace(root, "mist_of_ages", "Mist", "UC123", "@Mist")
            token_path = channel_workspace.canonical_channel_paths(root, "mist_of_ages").oauth_token_file
            token_path.parent.mkdir(parents=True, exist_ok=True)
            token_path.write_text(
                json.dumps(token_response(access_token="old", refresh_token="keep-me", expires_in=1) | {"expires_at": "2000-01-01T00:00:00+00:00"}) + "\n",
                encoding="utf-8",
            )
            transport = FakeTransport([(lambda m, u, h, d: True, {"access_token": "new", "expires_in": 3600, "scope": "scope-a", "token_type": "Bearer"})])
            refreshed = channel_oauth.refresh_channel_token(root, "mist_of_ages", transport, force=True)
            self.assertEqual(refreshed["refresh_token"], "keep-me")

    def test_refresh_failure_preserves_previous_token_byte_for_byte(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_client_config(root / "youtube_oauth_client.json")
            channel_workspace.create_channel_workspace(root, "mist_of_ages", "Mist", "UC123", "@Mist")
            token_path = channel_workspace.canonical_channel_paths(root, "mist_of_ages").oauth_token_file
            token_path.parent.mkdir(parents=True, exist_ok=True)
            token_path.write_bytes(
                (json.dumps(token_response(access_token="old", refresh_token="keep-me", expires_in=1) | {"expires_at": "2000-01-01T00:00:00+00:00"}) + "\n").encode("utf-8")
            )
            original = token_path.read_bytes()
            transport = FakeTransport([(lambda m, u, h, d: True, {"error": "invalid_grant"})])
            with self.assertRaises(channel_oauth.OAuthExchangeError):
                channel_oauth.refresh_channel_token(root, "mist_of_ages", transport, force=True)
            self.assertEqual(token_path.read_bytes(), original)

    def test_missing_refresh_token_returns_reconnect_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_client_config(root / "youtube_oauth_client.json")
            channel_workspace.create_channel_workspace(root, "mist_of_ages", "Mist", "UC123", "@Mist")
            token_path = channel_workspace.canonical_channel_paths(root, "mist_of_ages").oauth_token_file
            token_path.parent.mkdir(parents=True, exist_ok=True)
            token_path.write_text(
                json.dumps(
                    {
                        "access_token": "old",
                        "expires_in": 1,
                        "expires_at": "2000-01-01T00:00:00+00:00",
                        "scope": "scope-a",
                        "token_type": "Bearer",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            with self.assertRaises(channel_oauth.ReconnectRequiredError):
                channel_oauth.refresh_channel_token(root, "mist_of_ages", FakeTransport([]), force=True)

    def test_expiry_timestamps_are_timezone_aware(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_client_config(root / "youtube_oauth_client.json")
            transport = FakeTransport([(lambda m, u, h, d: True, token_response())])
            token = channel_oauth.exchange_authorization_code(root, "auth-code", "http://127.0.0.1:8765/callback", transport)
            self.assertIn("+00:00", token["expires_at"])

    def test_token_json_is_newline_terminated(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_client_config(root / "youtube_oauth_client.json")
            transport = FakeTransport(
                [
                    (lambda m, u, h, d: m == "POST", token_response()),
                    (lambda m, u, h, d: m == "GET", identity_response()),
                ]
            )
            channel_oauth.connect_channel_from_authorization_code(
                root, "mist_of_ages", "auth-code", "http://127.0.0.1:8765/callback", transport, create_if_missing=True
            )
            content = channel_workspace.canonical_channel_paths(root, "mist_of_ages").oauth_token_file.read_text(encoding="utf-8")
            self.assertTrue(content.endswith("\n"))

    def test_token_writes_are_atomic(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_client_config(root / "youtube_oauth_client.json")
            transport = FakeTransport(
                [
                    (lambda m, u, h, d: m == "POST", token_response()),
                    (lambda m, u, h, d: m == "GET", identity_response()),
                ]
            )
            channel_oauth.connect_channel_from_authorization_code(
                root, "mist_of_ages", "auth-code", "http://127.0.0.1:8765/callback", transport, create_if_missing=True
            )
            secret_dir = root / "secrets" / "youtube"
            leftovers = [path for path in secret_dir.iterdir() if path.suffix == ".tmp"]
            self.assertEqual(leftovers, [])

    def test_channel_metadata_updates_preserve_immutable_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            channel_workspace.create_channel_workspace(root, "mist_of_ages", "Old", "UC123", "@Old")
            updated = channel_workspace.update_channel_connection_metadata(
                root,
                "mist_of_ages",
                youtube_channel_id="UC123",
                display_name="New",
                youtube_handle="@New",
            )
            self.assertEqual(updated["channel_slug"], "mist_of_ages")
            self.assertEqual(updated["youtube_channel_id"], "UC123")
            self.assertEqual(updated["display_name"], "New")
            self.assertEqual(updated["status"], "CONNECTED")

    def test_channel_metadata_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            channel_workspace.create_channel_workspace(root, "mist_of_ages", "Old", "UC123", "@Old")
            with self.assertRaises(channel_workspace.ChannelWorkspaceError):
                channel_workspace.update_channel_connection_metadata(
                    root,
                    "mist_of_ages",
                    youtube_channel_id="UC999",
                    display_name="New",
                    youtube_handle="@New",
                )

    def test_no_token_or_client_secret_fields_appear_in_channel_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_client_config(root / "youtube_oauth_client.json")
            transport = FakeTransport(
                [
                    (lambda m, u, h, d: m == "POST", token_response(access_token="a-token", refresh_token="a-refresh")),
                    (lambda m, u, h, d: m == "GET", identity_response()),
                ]
            )
            channel_oauth.connect_channel_from_authorization_code(
                root, "mist_of_ages", "auth-code", "http://127.0.0.1:8765/callback", transport, create_if_missing=True
            )
            payload = json.loads((root / "channels" / "mist_of_ages" / "channel.json").read_text(encoding="utf-8"))
            dumped = json.dumps(payload)
            self.assertNotIn("access_token", dumped)
            self.assertNotIn("refresh_token", dumped)
            self.assertNotIn("client_secret", dumped)
            self.assertNotIn("a-token", dumped)
            self.assertNotIn("a-refresh", dumped)

    def test_no_real_repository_credential_or_runtime_path_is_touched(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_client_config(root / "youtube_oauth_client.json")
            transport = FakeTransport(
                [
                    (lambda m, u, h, d: m == "POST", token_response()),
                    (lambda m, u, h, d: m == "GET", identity_response()),
                ]
            )
            channel_oauth.connect_channel_from_authorization_code(
                root, "mist_of_ages", "auth-code", "http://127.0.0.1:8765/callback", transport, create_if_missing=True
            )
            self.assertFalse((ROOT / "channels").exists())
            self.assertFalse((ROOT / "secrets").exists())


if __name__ == "__main__":
    unittest.main()
