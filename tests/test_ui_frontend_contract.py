import re
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import ui_server


class UiFrontendContractTests(unittest.TestCase):
    def setUp(self):
        self.html = ui_server.HTML_PAGE

    def test_embedded_ui_uses_v2_channel_reads(self):
        self.assertIn('v2Api("channels")', self.html)
        self.assertIn('v2Api(`channels/${encodeURIComponent(slug)}`', self.html)
        self.assertNotIn("/api/status", self.html)

    def test_active_visible_ui_route_allowlist_is_canonical_v2_only(self):
        routes = set(re.findall(r'v2Api\((?:`|")([^`"]+)', self.html))
        self.assertEqual(
            routes,
            {
                "channels",
                "oauth/start?channel_slug=${encodeURIComponent(slug)}&mode=${encodeURIComponent(mode)}",
                "channels/${encodeURIComponent(slug)}",
                "channels/${encodeURIComponent(slug)}/sync_metrics",
                "channels/${encodeURIComponent(slug)}/projects",
                "channels/${encodeURIComponent(channelSlug)}/projects/${encodeURIComponent(projectSlug)}",
                "channels/${encodeURIComponent(channelSlug)}/projects/${encodeURIComponent(projectSlug)}/transcript",
                "channels/${encodeURIComponent(slug)}/projects/${encodeURIComponent(projectSlug)}/transcript",
                "channels/${encodeURIComponent(slug)}/projects/${encodeURIComponent(projectSlug)}/validate",
            },
        )

    def test_selected_channel_state_contract_is_present(self):
        for token in [
            "SELECTED_CHANNEL_STORAGE_KEY",
            "selectedChannelSlug",
            "selectedChannelSummary",
            "selectedProjectSlug",
            "selectedProjectDetail",
            "selectedProjectTranscript",
            "selectedProjectValidation",
            "state.channels",
            "state.projects",
            "state.isLoadingChannels",
            "state.isLoadingSummary",
            "state.isLoadingProjects",
            "state.isLoadingProjectDetail",
            "oauthAction",
            "metricsAction",
            "actionFeedback",
            "createProjectAction",
            "transcriptSaveAction",
            "validationAction",
            "projectFeedback",
        ]:
            self.assertIn(token, self.html)

    def test_valid_saved_selection_is_restored_and_stale_selection_is_cleared(self):
        self.assertIn("localStorage.getItem(SELECTED_CHANNEL_STORAGE_KEY)", self.html)
        self.assertIn("validSavedSlug", self.html)
        self.assertIn("if (savedSlug && !validSavedSlug) localStorage.removeItem(SELECTED_CHANNEL_STORAGE_KEY);", self.html)
        self.assertIn('state.errorMessage = "The previously selected channel is no longer available. Please select another channel.";', self.html)

    def test_no_hard_coded_mist_of_ages_selection_fallback_exists(self):
        forbidden_patterns = [
            r'selectedChannelSlug\s*=\s*"mist_of_ages"',
            r'getItem\(SELECTED_CHANNEL_STORAGE_KEY\)\s*\|\|\s*"mist_of_ages"',
            r'/api/v2/channels/mist_of_ages',
        ]
        for pattern in forbidden_patterns:
            self.assertIsNone(re.search(pattern, self.html))

    def test_nested_v2_error_handling_and_safe_fallback_exist(self):
        self.assertIn('payload.error && typeof payload.error.message === "string"', self.html)
        self.assertIn('payload.error && typeof payload.error.code === "string"', self.html)
        self.assertIn('JSON.parse(text)', self.html)
        self.assertIn("The request could not be completed.", self.html)
        self.assertIn("Could not reach the local collector UI.", self.html)

    def test_stale_async_responses_cannot_replace_current_selection(self):
        for token in [
            "summaryRequestId",
            "summaryAbortController",
            "projectListRequestId",
            "projectDetailRequestId",
            "new AbortController()",
            "requestId !== state.summaryRequestId",
            "slug !== state.selectedChannelSlug",
            "state.oauthAction.requestId !== requestId",
            "state.metricsAction.requestId !== requestId",
            "state.createProjectAction.requestId !== requestId",
            "state.transcriptSaveAction.requestId !== requestId",
            "state.validationAction.requestId !== requestId",
            "projectSlug !== state.selectedProjectSlug",
        ]:
            self.assertIn(token, self.html)

    def test_no_channel_and_disconnected_states_are_rendered(self):
        self.assertIn("Selection required", self.html)
        self.assertIn("No channel is selected.", self.html)
        self.assertIn("Channel disconnected", self.html)
        self.assertIn("This selected channel is not currently connected.", self.html)

    def test_oauth_ui_uses_selected_slug_and_canonical_v2_route(self):
        self.assertIn("oauth/start?channel_slug=${encodeURIComponent(slug)}&mode=${encodeURIComponent(mode)}", self.html)
        self.assertIn('label: busy ? (isConnected ? "Starting reconnect..." : "Starting connection...") : (isConnected ? "Reconnect Channel" : "Connect Channel")', self.html)
        self.assertIn('mode: "reconnect"', self.html)
        self.assertNotIn('window.open("/oauth/start"', self.html)

    def test_metrics_ui_uses_selected_slug_and_canonical_post_route(self):
        self.assertIn('channels/${encodeURIComponent(slug)}/sync_metrics', self.html)
        self.assertIn('method: "POST"', self.html)
        self.assertIn("window_days", self.html)
        self.assertIn("recent_count", self.html)
        self.assertIn("Metrics sync is available only when the selected channel is connected.", self.html)

    def test_project_list_and_detail_use_selected_channel_and_project_routes(self):
        self.assertIn('v2Api(`channels/${encodeURIComponent(slug)}/projects`)', self.html)
        self.assertIn('v2Api(`channels/${encodeURIComponent(channelSlug)}/projects/${encodeURIComponent(projectSlug)}`)', self.html)
        self.assertIn('Select a channel to load its canonical project list.', self.html)
        self.assertIn("No canonical projects yet", self.html)
        self.assertIn("setSelectedProjectSlug(", self.html)

    def test_project_creation_uses_exact_v2_route_and_supported_payload(self):
        self.assertIn('v2Api(`channels/${encodeURIComponent(slug)}/projects`, {', self.html)
        self.assertIn('const payload = { url };', self.html)
        self.assertIn("payload.project_name = projectName;", self.html)
        self.assertIn("Project creation is available only when the selected channel is connected.", self.html)
        self.assertNotIn("project_slug:", self.html)

    def test_transcript_and_validation_use_exact_v2_project_routes(self):
        self.assertIn('v2Api(`channels/${encodeURIComponent(slug)}/projects/${encodeURIComponent(projectSlug)}/transcript`, {', self.html)
        self.assertIn('const body = { transcript: transcriptText };', self.html)
        self.assertIn("body.overwrite = true;", self.html)
        self.assertIn('v2Api(`channels/${encodeURIComponent(slug)}/projects/${encodeURIComponent(projectSlug)}/validate`, {', self.html)
        self.assertIn('body: JSON.stringify({})', self.html)

    def test_duplicate_and_stale_action_requests_are_blocked(self):
        for token in [
            "state.oauthAction.busy && state.oauthAction.slug === state.selectedChannelSlug",
            "state.metricsAction.busy && state.metricsAction.slug === state.selectedChannelSlug",
            "state.createProjectAction.busy && state.createProjectAction.slug === state.selectedChannelSlug",
            "state.transcriptSaveAction.busy",
            "state.validationAction.busy",
            "if (oauth.disabled)",
            "if (metrics.disabled)",
            "clearActionFeedback();",
            "clearProjectState();",
            "clearProjectFeedback();",
            "await refreshSelectedSummaryForAction(slug);",
            "await loadProjectsForChannel(slug);",
            "await loadSelectedProjectDetail(projectSlug, slug);",
        ]:
            self.assertIn(token, self.html)

    def test_legacy_mutations_and_raw_opening_are_absent_from_visible_frontend(self):
        self.assertGreaterEqual(self.html.count('data-cutover-state="disabled"'), 3)
        for path in [
            "/oauth/start",
            "/api/create_project",
            "/api/save_transcript",
            "/api/validate",
            "/api/open_path",
        ]:
            self.assertNotIn(path, self.html)
        self.assertIn("Raw-path opening and later collector actions remain disabled.", self.html)
        self.assertIn("Project workflow cutover is partially active.", self.html)

    def test_frontend_contains_no_live_credential_material(self):
        forbidden = [
            "Bearer ey",
            "refresh_token\":",
            "client_secret\":",
            "authorization_code",
        ]
        for token in forbidden:
            self.assertNotIn(token, self.html)

    def test_visible_ui_still_signals_embedded_collector_context(self):
        self.assertIn("Mist of Ages Research", self.html)
        self.assertIn("Refresh Channels", self.html)
        self.assertIn("Selected Channel Summary", self.html)
        self.assertIn("Selected Channel Actions", self.html)
        self.assertIn("Research Projects", self.html)
        self.assertIn("Project Detail", self.html)


if __name__ == "__main__":
    unittest.main()
