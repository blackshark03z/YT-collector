import json
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import ui_server


SCRIPT_MATCH = re.search(r"<script>\n(.*)\n</script>", ui_server.HTML_PAGE, re.DOTALL)
assert SCRIPT_MATCH is not None
UI_SCRIPT = SCRIPT_MATCH.group(1)


def run_ui_runtime_scenario(body: str) -> dict:
    node = shutil.which("node")
    if node is None:
        raise unittest.SkipTest("node runtime is not available")
    harness = f"""
const uiScript = {json.dumps(UI_SCRIPT)};
const scenarioBody = {json.dumps(textwrap.dedent(body).strip())};

function makeDeferred() {{
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => {{
    resolve = res;
    reject = rej;
  }});
  return {{ promise, resolve, reject }};
}}

class Element {{
  constructor(id = "") {{
    this.id = id;
    this._innerHTML = "";
    this.textContent = "";
    this.value = "";
    this.disabled = false;
    this.style = {{}};
    this.attributes = {{}};
    this.listeners = {{}};
    this.children = [];
    this.dataset = {{}};
    this.selectionStart = 0;
    this.selectionEnd = 0;
  }}
  set innerHTML(value) {{
    this._innerHTML = String(value);
  }}
  get innerHTML() {{
    return this._innerHTML;
  }}
  addEventListener(type, handler) {{
    this.listeners[type] = handler;
  }}
  setAttribute(name, value) {{
    this.attributes[name] = String(value);
  }}
  getAttribute(name) {{
    return this.attributes[name] || null;
  }}
  focus() {{
    document.activeElement = this;
  }}
  select() {{
    this.selectionStart = 0;
    this.selectionEnd = this.value.length;
  }}
  closest() {{
    return null;
  }}
  appendChild(child) {{
    this.children.push(child);
    return child;
  }}
  removeChild(child) {{
    this.children = this.children.filter((item) => item !== child);
  }}
}}

const elements = new Map();
function getElement(id) {{
  if (!elements.has(id)) elements.set(id, new Element(id));
  return elements.get(id);
}}

const bodyChildren = [];
const document = {{
  activeElement: null,
  body: {{
    appendChild(node) {{
      bodyChildren.push(node);
      return node;
    }},
    removeChild(node) {{
      const index = bodyChildren.indexOf(node);
      if (index >= 0) bodyChildren.splice(index, 1);
      return node;
    }},
  }},
  getElementById(id) {{
    return getElement(id);
  }},
  createElement(tag) {{
    return new Element(tag);
  }},
  execCommand(command) {{
    execCommandCalls.push(command);
    return execCommandResult;
  }},
}};

const localStorageData = new Map();
const localStorage = {{
  getItem(key) {{
    return localStorageData.has(key) ? localStorageData.get(key) : null;
  }},
  setItem(key, value) {{
    localStorageData.set(key, String(value));
  }},
  removeItem(key) {{
    localStorageData.delete(key);
  }},
}};

let fetchCalls = [];
let fetchHandler = async () => jsonResponse({{ channels: [] }});
async function fetch(path, config = {{}}) {{
  fetchCalls.push({{
    path,
    method: config.method || "GET",
    body: config.body ?? null,
  }});
  return await fetchHandler(path, config);
}}

function jsonResponse(payload, options = {{}}) {{
  return {{
    ok: options.ok !== false,
    status: options.status || (options.ok === false ? 409 : 200),
    statusText: options.statusText || (options.ok === false ? "ERROR" : "OK"),
    text: async () => JSON.stringify(payload),
  }};
}}

function errorResponse(code, message, status = 409) {{
  return jsonResponse({{ error: {{ code, message }} }}, {{ ok: false, status, statusText: "ERROR" }});
}}

let clipboardCalls = [];
let clipboardReject = null;
let execCommandCalls = [];
let execCommandResult = true;
const navigator = {{
  clipboard: {{
    async writeText(text) {{
      if (clipboardReject) throw clipboardReject;
      clipboardCalls.push(text);
    }},
  }},
}};

const openedUrls = [];
const window = globalThis;
window.open = (url) => {{
  openedUrls.push(url);
  return {{}};
}};
window.document = document;
window.localStorage = localStorage;
window.fetch = fetch;
window.navigator = navigator;
window.setTimeout = setTimeout;
window.clearTimeout = clearTimeout;
globalThis.document = document;
globalThis.localStorage = localStorage;
globalThis.fetch = fetch;
globalThis.navigator = navigator;
globalThis.window = window;

[
  "channelSelect",
  "channelState",
  "connectChannelBtn",
  "syncMetricsBtn",
  "recent",
  "window",
  "actionState",
  "refreshProjectsBtn",
  "createBtn",
  "url",
  "name",
  "workflowBinding",
  "projectListState",
  "projectListPanel",
  "projectCreateState",
  "projectDetailState",
  "projectDetailPanel",
  "validationPanel",
  "transcript",
  "saveTranscriptBtn",
  "validateProjectBtn",
  "summaryPanel",
  "message",
  "openLearningsBtn",
  "openProjectBtn",
  "openTranscriptBtn",
].forEach(getElement);

getElement("window").value = "28";
getElement("recent").value = "10";
document.activeElement = getElement("channelSelect");

async function flush() {{
  await new Promise((resolve) => setTimeout(resolve, 0));
  await new Promise((resolve) => setTimeout(resolve, 0));
}}

function assert(condition, message) {{
  if (!condition) throw new Error(message);
}}

(async () => {{
  eval(uiScript + "\\n;globalThis.__scenarioPromise = (async () => {{\\n" + scenarioBody + "\\n}})();");
  const result = await globalThis.__scenarioPromise;
  process.stdout.write(JSON.stringify(result));
}})().catch((error) => {{
  console.error(error && error.stack ? error.stack : String(error));
  process.exit(1);
}});
"""
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as handle:
        handle.write(harness)
        harness_path = handle.name
    try:
        completed = subprocess.run(
            [node, harness_path],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=True,
        )
    finally:
        Path(harness_path).unlink(missing_ok=True)
    return json.loads(completed.stdout)


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
                "channels/${encodeURIComponent(channelSlug)}/projects/${encodeURIComponent(projectSlug)}/workflow",
                "channels/${encodeURIComponent(channelSlug)}/projects/${encodeURIComponent(projectSlug)}/workflow/steps/${encodeURIComponent(step.step_id)}/bundle",
                "channels/${encodeURIComponent(channelSlug)}/projects/${encodeURIComponent(projectSlug)}/workflow/steps/${encodeURIComponent(step.step_id)}/parse-output",
                "channels/${encodeURIComponent(channelSlug)}/projects/${encodeURIComponent(projectSlug)}/workflow/steps/${encodeURIComponent(step.step_id)}/revisions",
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
            "selectedProjectWorkflow",
            "selectedWorkflowStepId",
            "selectedWorkflowBundle",
            "pastedOutputDraft",
            "parsedOutputResult",
            "parsedOutputError",
            "state.channels",
            "state.projects",
            "state.isLoadingChannels",
            "state.isLoadingSummary",
            "state.isLoadingProjects",
            "state.isLoadingProjectDetail",
            "state.isLoadingWorkflow",
            "oauthAction",
            "metricsAction",
            "actionFeedback",
            "createProjectAction",
            "transcriptSaveAction",
            "validationAction",
            "projectFeedback",
            "bundleAction",
            "bundleFeedback",
            "parseOutputAction",
            "saveCandidateAction",
            "candidateSaveFeedback",
            "lastSaveCandidateResult",
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
            "workflowRequestId",
            "new AbortController()",
            "requestId !== state.summaryRequestId",
            "slug !== state.selectedChannelSlug",
            "state.oauthAction.requestId !== requestId",
            "state.metricsAction.requestId !== requestId",
            "state.createProjectAction.requestId !== requestId",
            "state.transcriptSaveAction.requestId !== requestId",
            "state.validationAction.requestId !== requestId",
            "projectSlug !== state.selectedProjectSlug",
            "state.bundleAction.requestId !== requestId",
            "step.step_id !== state.selectedWorkflowStepId",
            "bundleMatchesSelection(state.selectedWorkflowBundle)",
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

    def test_workflow_panel_uses_selected_project_workflow_and_bundle_routes(self):
        self.assertIn('v2Api(`channels/${encodeURIComponent(channelSlug)}/projects/${encodeURIComponent(projectSlug)}/workflow`)', self.html)
        self.assertIn('v2Api(`channels/${encodeURIComponent(channelSlug)}/projects/${encodeURIComponent(projectSlug)}/workflow/steps/${encodeURIComponent(step.step_id)}/bundle`)', self.html)
        self.assertIn('v2Api(`channels/${encodeURIComponent(channelSlug)}/projects/${encodeURIComponent(projectSlug)}/workflow/steps/${encodeURIComponent(step.step_id)}/parse-output`, {', self.html)
        self.assertIn('v2Api(`channels/${encodeURIComponent(channelSlug)}/projects/${encodeURIComponent(projectSlug)}/workflow/steps/${encodeURIComponent(step.step_id)}/revisions`, {', self.html)
        self.assertIn("Workflow Panel", self.html)
        self.assertIn("Workflow Steps", self.html)
        self.assertIn("Selected Workflow Step", self.html)
        self.assertIn("Build Complete Bundle", self.html)
        self.assertIn("Copy Complete Bundle", self.html)
        self.assertIn("Parse and Preview", self.html)
        self.assertIn("Save Candidate", self.html)
        self.assertIn("Paste AI Output", self.html)
        self.assertIn("Prompt bundle unavailable for this workflow version.", self.html)

    def test_workflow_step_selection_clears_bundle_without_auto_fetch(self):
        self.assertIn("setSelectedWorkflowStepId(nextStepId)", self.html)
        self.assertIn("invalidateLoadedBundle();", self.html)
        self.assertIn('if (event.target.id === "workflowStepSelect")', self.html)
        self.assertIn('data-workflow-step-id="${escapeHtml(step.step_id)}"', self.html)
        self.assertNotIn('workflowStepSelect")\n    buildBundleAction()', self.html)

    def test_bundle_preview_and_copy_use_exact_state_bundle_text(self):
        self.assertIn('<textarea id="bundlePreviewText" readonly spellcheck="false"></textarea>', self.html)
        self.assertIn('bundlePreviewText.value = typeof bundle.bundle === "string" ? bundle.bundle : "";', self.html)
        self.assertIn("navigator.clipboard.writeText(bundle.bundle)", self.html)
        self.assertIn("await fallbackCopyBundleText(bundle.bundle);", self.html)
        self.assertIn("bundle.bundle_character_count", self.html)
        self.assertIn("bundle.bundle_sha256", self.html)
        self.assertIn("bundle.prompt_file_sha256", self.html)
        self.assertIn('role="status" aria-live="polite"', self.html)

    def test_output_preview_contract_and_safe_error_mapping_exist(self):
        for token in [
            "pastedOutputText",
            "parseOutputBtn",
            "parsedArtifactPreview${index}",
            "parsedOutputMatchesSelection(state.parsedOutputResult)",
            "parsedOutputIdentityForSelection(state.pastedOutputDraft)",
            "parseOutputErrorSummary(error, \"Could not parse the pasted output preview.\")",
            "saveCandidateErrorSummary(error, \"Could not save the current candidate output.\")",
            "BUNDLE_IDENTITY_MISMATCH",
            "OUTPUT_TEXT_REQUIRED",
            "OUTPUT_CONTRACT_INVALID",
            "PROMPT_OUTPUT_PARSE_FAILED",
            "PROMPT_OUTPUT_INVALID",
            "STATE_REVISION_CONFLICT",
            "CANDIDATE_EXISTS",
        ]:
            self.assertIn(token, self.html)

    def test_workflow_panel_renders_generic_step_and_constraint_data(self):
        self.assertIn("Generated from the workflow definition in step order.", self.html)
        self.assertIn("workflowSteps.length", self.html)
        self.assertIn("describeConversationConstraint(step)", self.html)
        self.assertIn("Continue in the same ${step.required_model || \"selected\"} conversation: ${constraint.group_id}", self.html)
        self.assertIn("No same-conversation requirement", self.html)

    def test_workflow_errors_are_mapped_to_safe_user_messages(self):
        for token in [
            "WORKFLOW_NOT_CONFIGURED",
            "WORKFLOW_STATE_INVALID",
            "PROMPT_SET_UNAVAILABLE",
            "PROMPT_MANIFEST_INVALID",
            "PROMPT_FILE_NOT_FOUND",
            "PROMPT_FILE_DIGEST_MISMATCH",
            "WORKFLOW_STEP_NOT_FOUND",
            "BUNDLE_REQUIRED_INPUT_MISSING",
            "BUNDLE_PROJECT_CONTEXT_MISSING",
            "PROMPT_BUNDLE_INVALID",
        ]:
            self.assertIn(token, self.html)
        self.assertIn("bundleValidationError(bundle)", self.html)
        self.assertIn("The loaded workflow bundle metadata is inconsistent.", self.html)

    def test_project_creation_uses_exact_v2_route_and_supported_payload(self):
        self.assertIn('v2Api(`channels/${encodeURIComponent(slug)}/projects`, {', self.html)
        self.assertIn('const payload = {', self.html)
        self.assertIn('competitor_url: url,', self.html)
        self.assertIn('workflow_id: workflowOption.workflow_id,', self.html)
        self.assertIn('workflow_version: workflowOption.workflow_version', self.html)
        self.assertIn("payload.project_name = projectName;", self.html)
        self.assertIn('Select a workflow version before creating a project.', self.html)
        self.assertIn('No server-approved workflow options are available for the selected channel.', self.html)
        create_action = self.html[self.html.index("async function createProjectAction()"):self.html.index("async function loadSelectedProjectDetail(")]
        self.assertNotIn('workflow_definition_sha256', create_action)
        self.assertNotIn('workflow_definition_path', create_action)
        self.assertNotIn('prompt_manifest_path', create_action)
        self.assertIn("Project creation is available only when the selected channel is connected.", self.html)

    def test_workflow_selector_uses_server_owned_options_without_hidden_default(self):
        for token in [
            '<label for="workflowBinding">Workflow Version</label>',
            '<select id="workflowBinding" disabled>',
            'available_workflows',
            'function channelWorkflowOptions()',
            'function selectedCreateWorkflowOption()',
            'workflowSelect.innerHTML = optionRows.join("")',
            'workflowSelect.disabled = !state.selectedChannelSlug || state.isLoadingSummary || !workflowOptions.length || state.createProjectAction.busy;',
            "return `${option.workflow_id}@@${option.workflow_version}`;",
            'const label = `${option.display_name || option.workflow_id} v${option.workflow_version}`;',
            'document.getElementById("workflowBinding").addEventListener("change", () => {',
        ]:
            self.assertIn(token, self.html)
        self.assertNotIn('workflowSelect.value = workflowOptions[0]', self.html)
        self.assertNotIn('value="mist_of_ages_assisted_content@@2"', self.html)

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
            "state.saveCandidateAction.busy",
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

    def test_output_preview_uses_no_browser_persistence_or_file_save_api(self):
        for token in [
            "sessionStorage",
            "indexedDB",
            "showSaveFilePicker",
            "createObjectURL",
            "download=",
            "Blob(",
        ]:
            self.assertNotIn(token, self.html)
        self.assertNotIn("localStorage.setItem(\"yt_input_collector.pastedOutput", self.html)

    def test_visible_ui_still_signals_embedded_collector_context(self):
        self.assertIn("Mist of Ages Research", self.html)
        self.assertIn("Refresh Channels", self.html)
        self.assertIn("Selected Channel Summary", self.html)
        self.assertIn("Selected Channel Actions", self.html)
        self.assertIn("Research Projects", self.html)
        self.assertIn("Project Detail", self.html)
        self.assertIn("Read-only workflow detail for the selected canonical project.", self.html)


class UiFrontendRuntimeTests(unittest.TestCase):
    def test_workflow_selector_loads_from_server_summary_and_create_stays_disabled_without_selection(self):
        result = run_ui_runtime_scenario(
            """
            await flush();
            state.selectedChannelSlug = "channel-a";
            state.selectedChannelSummary = {
              channel: { channel_slug: "channel-a", status: "CONNECTED" },
              available_workflows: [
                { workflow_id: "wf-alpha", workflow_version: "2", display_name: "Workflow <Alpha>", version_status: "ACTIVE" },
                { workflow_id: "wf-alpha", workflow_version: "1", display_name: "Workflow <Alpha>", version_status: "ACTIVE" },
              ],
            };
            render();
            const select = document.getElementById("workflowBinding");
            const button = document.getElementById("createBtn");
            return {
              createDisabled: button.disabled,
              selectDisabled: select.disabled,
              selectHtml: select.innerHTML,
              helperHtml: document.getElementById("projectCreateState").innerHTML,
            };
            """
        )
        self.assertTrue(result["createDisabled"])
        self.assertFalse(result["selectDisabled"])
        self.assertIn("Select a workflow</option>", result["selectHtml"])
        self.assertIn("Workflow &lt;Alpha&gt; v2", result["selectHtml"])
        self.assertIn("Workflow &lt;Alpha&gt; v1", result["selectHtml"])
        self.assertIn("Select a workflow version before creating a project.", result["helperHtml"])

    def test_create_project_sends_only_selected_workflow_id_and_version(self):
        result = run_ui_runtime_scenario(
            """
            await flush();
            state.selectedChannelSlug = "channel-a";
            state.selectedChannelSummary = {
              channel: { channel_slug: "channel-a", status: "CONNECTED" },
              available_workflows: [
                { workflow_id: "wf-alpha", workflow_version: "2", display_name: "Workflow Alpha", version_status: "ACTIVE" },
              ],
            };
            fetchHandler = async (path, config) => {
              if (path === "/api/v2/channels/channel-a/projects" && (config.method || "GET") === "POST") {
                return jsonResponse({
                  project: {
                    project_slug: "project-a",
                    channel_slug: "channel-a",
                    workflow_binding: {
                      workflow_id: "wf-alpha",
                      workflow_version: "2",
                      workflow_definition_sha256: "server-digest",
                    },
                  },
                });
              }
              if (path === "/api/v2/channels/channel-a") {
                return jsonResponse(state.selectedChannelSummary);
              }
              if (path === "/api/v2/channels/channel-a/projects") {
                return jsonResponse({ projects: [{ project_slug: "project-a" }] });
              }
              if (path === "/api/v2/channels/channel-a/projects/project-a") {
                return jsonResponse({
                  project: {
                    project_slug: "project-a",
                    channel_slug: "channel-a",
                    source_video_id: "VIDEO12345A",
                    source_video_url: "https://youtube.com/watch?v=VIDEO12345A",
                    status: "READY",
                    workflow_input_status: "READY",
                    runnable: true,
                    created_at: "2026-07-03T00:00:00Z",
                    updated_at: "2026-07-03T00:00:00Z",
                    has_content: false,
                    has_publishing_package: false,
                    workflow_binding: {
                      workflow_id: "wf-alpha",
                      workflow_version: "2",
                      workflow_definition_sha256: "server-digest",
                    },
                  },
                });
              }
              if (path === "/api/v2/channels/channel-a/projects/project-a/workflow") {
                return jsonResponse({
                  channel_slug: "channel-a",
                  project_slug: "project-a",
                  binding: {
                    workflow_id: "wf-alpha",
                    workflow_version: "2",
                    workflow_definition_sha256: "server-digest",
                    binding_source: "PROJECT_JSON",
                  },
                  definition: {
                    workflow_id: "wf-alpha",
                    workflow_version: "2",
                    display_name: "Workflow Alpha",
                    execution_mode: "ASSISTED",
                    prompt_set: { status: "AVAILABLE", bundle_available: true },
                    steps: [],
                  },
                  state: {
                    current_step_id: null,
                    current_step_status: "READY",
                    next_step_id: null,
                    current_lifecycle_state: "INPUT_READY",
                  },
                  artifacts: [],
                });
              }
              if (path === "/api/v2/channels/channel-a/projects/project-a/transcript") {
                return jsonResponse({ transcript: "", is_template: true, has_real_content: false });
              }
              return jsonResponse({ channels: [] });
            };
            render();
            document.getElementById("url").value = "https://youtube.com/watch?v=VIDEO12345A";
            document.getElementById("workflowBinding").value = "wf-alpha@@2";
            render();
            await createProjectAction();
            await flush();
            const createCall = fetchCalls.find((call) => call.path === "/api/v2/channels/channel-a/projects" && call.method === "POST");
            return {
              createDisabledAfterSelection: document.getElementById("createBtn").disabled,
              createBody: JSON.parse(createCall.body),
              feedback: state.projectFeedback.text,
              workflowVersionCardVisible: document.getElementById("projectDetailPanel").innerHTML.includes("Workflow Version"),
              workflowVersionVisible: document.getElementById("projectDetailPanel").innerHTML.includes(">2<"),
            };
            """
        )
        self.assertFalse(result["createDisabledAfterSelection"])
        self.assertEqual(
            result["createBody"],
            {
                "competitor_url": "https://youtube.com/watch?v=VIDEO12345A",
                "workflow_id": "wf-alpha",
                "workflow_version": "2",
            },
        )
        self.assertNotIn("workflow_definition_sha256", result["createBody"])
        self.assertNotIn("workflow_definition_path", result["createBody"])
        self.assertNotIn("prompt_manifest_path", result["createBody"])
        self.assertEqual(result["feedback"], "Canonical project created for the selected channel.")
        self.assertTrue(result["workflowVersionCardVisible"])
        self.assertTrue(result["workflowVersionVisible"])

    def test_channel_change_invalidates_stale_workflow_options(self):
        result = run_ui_runtime_scenario(
            """
            await flush();
            state.channels = [
              { channel_slug: "channel-a", status: "CONNECTED" },
              { channel_slug: "channel-b", status: "CONNECTED" },
            ];
            fetchHandler = async (path) => {
              if (path === "/api/v2/channels/channel-b") {
                return jsonResponse({
                  channel: { channel_slug: "channel-b", status: "CONNECTED" },
                  available_workflows: [],
                });
              }
              return jsonResponse({ channels: [] });
            };
            state.selectedChannelSlug = "channel-a";
            state.selectedChannelSummary = {
              channel: { channel_slug: "channel-a", status: "CONNECTED" },
              available_workflows: [
                { workflow_id: "wf-alpha", workflow_version: "2", display_name: "Workflow Alpha", version_status: "ACTIVE" },
              ],
            };
            render();
            document.getElementById("workflowBinding").value = "wf-alpha@@2";
            render();
            setSelectedChannelSlug("channel-b");
            await flush();
            const select = document.getElementById("workflowBinding");
            return {
              selectedChannelSlug: state.selectedChannelSlug,
              selectedChannelSummary: state.selectedChannelSummary,
              selectedProjectSlug: state.selectedProjectSlug,
              selectValue: select.value,
              selectDisabled: select.disabled,
              createDisabled: document.getElementById("createBtn").disabled,
              selectHtml: select.innerHTML,
            };
            """
        )
        self.assertEqual(result["selectedChannelSlug"], "channel-b")
        self.assertEqual(result["selectedChannelSummary"]["channel"]["channel_slug"], "channel-b")
        self.assertEqual(result["selectedChannelSummary"]["available_workflows"], [])
        self.assertIsNone(result["selectedProjectSlug"])
        self.assertTrue(result["selectDisabled"])
        self.assertTrue(result["createDisabled"])
        self.assertNotIn("wf-alpha@@2", result["selectHtml"])

    def test_step_change_build_copy_and_inert_bundle_preview(self):
        result = run_ui_runtime_scenario(
            """
            await flush();
            state.selectedChannelSlug = "channel-a";
            state.selectedProjectSlug = "project-a";
            state.selectedProjectDetail = { project: { project_slug: "project-a", status: "READY", workflow_input_status: "READY", runnable: true, source_video_id: "VID1", source_video_url: "https://example.com", updated_at: "2026-07-02T00:00:00Z" } };
            state.selectedProjectWorkflow = {
              channel_slug: "channel-a",
              project_slug: "project-a",
              binding: {
                workflow_id: "wf-demo",
                workflow_version: "2",
                workflow_definition_sha256: "abc123",
                binding_source: "PROJECT_JSON",
              },
              definition: {
                workflow_id: "wf-demo",
                workflow_version: "2",
                display_name: "Workflow <Demo>",
                execution_mode: "ASSISTED",
                prompt_set: { status: "AVAILABLE", bundle_available: true },
                steps: [
                  {
                    step_id: "alpha-step",
                    order: 1,
                    display_name: "Alpha <Step>",
                    required_model: "Gemini 2.5",
                    input_artifact_ids: ["input_a"],
                    optional_input_artifact_ids: ["optional_a"],
                    output_artifact_ids: ["output_a"],
                    resulting_lifecycle_state: "READY",
                    constraints: [],
                  },
                  {
                    step_id: "beta-step",
                    order: 2,
                    display_name: "Beta",
                    required_model: "Claude 4",
                    input_artifact_ids: [],
                    optional_input_artifact_ids: [],
                    output_artifact_ids: [],
                    resulting_lifecycle_state: "DONE",
                    constraints: [{ type: "SAME_MODEL_CONVERSATION_REQUIRED", group_id: "claude_group" }],
                  },
                ],
              },
              state: {
                current_step_id: "alpha-step",
                current_step_status: "READY",
                next_step_id: "beta-step",
                current_lifecycle_state: "INPUT_READY",
              },
              artifacts: [
                { artifact_id: "input_a", display_name: "Input <A>", relative_path: "workflow/input_a.md", exists: true },
                { artifact_id: "optional_a", display_name: "Optional", relative_path: "workflow/optional_a.md", exists: false },
                { artifact_id: "output_a", display_name: "Output", relative_path: "workflow/output_a.md", exists: false },
              ],
            };
            state.selectedWorkflowStepId = "alpha-step";
            const bundleText = "Line 1\\n<img src=x onerror=alert(1)>\\n<script>throw new Error(\\"unsafe\\")</script>\\n& < > \\" '";
            fetchHandler = async (path) => {
              if (path.includes("/workflow/steps/alpha-step/bundle")) {
                return jsonResponse({
                  channel_slug: "channel-a",
                  project_slug: "project-a",
                  step_id: "alpha-step",
                  binding: {
                    workflow_id: "wf-demo",
                    workflow_version: "2",
                    workflow_definition_sha256: "abc123",
                  },
                  bundle: bundleText,
                  bundle_sha256: "sha-alpha",
                  bundle_character_count: bundleText.length,
                  prompt_file_sha256: "prompt-sha",
                  input_artifact_ids: ["input_a"],
                  missing_optional_inputs: ["optional_a"],
                  required_model: "Gemini 2.5",
                  output_contract: { response_mode: "TEXT_ONLY" },
                });
              }
              return jsonResponse({ channels: [] });
            };
            render();
            const beforeFetchCount = fetchCalls.length;
            setSelectedWorkflowStepId("beta-step");
            await flush();
            const afterStepFetchCount = fetchCalls.length;
            setSelectedWorkflowStepId("alpha-step");
            await flush();
            await buildBundleAction();
            await flush();
            const previewValue = document.getElementById("bundlePreviewText").value;
            const panelHtml = document.getElementById("projectDetailPanel").innerHTML;
            await copyBundleAction();
            await flush();
            return {
              beforeFetchCount,
              afterStepFetchCount,
              bundleFetchCalls: fetchCalls.filter((call) => call.path.includes("/workflow/steps/alpha-step/bundle")).length,
              bundlePath: fetchCalls.find((call) => call.path.includes("/workflow/steps/alpha-step/bundle")).path,
              storedBundle: state.selectedWorkflowBundle.bundle,
              previewValue,
              panelContainsRawImg: panelHtml.includes("<img src=x onerror=alert(1)>"),
              panelContainsEscapedStepName: panelHtml.includes("Alpha &lt;Step&gt;"),
              clipboardCalls,
              copyFeedback: state.bundleFeedback.text,
            };
            """
        )
        self.assertEqual(result["beforeFetchCount"], result["afterStepFetchCount"])
        self.assertEqual(result["bundleFetchCalls"], 1)
        self.assertEqual(
            result["bundlePath"],
            "/api/v2/channels/channel-a/projects/project-a/workflow/steps/alpha-step/bundle",
        )
        self.assertEqual(result["storedBundle"], result["previewValue"])
        self.assertEqual(result["clipboardCalls"], [result["storedBundle"]])
        self.assertFalse(result["panelContainsRawImg"])
        self.assertTrue(result["panelContainsEscapedStepName"])
        self.assertEqual(result["copyFeedback"], "Copied the exact complete bundle.")

    def test_parse_output_preview_uses_current_bundle_and_renders_exact_artifact_text(self):
        result = run_ui_runtime_scenario(
            """
            await flush();
            state.selectedChannelSlug = "channel-a";
            state.selectedProjectSlug = "project-a";
            state.selectedProjectDetail = { project: { project_slug: "project-a", status: "READY", workflow_input_status: "READY", runnable: true, source_video_id: "VID1", source_video_url: "https://example.com", updated_at: "2026-07-02T00:00:00Z" } };
            state.selectedProjectWorkflow = {
              binding: { workflow_id: "wf-demo", workflow_version: "2", workflow_definition_sha256: "sha-workflow", binding_source: "PROJECT_JSON" },
              definition: {
                workflow_id: "wf-demo",
                workflow_version: "2",
                display_name: "Workflow Demo",
                execution_mode: "ASSISTED",
                prompt_set: { status: "AVAILABLE", bundle_available: true },
                steps: [{ step_id: "step-1", order: 1, display_name: "Step 1", required_model: "Gemini", input_artifact_ids: [], optional_input_artifact_ids: [], output_artifact_ids: ["artifact-a"], resulting_lifecycle_state: "ONE", constraints: [] }],
              },
              state: { current_step_id: "step-1", current_step_status: "READY", next_step_id: null, current_lifecycle_state: "INPUT_READY" },
              artifacts: [{ artifact_id: "artifact-a", display_name: "Artifact A", relative_path: "workflow/artifact_a.md", exists: false }],
            };
            state.selectedWorkflowStepId = "step-1";
            state.selectedWorkflowBundle = {
              channel_slug: "channel-a",
              project_slug: "project-a",
              step_id: "step-1",
              binding: { workflow_id: "wf-demo", workflow_version: "2", workflow_definition_sha256: "sha-workflow" },
              bundle: "Prompt bundle",
              bundle_sha256: "sha-bundle",
              bundle_character_count: "Prompt bundle".length,
              prompt_file_sha256: "prompt-sha",
              input_artifact_ids: [],
              missing_optional_inputs: [],
              required_model: "Gemini",
              output_contract: { response_mode: "SINGLE_ARTIFACT" },
              identity: { channel_slug: "channel-a", project_slug: "project-a", workflow_id: "wf-demo", workflow_version: "2", workflow_definition_sha256: "sha-workflow", step_id: "step-1", bundle_sha256: "sha-bundle" },
            };
            state.pastedOutputDraft = "## Subject\\nRome\\n<img src=x onerror=1>";
            fetchHandler = async (path, config) => {
              if (path.endsWith("/steps/step-1/parse-output")) {
                return jsonResponse({
                  identity: { channel_slug: "channel-a", project_slug: "project-a", workflow_id: "wf-demo", workflow_version: "2", step_id: "step-1", bundle_sha256: "sha-bundle" },
                  raw_output: { sha256: "raw-sha", character_count: state.pastedOutputDraft.length },
                  contract: { response_mode: "SINGLE_ARTIFACT" },
                  status: "VALID",
                  artifacts: [{
                    artifact_id: "artifact-a",
                    display_name: "Artifact A",
                    filename: "artifact_a.md",
                    content: state.pastedOutputDraft,
                    sha256: "artifact-sha",
                    character_count: state.pastedOutputDraft.length,
                    validation: { status: "VALID", errors: [], warnings: [], heading_results: [] },
                  }],
                  validation: { errors: [], warnings: [] },
                });
              }
              return jsonResponse({ channels: [] });
            };
            render();
            await parseOutputAction();
            await flush();
            return {
              parseCalls: fetchCalls.filter((call) => call.path.includes("/parse-output")).length,
              parsePath: fetchCalls.find((call) => call.path.includes("/parse-output")).path,
              parseBody: fetchCalls.find((call) => call.path.includes("/parse-output")).body,
              previewStatus: state.parsedOutputResult && state.parsedOutputResult.status,
              parsedPreviewValue: document.getElementById("parsedArtifactPreview0").value,
              panelContainsRawImg: document.getElementById("projectDetailPanel").innerHTML.includes("<img src=x onerror=1>"),
            };
            """
        )
        self.assertEqual(result["parseCalls"], 1)
        self.assertEqual(
            result["parsePath"],
            "/api/v2/channels/channel-a/projects/project-a/workflow/steps/step-1/parse-output",
        )
        self.assertIn('"bundle_sha256":"sha-bundle"', result["parseBody"])
        self.assertEqual(result["previewStatus"], "VALID")
        self.assertEqual(result["parsedPreviewValue"], "## Subject\nRome\n<img src=x onerror=1>")
        self.assertFalse(result["panelContainsRawImg"])

    def test_output_textarea_stays_disabled_without_bundle_and_paste_does_not_auto_parse(self):
        result = run_ui_runtime_scenario(
            """
            await flush();
            state.selectedChannelSlug = "channel-a";
            state.selectedProjectSlug = "project-a";
            state.selectedProjectDetail = { project: { project_slug: "project-a", status: "READY", workflow_input_status: "READY", runnable: true, source_video_id: "VID1", source_video_url: "https://example.com", updated_at: "2026-07-02T00:00:00Z" } };
            state.selectedProjectWorkflow = {
              binding: { workflow_id: "wf-demo", workflow_version: "2", workflow_definition_sha256: "sha-workflow", binding_source: "PROJECT_JSON" },
              definition: {
                workflow_id: "wf-demo",
                workflow_version: "2",
                display_name: "Workflow Demo",
                execution_mode: "ASSISTED",
                prompt_set: { status: "AVAILABLE", bundle_available: true },
                steps: [{ step_id: "step-1", order: 1, display_name: "Step 1", required_model: "Gemini", input_artifact_ids: [], optional_input_artifact_ids: [], output_artifact_ids: ["artifact-a"], resulting_lifecycle_state: "ONE", constraints: [] }],
              },
              state: { current_step_id: "step-1", current_step_status: "READY", next_step_id: null, current_lifecycle_state: "INPUT_READY" },
              artifacts: [{ artifact_id: "artifact-a", display_name: "Artifact A", relative_path: "workflow/artifact_a.md", exists: false }],
            };
            state.selectedWorkflowStepId = "step-1";
            render();
            const disabledBefore = document.getElementById("projectDetailPanel").innerHTML.includes('id="pastedOutputText"') && document.getElementById("projectDetailPanel").innerHTML.includes('id="pastedOutputText" placeholder="Paste the exact AI output for the selected step here." disabled');
            document.getElementById("projectDetailPanel").listeners["input"]({ target: { id: "pastedOutputText", value: "draft one" } });
            await flush();
            const parseCallsBeforeBundle = fetchCalls.filter((call) => call.path.includes("/parse-output")).length;
            state.selectedWorkflowBundle = {
              channel_slug: "channel-a",
              project_slug: "project-a",
              step_id: "step-1",
              binding: { workflow_id: "wf-demo", workflow_version: "2", workflow_definition_sha256: "sha-workflow" },
              bundle: "Prompt bundle",
              bundle_sha256: "sha-bundle",
              bundle_character_count: "Prompt bundle".length,
              prompt_file_sha256: "prompt-sha",
              input_artifact_ids: [],
              missing_optional_inputs: [],
              required_model: "Gemini",
              output_contract: { response_mode: "SINGLE_ARTIFACT" },
              identity: { channel_slug: "channel-a", project_slug: "project-a", workflow_id: "wf-demo", workflow_version: "2", workflow_definition_sha256: "sha-workflow", step_id: "step-1", bundle_sha256: "sha-bundle" },
            };
            render();
            const disabledAfter = document.getElementById("projectDetailPanel").innerHTML.includes('id="pastedOutputText" placeholder="Paste the exact AI output for the selected step here." disabled');
            document.getElementById("projectDetailPanel").listeners["input"]({ target: { id: "pastedOutputText", value: "draft two" } });
            await flush();
            return {
              disabledBefore,
              disabledAfter,
              parseCallsBeforeBundle,
              parseCallsAfterPaste: fetchCalls.filter((call) => call.path.includes("/parse-output")).length,
              currentDraft: state.pastedOutputDraft,
            };
            """
        )
        self.assertTrue(result["disabledBefore"])
        self.assertFalse(result["disabledAfter"])
        self.assertEqual(result["parseCallsBeforeBundle"], 0)
        self.assertEqual(result["parseCallsAfterPaste"], 0)
        self.assertEqual(result["currentDraft"], "draft two")

    def test_editing_pasted_output_invalidates_previous_preview_and_stale_parse_response_is_ignored(self):
        result = run_ui_runtime_scenario(
            """
            await flush();
            state.selectedChannelSlug = "channel-a";
            state.selectedProjectSlug = "project-a";
            state.selectedProjectDetail = { project: { project_slug: "project-a", status: "READY", workflow_input_status: "READY", runnable: true, source_video_id: "VID1", source_video_url: "https://example.com", updated_at: "2026-07-02T00:00:00Z" } };
            state.selectedProjectWorkflow = {
              binding: { workflow_id: "wf-demo", workflow_version: "2", workflow_definition_sha256: "sha-workflow", binding_source: "PROJECT_JSON" },
              definition: {
                workflow_id: "wf-demo",
                workflow_version: "2",
                display_name: "Workflow Demo",
                execution_mode: "ASSISTED",
                prompt_set: { status: "AVAILABLE", bundle_available: true },
                steps: [{ step_id: "step-1", order: 1, display_name: "Step 1", required_model: "Gemini", input_artifact_ids: [], optional_input_artifact_ids: [], output_artifact_ids: ["artifact-a"], resulting_lifecycle_state: "ONE", constraints: [] }],
              },
              state: { current_step_id: "step-1", current_step_status: "READY", next_step_id: null, current_lifecycle_state: "INPUT_READY" },
              artifacts: [{ artifact_id: "artifact-a", display_name: "Artifact A", relative_path: "workflow/artifact_a.md", exists: false }],
            };
            state.selectedWorkflowStepId = "step-1";
            state.selectedWorkflowBundle = {
              channel_slug: "channel-a",
              project_slug: "project-a",
              step_id: "step-1",
              binding: { workflow_id: "wf-demo", workflow_version: "2", workflow_definition_sha256: "sha-workflow" },
              bundle: "Prompt bundle",
              bundle_sha256: "sha-bundle",
              bundle_character_count: "Prompt bundle".length,
              prompt_file_sha256: "prompt-sha",
              input_artifact_ids: [],
              missing_optional_inputs: [],
              required_model: "Gemini",
              output_contract: { response_mode: "SINGLE_ARTIFACT" },
              identity: { channel_slug: "channel-a", project_slug: "project-a", workflow_id: "wf-demo", workflow_version: "2", workflow_definition_sha256: "sha-workflow", step_id: "step-1", bundle_sha256: "sha-bundle" },
            };
            state.pastedOutputDraft = "first";
            state.parsedOutputResult = {
              identity: { channel_slug: "channel-a", project_slug: "project-a", workflow_id: "wf-demo", workflow_version: "2", workflow_definition_sha256: "sha-workflow", step_id: "step-1", bundle_sha256: "sha-bundle" },
              raw_output: { sha256: "sha-first", character_count: 5 },
              contract: { response_mode: "SINGLE_ARTIFACT" },
              status: "VALID",
              artifacts: [{ artifact_id: "artifact-a", display_name: "Artifact A", filename: "artifact_a.md", content: "first", sha256: "sha-artifact", character_count: 5, validation: { status: "VALID", errors: [], warnings: [], heading_results: [] } }],
              validation: { errors: [], warnings: [] },
            };
            render();
            document.getElementById("projectDetailPanel").listeners["input"]({ target: { id: "pastedOutputText", value: "second" } });
            const deferred = makeDeferred();
            fetchHandler = async (path) => {
              if (path.endsWith("/steps/step-1/parse-output")) return await deferred.promise;
              return jsonResponse({ channels: [] });
            };
            const pending = parseOutputAction();
            state.pastedOutputDraft = "third";
            deferred.resolve(jsonResponse({
              identity: { channel_slug: "channel-a", project_slug: "project-a", workflow_id: "wf-demo", workflow_version: "2", step_id: "step-1", bundle_sha256: "sha-bundle" },
              raw_output: { sha256: "sha-second", character_count: 6 },
              contract: { response_mode: "SINGLE_ARTIFACT" },
              status: "VALID",
              artifacts: [{ artifact_id: "artifact-a", display_name: "Artifact A", filename: "artifact_a.md", content: "second", sha256: "sha-second-artifact", character_count: 6, validation: { status: "VALID", errors: [], warnings: [], heading_results: [] } }],
              validation: { errors: [], warnings: [] },
            }));
            await pending;
            await flush();
            return {
              previewClearedAfterEdit: state.parsedOutputResult === null,
              finalParsedOutput: state.parsedOutputResult,
              currentDraft: state.pastedOutputDraft,
            };
            """
        )
        self.assertTrue(result["previewClearedAfterEdit"])
        self.assertIsNone(result["finalParsedOutput"])
        self.assertEqual(result["currentDraft"], "third")

    def test_parse_failure_retains_current_raw_output(self):
        result = run_ui_runtime_scenario(
            """
            await flush();
            state.selectedChannelSlug = "channel-a";
            state.selectedProjectSlug = "project-a";
            state.selectedProjectDetail = { project: { project_slug: "project-a", status: "READY", workflow_input_status: "READY", runnable: true, source_video_id: "VID1", source_video_url: "https://example.com", updated_at: "2026-07-02T00:00:00Z" } };
            state.selectedProjectWorkflow = {
              binding: { workflow_id: "wf-demo", workflow_version: "2", workflow_definition_sha256: "sha-workflow", binding_source: "PROJECT_JSON" },
              definition: { workflow_id: "wf-demo", workflow_version: "2", display_name: "Workflow Demo", execution_mode: "ASSISTED", prompt_set: { status: "AVAILABLE", bundle_available: true }, steps: [{ step_id: "step-1", order: 1, display_name: "Step 1", required_model: "Gemini", input_artifact_ids: [], optional_input_artifact_ids: [], output_artifact_ids: ["artifact-a"], resulting_lifecycle_state: "ONE", constraints: [] }] },
              state: { current_step_id: "step-1", current_step_status: "READY", next_step_id: null, current_lifecycle_state: "INPUT_READY" },
              artifacts: [{ artifact_id: "artifact-a", display_name: "Artifact A", relative_path: "workflow/artifact_a.md", exists: false }],
            };
            state.selectedWorkflowStepId = "step-1";
            state.selectedWorkflowBundle = {
              channel_slug: "channel-a",
              project_slug: "project-a",
              step_id: "step-1",
              binding: { workflow_id: "wf-demo", workflow_version: "2", workflow_definition_sha256: "sha-workflow" },
              bundle: "Prompt bundle",
              bundle_sha256: "sha-bundle",
              bundle_character_count: "Prompt bundle".length,
              prompt_file_sha256: "prompt-sha",
              input_artifact_ids: [],
              missing_optional_inputs: [],
              required_model: "Gemini",
              output_contract: { response_mode: "SINGLE_ARTIFACT" },
              identity: { channel_slug: "channel-a", project_slug: "project-a", workflow_id: "wf-demo", workflow_version: "2", workflow_definition_sha256: "sha-workflow", step_id: "step-1", bundle_sha256: "sha-bundle" },
            };
            state.pastedOutputDraft = "still here";
            fetchHandler = async (path) => {
              if (path.endsWith("/parse-output")) return errorResponse("PROMPT_OUTPUT_PARSE_FAILED", "Bad output", 409);
              return jsonResponse({ channels: [] });
            };
            render();
            await parseOutputAction();
            await flush();
            return {
              draft: state.pastedOutputDraft,
              parseError: state.parsedOutputError,
              parsedResult: state.parsedOutputResult,
            };
            """
        )
        self.assertEqual(result["draft"], "still here")
        self.assertIn("could not be parsed", result["parseError"].lower())
        self.assertIsNone(result["parsedResult"])

    def test_stale_workflow_response_is_ignored_after_project_change(self):
        result = run_ui_runtime_scenario(
            """
            await flush();
            state.selectedChannelSlug = "channel-a";
            state.selectedProjectSlug = "project-a";
            state.selectedProjectDetail = { project: { project_slug: "project-a", status: "READY", workflow_input_status: "READY", runnable: true, source_video_id: "VID1", source_video_url: "https://example.com", updated_at: "2026-07-02T00:00:00Z" } };
            const deferredA = makeDeferred();
            const deferredB = makeDeferred();
            fetchHandler = async (path) => {
              if (path.endsWith("/projects/project-a/workflow")) return await deferredA.promise;
              if (path.endsWith("/projects/project-b/workflow")) return await deferredB.promise;
              return jsonResponse({ channels: [] });
            };
            const requestA = loadSelectedProjectWorkflow("project-a", "channel-a");
            state.selectedProjectSlug = "project-b";
            const requestB = loadSelectedProjectWorkflow("project-b", "channel-a");
            deferredB.resolve(jsonResponse({
              channel_slug: "channel-a",
              project_slug: "project-b",
              binding: { workflow_id: "wf-b", workflow_version: "2", workflow_definition_sha256: "sha-b", binding_source: "PROJECT_JSON" },
              definition: {
                workflow_id: "wf-b",
                workflow_version: "2",
                display_name: "Workflow B",
                execution_mode: "ASSISTED",
                prompt_set: { status: "AVAILABLE", bundle_available: true },
                steps: [{ step_id: "b-step", order: 1, display_name: "B Step", required_model: "Claude", input_artifact_ids: [], optional_input_artifact_ids: [], output_artifact_ids: [], resulting_lifecycle_state: "B", constraints: [] }],
              },
              state: { current_step_id: "b-step", current_step_status: "READY", next_step_id: null, current_lifecycle_state: "INPUT_READY" },
              artifacts: [],
            }));
            await flush();
            deferredA.resolve(jsonResponse({
              channel_slug: "channel-a",
              project_slug: "project-a",
              binding: { workflow_id: "wf-a", workflow_version: "2", workflow_definition_sha256: "sha-a", binding_source: "PROJECT_JSON" },
              definition: {
                workflow_id: "wf-a",
                workflow_version: "2",
                display_name: "Workflow A",
                execution_mode: "ASSISTED",
                prompt_set: { status: "AVAILABLE", bundle_available: true },
                steps: [{ step_id: "a-step", order: 1, display_name: "A Step", required_model: "Gemini", input_artifact_ids: [], optional_input_artifact_ids: [], output_artifact_ids: [], resulting_lifecycle_state: "A", constraints: [] }],
              },
              state: { current_step_id: "a-step", current_step_status: "READY", next_step_id: null, current_lifecycle_state: "INPUT_READY" },
              artifacts: [],
            }));
            await Promise.all([requestA, requestB]);
            await flush();
            return {
              selectedProjectSlug: state.selectedProjectSlug,
              workflowId: state.selectedProjectWorkflow.binding.workflow_id,
              selectedStepId: state.selectedWorkflowStepId,
              workflowError: state.workflowError,
            };
            """
        )
        self.assertEqual(result["selectedProjectSlug"], "project-b")
        self.assertEqual(result["workflowId"], "wf-b")
        self.assertEqual(result["selectedStepId"], "b-step")
        self.assertEqual(result["workflowError"], "")

    def test_stale_bundle_response_and_copy_time_identity_guard(self):
        result = run_ui_runtime_scenario(
            """
            await flush();
            state.selectedChannelSlug = "channel-a";
            state.selectedProjectSlug = "project-a";
            state.selectedProjectDetail = { project: { project_slug: "project-a", status: "READY", workflow_input_status: "READY", runnable: true, source_video_id: "VID1", source_video_url: "https://example.com", updated_at: "2026-07-02T00:00:00Z" } };
            state.selectedProjectWorkflow = {
              binding: { workflow_id: "wf-demo", workflow_version: "2", workflow_definition_sha256: "sha-workflow", binding_source: "PROJECT_JSON" },
              definition: {
                workflow_id: "wf-demo",
                workflow_version: "2",
                display_name: "Workflow Demo",
                execution_mode: "ASSISTED",
                prompt_set: { status: "AVAILABLE", bundle_available: true },
                steps: [
                  { step_id: "step-1", order: 1, display_name: "Step 1", required_model: "Gemini", input_artifact_ids: [], optional_input_artifact_ids: [], output_artifact_ids: [], resulting_lifecycle_state: "ONE", constraints: [] },
                  { step_id: "step-2", order: 2, display_name: "Step 2", required_model: "Claude", input_artifact_ids: [], optional_input_artifact_ids: [], output_artifact_ids: [], resulting_lifecycle_state: "TWO", constraints: [] },
                ],
              },
              state: { current_step_id: "step-1", current_step_status: "READY", next_step_id: "step-2", current_lifecycle_state: "INPUT_READY" },
              artifacts: [],
            };
            state.selectedWorkflowStepId = "step-1";
            const deferred1 = makeDeferred();
            const deferred2 = makeDeferred();
            fetchHandler = async (path) => {
              if (path.endsWith("/steps/step-1/bundle")) return await deferred1.promise;
              if (path.endsWith("/steps/step-2/bundle")) return await deferred2.promise;
              return jsonResponse({ channels: [] });
            };
            const first = buildBundleAction();
            setSelectedWorkflowStepId("step-2");
            const second = buildBundleAction();
            deferred2.resolve(jsonResponse({
              channel_slug: "channel-a",
              project_slug: "project-a",
              step_id: "step-2",
              binding: { workflow_id: "wf-demo", workflow_version: "2", workflow_definition_sha256: "sha-workflow" },
              bundle: "bundle-two",
              bundle_sha256: "sha-two",
              bundle_character_count: 10,
              prompt_file_sha256: "prompt-two",
              input_artifact_ids: [],
              missing_optional_inputs: [],
              required_model: "Claude",
              output_contract: { response_mode: "TEXT_ONLY" },
            }));
            await flush();
            deferred1.resolve(jsonResponse({
              channel_slug: "channel-a",
              project_slug: "project-a",
              step_id: "step-1",
              binding: { workflow_id: "wf-demo", workflow_version: "2", workflow_definition_sha256: "sha-workflow" },
              bundle: "bundle-one",
              bundle_sha256: "sha-one",
              bundle_character_count: 10,
              prompt_file_sha256: "prompt-one",
              input_artifact_ids: [],
              missing_optional_inputs: [],
              required_model: "Gemini",
              output_contract: { response_mode: "TEXT_ONLY" },
            }));
            await Promise.all([first, second]);
            await flush();
            state.selectedWorkflowBundle.identity.project_slug = "other-project";
            await copyBundleAction();
            await flush();
            return {
              finalBundle: state.selectedWorkflowBundle,
              clipboardCalls,
              bundleFeedback: state.bundleFeedback.text,
            };
            """
        )
        self.assertIsNone(result["finalBundle"])
        self.assertEqual(result["clipboardCalls"], [])
        self.assertEqual(result["bundleFeedback"], "The loaded bundle is stale. Build it again for the current selection.")

    def test_clipboard_fallback_restores_focus_and_cleans_up(self):
        result = run_ui_runtime_scenario(
            """
            await flush();
            const previouslyFocused = document.getElementById("saveTranscriptBtn");
            previouslyFocused.focus();
            state.selectedChannelSlug = "channel-a";
            state.selectedProjectSlug = "project-a";
            state.selectedProjectDetail = { project: { project_slug: "project-a", status: "READY", workflow_input_status: "READY", runnable: true, source_video_id: "VID1", source_video_url: "https://example.com", updated_at: "2026-07-02T00:00:00Z" } };
            state.selectedProjectWorkflow = {
              binding: { workflow_id: "wf-demo", workflow_version: "2", workflow_definition_sha256: "sha-workflow", binding_source: "PROJECT_JSON" },
              definition: { workflow_id: "wf-demo", workflow_version: "2", display_name: "Workflow Demo", execution_mode: "ASSISTED", prompt_set: { status: "AVAILABLE", bundle_available: true }, steps: [{ step_id: "step-1", order: 1, display_name: "Step 1", required_model: "Gemini", input_artifact_ids: [], optional_input_artifact_ids: [], output_artifact_ids: [], resulting_lifecycle_state: "ONE", constraints: [] }] },
              state: { current_step_id: "step-1", current_step_status: "READY", next_step_id: null, current_lifecycle_state: "INPUT_READY" },
              artifacts: [],
            };
            state.selectedWorkflowStepId = "step-1";
            state.selectedWorkflowBundle = {
              channel_slug: "channel-a",
              project_slug: "project-a",
              step_id: "step-1",
              binding: { workflow_id: "wf-demo", workflow_version: "2", workflow_definition_sha256: "sha-workflow" },
              bundle: "Line 1\\nLine 2 with unicode: Xin chào\\n  trailing  ",
              bundle_sha256: "sha-bundle",
              bundle_character_count: "Line 1\\nLine 2 with unicode: Xin chào\\n  trailing  ".length,
              prompt_file_sha256: "prompt-sha",
              input_artifact_ids: [],
              missing_optional_inputs: [],
              required_model: "Gemini",
              output_contract: { response_mode: "TEXT_ONLY" },
              identity: { channel_slug: "channel-a", project_slug: "project-a", workflow_id: "wf-demo", workflow_version: "2", workflow_definition_sha256: "sha-workflow", step_id: "step-1", bundle_sha256: "sha-bundle" },
            };
            clipboardReject = new Error("denied");
            await copyBundleAction();
            await flush();
            return {
              clipboardCalls,
              execCommandCalls,
              activeElementId: document.activeElement && document.activeElement.id,
              bodyChildrenAfter: bodyChildren.length,
              feedback: state.bundleFeedback.text,
            };
            """
        )
        self.assertEqual(result["clipboardCalls"], [])
        self.assertEqual(result["execCommandCalls"], ["copy"])
        self.assertEqual(result["activeElementId"], "saveTranscriptBtn")
        self.assertEqual(result["bodyChildrenAfter"], 0)
        self.assertEqual(result["feedback"], "Copied the exact complete bundle.")

    def test_generic_workflow_rendering_v1_unavailable_and_required_input_policy(self):
        result = run_ui_runtime_scenario(
            """
            await flush();
            state.selectedChannelSlug = "channel-a";
            state.selectedProjectSlug = "project-a";
            state.selectedProjectDetail = { project: { project_slug: "project-a", status: "READY", workflow_input_status: "READY", runnable: true, source_video_id: "VID1", source_video_url: "https://example.com", updated_at: "2026-07-02T00:00:00Z" } };
            state.selectedProjectWorkflow = {
              binding: { workflow_id: "wf-three", workflow_version: "1", workflow_definition_sha256: "sha-three", binding_source: "LEGACY_SYNTHESIZED" },
              definition: {
                workflow_id: "wf-three",
                workflow_version: "1",
                display_name: "Workflow Three",
                execution_mode: "ASSISTED",
                prompt_set: { status: "MISSING", bundle_available: false },
                steps: [
                  { step_id: "alpha", order: 1, display_name: "Alpha", required_model: "Model A", input_artifact_ids: ["input_alpha"], optional_input_artifact_ids: [], output_artifact_ids: ["out_alpha"], resulting_lifecycle_state: "A", constraints: [] },
                  { step_id: "beta", order: 2, display_name: "Beta", required_model: "Model B", input_artifact_ids: [], optional_input_artifact_ids: [], output_artifact_ids: ["out_beta"], resulting_lifecycle_state: "B", constraints: [{ type: "SAME_MODEL_CONVERSATION_REQUIRED", group_id: "group-b" }] },
                  { step_id: "gamma", order: 3, display_name: "Gamma", required_model: "Model C", input_artifact_ids: [], optional_input_artifact_ids: ["opt_gamma"], output_artifact_ids: [], resulting_lifecycle_state: "C", constraints: [] },
                ],
              },
              state: { current_step_id: "missing-current", current_step_status: "BLOCKED", next_step_id: "gamma", current_lifecycle_state: "INPUT_READY", blocking_reason: "WAITING_FOR_INPUT" },
              artifacts: [
                { artifact_id: "input_alpha", display_name: "Input Alpha", relative_path: "workflow/input_alpha.md", exists: false },
                { artifact_id: "out_alpha", display_name: "Output Alpha", relative_path: "workflow/out_alpha.md", exists: false },
                { artifact_id: "out_beta", display_name: "Output Beta", relative_path: "workflow/out_beta.md", exists: false },
                { artifact_id: "opt_gamma", display_name: "Optional Gamma", relative_path: "workflow/opt_gamma.md", exists: false },
              ],
            };
            state.selectedWorkflowStepId = "alpha";
            render();
            const threeStepCount = (document.getElementById("projectDetailPanel").innerHTML.match(/data-workflow-step-id=/g) || []).length;
            const nextStepRendered = document.getElementById("projectDetailPanel").innerHTML.includes("gamma");
            const buildDisabledV1 = bundleButtonModel().disabled;
            await buildBundleAction();
            await flush();
            const bundleCallCountV1 = fetchCalls.filter((call) => call.path.includes("/workflow/steps/")).length;

            state.selectedProjectWorkflow = {
              binding: { workflow_id: "wf-eight", workflow_version: "2", workflow_definition_sha256: "sha-eight", binding_source: "PROJECT_JSON" },
              definition: {
                workflow_id: "wf-eight",
                workflow_version: "2",
                display_name: "Workflow Eight",
                execution_mode: "ASSISTED",
                prompt_set: { status: "AVAILABLE", bundle_available: true },
                steps: [
                  { step_id: "one", order: 1, display_name: "One", required_model: "X", input_artifact_ids: ["req"], optional_input_artifact_ids: [], output_artifact_ids: [], resulting_lifecycle_state: "1", constraints: [] },
                  { step_id: "two", order: 2, display_name: "Two", required_model: "Y", input_artifact_ids: [], optional_input_artifact_ids: [], output_artifact_ids: [], resulting_lifecycle_state: "2", constraints: [] },
                  { step_id: "three", order: 3, display_name: "Three", required_model: "Z", input_artifact_ids: [], optional_input_artifact_ids: [], output_artifact_ids: [], resulting_lifecycle_state: "3", constraints: [] },
                  { step_id: "four", order: 4, display_name: "Four", required_model: "Q", input_artifact_ids: [], optional_input_artifact_ids: [], output_artifact_ids: [], resulting_lifecycle_state: "4", constraints: [] },
                  { step_id: "five", order: 5, display_name: "Five", required_model: "R", input_artifact_ids: [], optional_input_artifact_ids: [], output_artifact_ids: [], resulting_lifecycle_state: "5", constraints: [] },
                  { step_id: "six", order: 6, display_name: "Six", required_model: "S", input_artifact_ids: [], optional_input_artifact_ids: [], output_artifact_ids: [], resulting_lifecycle_state: "6", constraints: [] },
                  { step_id: "seven", order: 7, display_name: "Seven", required_model: "T", input_artifact_ids: [], optional_input_artifact_ids: [], output_artifact_ids: [], resulting_lifecycle_state: "7", constraints: [] },
                  { step_id: "eight", order: 8, display_name: "Eight", required_model: "U", input_artifact_ids: [], optional_input_artifact_ids: [], output_artifact_ids: [], resulting_lifecycle_state: "8", constraints: [] },
                ],
              },
              state: { current_step_id: "unknown", current_step_status: "READY", next_step_id: "three", current_lifecycle_state: "READY" },
              artifacts: [{ artifact_id: "req", display_name: "Required", relative_path: "workflow/req.md", exists: false }],
            };
            state.selectedWorkflowStepId = workflowStepList()[0] ? workflowStepList()[0].step_id : null;
            fetchHandler = async (path) => {
              if (path.endsWith("/steps/one/bundle")) return errorResponse("BUNDLE_REQUIRED_INPUT_MISSING", "Required input missing at C:\\\\secret\\\\path", 409);
              return jsonResponse({ channels: [] });
            };
            render();
            const eightStepCount = (document.getElementById("projectDetailPanel").innerHTML.match(/data-workflow-step-id=/g) || []).length;
            await buildBundleAction();
            await flush();
            return {
              threeStepCount,
              eightStepCount,
              selectedFallback: state.selectedWorkflowStepId,
              nextStepRendered,
              buildDisabledV1,
              bundleCallCountV1,
              requiredInputError: state.bundleFeedback.text,
              bundleCallsTotal: fetchCalls.filter((call) => call.path.includes("/workflow/steps/")).length,
            };
            """
        )
        self.assertEqual(result["threeStepCount"], 3)
        self.assertEqual(result["eightStepCount"], 8)
        self.assertEqual(result["selectedFallback"], "one")
        self.assertTrue(result["nextStepRendered"])
        self.assertTrue(result["buildDisabledV1"])
        self.assertEqual(result["bundleCallCountV1"], 0)
        self.assertEqual(result["requiredInputError"], "Required workflow inputs are still missing for this step.")
        self.assertEqual(result["bundleCallsTotal"], 1)

    def test_save_candidate_uses_exact_request_body_and_keeps_preview_visible(self):
        result = run_ui_runtime_scenario(
            """
            await flush();
            state.selectedChannelSlug = "channel-a";
            state.selectedProjectSlug = "project-a";
            state.selectedProjectDetail = { project: { project_slug: "project-a", status: "READY", workflow_input_status: "READY", runnable: true, source_video_id: "VID1", source_video_url: "https://example.com", updated_at: "2026-07-02T00:00:00Z" } };
            state.selectedProjectWorkflow = {
              channel_slug: "channel-a",
              project_slug: "project-a",
              binding: { workflow_id: "wf-demo", workflow_version: "2", workflow_definition_sha256: "sha-workflow", binding_source: "PROJECT_JSON" },
              definition: {
                workflow_id: "wf-demo",
                workflow_version: "2",
                display_name: "Workflow Demo",
                execution_mode: "ASSISTED",
                prompt_set: { status: "AVAILABLE", bundle_available: true },
                steps: [{ step_id: "step-1", order: 1, display_name: "Step 1", required_model: "Gemini", input_artifact_ids: [], optional_input_artifact_ids: [], output_artifact_ids: ["artifact-a"], resulting_lifecycle_state: "ONE", constraints: [] }],
              },
              state: { current_step_id: "step-1", current_step_status: "READY", next_step_id: null, current_lifecycle_state: "INPUT_READY", state_revision: 0, state_persisted: false, step_states: {} },
              available_actions: { "step-1": { save_candidate: true, approve_candidate: false, reject_candidate: false } },
              artifacts: [{ artifact_id: "artifact-a", display_name: "Artifact A", relative_path: "workflow/artifact_a.md", exists: false }],
            };
            const workflowDefinition = state.selectedProjectWorkflow.definition;
            state.selectedWorkflowStepId = "step-1";
            state.selectedWorkflowBundle = {
              channel_slug: "channel-a",
              project_slug: "project-a",
              step_id: "step-1",
              binding: { workflow_id: "wf-demo", workflow_version: "2", workflow_definition_sha256: "sha-workflow" },
              bundle: "Prompt bundle",
              bundle_sha256: "sha-bundle",
              bundle_character_count: "Prompt bundle".length,
              prompt_file_sha256: "prompt-sha",
              input_artifact_ids: [],
              missing_optional_inputs: [],
              required_model: "Gemini",
              output_contract: { response_mode: "SINGLE_ARTIFACT" },
              identity: { channel_slug: "channel-a", project_slug: "project-a", workflow_id: "wf-demo", workflow_version: "2", workflow_definition_sha256: "sha-workflow", step_id: "step-1", bundle_sha256: "sha-bundle" },
            };
            state.pastedOutputDraft = "## Subject\\nRome\\n";
            state.parsedOutputResult = {
              identity: { channel_slug: "channel-a", project_slug: "project-a", workflow_id: "wf-demo", workflow_version: "2", step_id: "step-1", bundle_sha256: "sha-bundle" },
              raw_output: { sha256: "raw-sha", character_count: state.pastedOutputDraft.length },
              contract: { response_mode: "SINGLE_ARTIFACT" },
              status: "VALID",
              artifacts: [{ artifact_id: "artifact-a", display_name: "Artifact A", filename: "artifact_a.md", content: state.pastedOutputDraft, sha256: "artifact-sha", character_count: state.pastedOutputDraft.length, validation: { status: "VALID", errors: [], warnings: [], heading_results: [] } }],
              validation: { errors: [], warnings: [] },
            };
            fetchHandler = async (path) => {
              if (path.endsWith("/workflow")) {
                return jsonResponse({
                  channel_slug: "channel-a",
                  project_slug: "project-a",
                  binding: { workflow_id: "wf-demo", workflow_version: "2", workflow_definition_sha256: "sha-workflow", binding_source: "PROJECT_JSON" },
                  definition: workflowDefinition,
                  state: { current_step_id: "step-1", current_step_status: "CANDIDATE", next_step_id: null, current_lifecycle_state: "INPUT_READY", state_revision: 1, state_persisted: true, step_states: { "step-1": { status: "CANDIDATE", candidate_group_id: "grp_000001", approved_group_id: null, candidate_idempotency_sha256: "idem", updated_at: "2026-07-02T00:00:00Z" } }, artifact_heads: { "artifact-a": { candidate_revision_id: "rev_000001", approved_revision_id: null } } },
                  available_actions: { "step-1": { save_candidate: false, approve_candidate: false, reject_candidate: false } },
                  artifacts: [{ artifact_id: "artifact-a", display_name: "Artifact A", relative_path: "workflow/artifact_a.md", exists: false }],
                });
              }
              if (path.endsWith("/revisions")) {
                return jsonResponse({
                  status: "CANDIDATE_SAVED",
                  idempotent_replay: false,
                  identity: { channel_slug: "channel-a", project_slug: "project-a", workflow_id: "wf-demo", workflow_version: "2", step_id: "step-1" },
                  state_revision: 1,
                  revision_group: {
                    revision_group_id: "grp_000001",
                    bundle_sha256: "sha-bundle",
                    raw_output_sha256: "raw-sha",
                    artifacts: [{ artifact_id: "artifact-a", revision_id: "rev_000001", content_sha256: "artifact-sha", character_count: state.pastedOutputDraft.length }],
                  },
                });
              }
              return jsonResponse({ channels: [] });
            };
            render();
            await saveCandidateAction();
            await flush();
            const saveCall = fetchCalls.find((call) => call.path.includes("/revisions"));
            return {
              savePath: saveCall && saveCall.path,
              saveBody: saveCall && saveCall.body,
              feedback: state.candidateSaveFeedback.text,
              parsePreviewValue: document.getElementById("parsedArtifactPreview0").value,
              saveDisabledAfterRefresh: document.getElementById("projectDetailPanel").innerHTML.includes('id="saveCandidateBtn" disabled'),
            };
            """
        )
        self.assertEqual(result["savePath"], "/api/v2/channels/channel-a/projects/project-a/workflow/steps/step-1/revisions")
        self.assertIn('"bundle_sha256":"sha-bundle"', result["saveBody"])
        self.assertIn('"output_text":"## Subject\\nRome\\n"', result["saveBody"])
        self.assertIn('"expected_state_revision":0', result["saveBody"])
        self.assertEqual(result["feedback"], "Candidate saved as grp_000001.")
        self.assertEqual(result["parsePreviewValue"], "## Subject\nRome\n")
        self.assertTrue(result["saveDisabledAfterRefresh"])

    def test_stale_save_candidate_response_is_ignored(self):
        result = run_ui_runtime_scenario(
            """
            await flush();
            state.selectedChannelSlug = "channel-a";
            state.selectedProjectSlug = "project-a";
            state.selectedProjectDetail = { project: { project_slug: "project-a", status: "READY", workflow_input_status: "READY", runnable: true, source_video_id: "VID1", source_video_url: "https://example.com", updated_at: "2026-07-02T00:00:00Z" } };
            state.selectedProjectWorkflow = {
              channel_slug: "channel-a",
              project_slug: "project-a",
              binding: { workflow_id: "wf-demo", workflow_version: "2", workflow_definition_sha256: "sha-workflow", binding_source: "PROJECT_JSON" },
              definition: {
                workflow_id: "wf-demo",
                workflow_version: "2",
                display_name: "Workflow Demo",
                execution_mode: "ASSISTED",
                prompt_set: { status: "AVAILABLE", bundle_available: true },
                steps: [{ step_id: "step-1", order: 1, display_name: "Step 1", required_model: "Gemini", input_artifact_ids: [], optional_input_artifact_ids: [], output_artifact_ids: ["artifact-a"], resulting_lifecycle_state: "ONE", constraints: [] }],
              },
              state: { current_step_id: "step-1", current_step_status: "READY", next_step_id: null, current_lifecycle_state: "INPUT_READY", state_revision: 0, state_persisted: false, step_states: {} },
              available_actions: { "step-1": { save_candidate: true, approve_candidate: false, reject_candidate: false } },
              artifacts: [{ artifact_id: "artifact-a", display_name: "Artifact A", relative_path: "workflow/artifact_a.md", exists: false }],
            };
            state.selectedWorkflowStepId = "step-1";
            state.selectedWorkflowBundle = {
              channel_slug: "channel-a",
              project_slug: "project-a",
              step_id: "step-1",
              binding: { workflow_id: "wf-demo", workflow_version: "2", workflow_definition_sha256: "sha-workflow" },
              bundle: "Prompt bundle",
              bundle_sha256: "sha-bundle",
              bundle_character_count: "Prompt bundle".length,
              prompt_file_sha256: "prompt-sha",
              input_artifact_ids: [],
              missing_optional_inputs: [],
              required_model: "Gemini",
              output_contract: { response_mode: "SINGLE_ARTIFACT" },
              identity: { channel_slug: "channel-a", project_slug: "project-a", workflow_id: "wf-demo", workflow_version: "2", workflow_definition_sha256: "sha-workflow", step_id: "step-1", bundle_sha256: "sha-bundle" },
            };
            state.pastedOutputDraft = "## Subject\\nRome\\n";
            state.parsedOutputResult = {
              identity: { channel_slug: "channel-a", project_slug: "project-a", workflow_id: "wf-demo", workflow_version: "2", step_id: "step-1", bundle_sha256: "sha-bundle" },
              raw_output: { sha256: "raw-sha", character_count: state.pastedOutputDraft.length },
              contract: { response_mode: "SINGLE_ARTIFACT" },
              status: "VALID",
              artifacts: [{ artifact_id: "artifact-a", display_name: "Artifact A", filename: "artifact_a.md", content: state.pastedOutputDraft, sha256: "artifact-sha", character_count: state.pastedOutputDraft.length, validation: { status: "VALID", errors: [], warnings: [], heading_results: [] } }],
              validation: { errors: [], warnings: [] },
            };
            const deferred = makeDeferred();
            fetchHandler = async (path) => {
              if (path.endsWith("/revisions")) return await deferred.promise;
              return jsonResponse({ channels: [] });
            };
            render();
            saveCandidateAction();
            await flush();
            state.pastedOutputDraft = "## Subject\\nChanged\\n";
            deferred.resolve(jsonResponse({
              status: "CANDIDATE_SAVED",
              idempotent_replay: false,
              identity: { channel_slug: "channel-a", project_slug: "project-a", workflow_id: "wf-demo", workflow_version: "2", step_id: "step-1" },
              state_revision: 1,
              revision_group: { revision_group_id: "grp_000001", bundle_sha256: "sha-bundle", raw_output_sha256: "raw-sha", artifacts: [] },
            }));
            await flush();
            await flush();
            return {
              feedback: state.candidateSaveFeedback.text,
              lastSaveCandidateResult: state.lastSaveCandidateResult,
              currentDraft: state.pastedOutputDraft,
            };
            """
        )
        self.assertEqual(result["feedback"], "")
        self.assertIsNone(result["lastSaveCandidateResult"])
        self.assertEqual(result["currentDraft"], "## Subject\nChanged\n")

    def test_approve_candidate_uses_exact_request_body_and_refreshes_workflow(self):
        result = run_ui_runtime_scenario(
            """
            await flush();
            state.selectedChannelSlug = "channel-a";
            state.selectedProjectSlug = "project-a";
            state.selectedProjectDetail = { project: { project_slug: "project-a", status: "READY", workflow_input_status: "READY", runnable: true, source_video_id: "VID1", source_video_url: "https://example.com", updated_at: "2026-07-02T00:00:00Z" } };
            state.selectedProjectWorkflow = {
              channel_slug: "channel-a",
              project_slug: "project-a",
              binding: { workflow_id: "wf-demo", workflow_version: "2", workflow_definition_sha256: "sha-workflow", binding_source: "PROJECT_JSON" },
              definition: {
                workflow_id: "wf-demo",
                workflow_version: "2",
                display_name: "Workflow Demo",
                execution_mode: "ASSISTED",
                prompt_set: { status: "AVAILABLE", bundle_available: true },
                steps: [{ step_id: "step-1", order: 1, display_name: "Step 1", required_model: "Gemini", input_artifact_ids: [], optional_input_artifact_ids: [], output_artifact_ids: ["artifact-a"], resulting_lifecycle_state: "ONE", constraints: [] }],
              },
              state: { current_step_id: "step-1", current_step_status: "CANDIDATE", next_step_id: null, current_lifecycle_state: "INPUT_READY", state_revision: 1, state_persisted: true, step_states: { "step-1": { step_id: "step-1", status: "CANDIDATE", candidate_group_id: "grp_000001", approved_group_id: null, candidate_group: { revision_group_id: "grp_000001", artifacts: [{ artifact_id: "artifact-a", revision_id: "rev_000001" }] }, approved_group: null, candidate_idempotency_sha256: "idem" } } },
              available_actions: { "step-1": { save_candidate: false, approve_candidate: true, reject_candidate: true } },
              artifacts: [{ artifact_id: "artifact-a", display_name: "Artifact A", relative_path: "workflow/artifact_a.md", exists: false }],
            };
            state.selectedWorkflowStepId = "step-1";
            state.selectedWorkflowBundle = {
              channel_slug: "channel-a",
              project_slug: "project-a",
              step_id: "step-1",
              binding: { workflow_id: "wf-demo", workflow_version: "2", workflow_definition_sha256: "sha-workflow" },
              bundle: "Prompt bundle",
              bundle_sha256: "sha-bundle",
              bundle_character_count: "Prompt bundle".length,
              prompt_file_sha256: "prompt-sha",
              input_artifact_ids: [],
              missing_optional_inputs: [],
              required_model: "Gemini",
              output_contract: { response_mode: "SINGLE_ARTIFACT" },
              identity: { channel_slug: "channel-a", project_slug: "project-a", workflow_id: "wf-demo", workflow_version: "2", workflow_definition_sha256: "sha-workflow", step_id: "step-1", bundle_sha256: "sha-bundle" },
            };
            state.pastedOutputDraft = "## Subject\\nRome\\n";
            state.parsedOutputResult = {
              identity: { channel_slug: "channel-a", project_slug: "project-a", workflow_id: "wf-demo", workflow_version: "2", step_id: "step-1", bundle_sha256: "sha-bundle" },
              raw_output: { sha256: "raw-sha", character_count: state.pastedOutputDraft.length },
              contract: { response_mode: "SINGLE_ARTIFACT" },
              status: "VALID",
              artifacts: [{ artifact_id: "artifact-a", display_name: "Artifact A", filename: "artifact_a.md", content: state.pastedOutputDraft, sha256: "artifact-sha", character_count: state.pastedOutputDraft.length, validation: { status: "VALID", errors: [], warnings: [], heading_results: [] } }],
              validation: { errors: [], warnings: [] },
            };
            const workflowDefinition = state.selectedProjectWorkflow.definition;
            let workflowFetchCount = 0;
            fetchHandler = async (path) => {
              if (path.endsWith("/candidate/approve")) {
                return jsonResponse({
                  status: "CANDIDATE_APPROVED",
                  idempotent_replay: false,
                  revision_group_id: "grp_000001",
                  state_revision: 2,
                  published_artifacts: [{ artifact_id: "artifact-a", revision_id: "rev_000001", content_sha256: "artifact-sha", character_count: 18 }],
                });
              }
              if (path.endsWith("/workflow")) {
                workflowFetchCount += 1;
                return jsonResponse({
                  channel_slug: "channel-a",
                  project_slug: "project-a",
                  binding: { workflow_id: "wf-demo", workflow_version: "2", workflow_definition_sha256: "sha-workflow", binding_source: "PROJECT_JSON" },
                  definition: workflowDefinition,
                  state: { current_step_id: "step-1", current_step_status: "APPROVED", next_step_id: null, current_lifecycle_state: "INPUT_READY", state_revision: 2, state_persisted: true, step_states: { "step-1": { step_id: "step-1", status: "APPROVED", candidate_group_id: null, approved_group_id: "grp_000001", candidate_group: null, approved_group: { revision_group_id: "grp_000001", artifacts: [{ artifact_id: "artifact-a", revision_id: "rev_000001" }] }, candidate_idempotency_sha256: null } }, artifact_heads: { "artifact-a": { candidate_revision_id: null, approved_revision_id: "rev_000001" } } },
                  available_actions: { "step-1": { save_candidate: false, approve_candidate: false, reject_candidate: false } },
                  artifacts: [{ artifact_id: "artifact-a", display_name: "Artifact A", relative_path: "workflow/artifact_a.md", exists: true }],
                });
              }
              return jsonResponse({ channels: [] });
            };
            render();
            await candidateDecisionAction("APPROVE");
            await flush();
            const approveCall = fetchCalls.find((call) => call.path.includes("/candidate/approve"));
            return {
              approvePath: approveCall && approveCall.path,
              approveBody: approveCall && approveCall.body,
              feedback: state.candidateSaveFeedback.text,
              workflowFetchCount,
              bundlePresentAfterApprove: !!state.selectedWorkflowBundle,
            };
            """
        )
        self.assertEqual(result["approvePath"], "/api/v2/channels/channel-a/projects/project-a/workflow/steps/step-1/candidate/approve")
        self.assertIn('"candidate_group_id":"grp_000001"', result["approveBody"])
        self.assertIn('"expected_state_revision":1', result["approveBody"])
        self.assertEqual(result["feedback"], "Candidate approved as grp_000001.")
        self.assertEqual(result["workflowFetchCount"], 1)
        self.assertFalse(result["bundlePresentAfterApprove"])

    def test_replacement_save_label_and_helper_are_rendered_for_approved_step(self):
        result = run_ui_runtime_scenario(
            """
            await flush();
            state.selectedChannelSlug = "channel-a";
            state.selectedProjectSlug = "project-a";
            state.selectedProjectDetail = { project: { project_slug: "project-a", status: "READY", workflow_input_status: "READY", runnable: true, source_video_id: "VID1", source_video_url: "https://example.com", updated_at: "2026-07-02T00:00:00Z" } };
            state.selectedProjectWorkflow = {
              channel_slug: "channel-a",
              project_slug: "project-a",
              binding: { workflow_id: "wf-demo", workflow_version: "2", workflow_definition_sha256: "sha-workflow", binding_source: "PROJECT_JSON" },
              definition: {
                workflow_id: "wf-demo",
                workflow_version: "2",
                display_name: "Workflow Demo",
                execution_mode: "ASSISTED",
                prompt_set: { status: "AVAILABLE", bundle_available: true },
                steps: [{ step_id: "step-1", order: 1, display_name: "Step 1", required_model: "Gemini", input_artifact_ids: [], optional_input_artifact_ids: [], output_artifact_ids: ["artifact-a"], resulting_lifecycle_state: "ONE", constraints: [] }],
              },
              state: { current_step_id: "step-1", current_step_status: "APPROVED", next_step_id: null, current_lifecycle_state: "INPUT_READY", state_revision: 2, state_persisted: true, step_states: { "step-1": { status: "APPROVED", approved_group_id: "grp_000001", candidate_group_id: null, stale_reason: null, invalidated_candidate_group_id: null, updated_at: "2026-07-02T00:00:00Z" } } },
              available_actions: { "step-1": { save_candidate: true, approve_candidate: false, reject_candidate: false } },
              artifacts: [{ artifact_id: "artifact-a", display_name: "Artifact A", relative_path: "workflow/artifact_a.md", exists: true }],
            };
            state.selectedWorkflowStepId = "step-1";
            state.selectedWorkflowBundle = {
              channel_slug: "channel-a",
              project_slug: "project-a",
              step_id: "step-1",
              binding: { workflow_id: "wf-demo", workflow_version: "2", workflow_definition_sha256: "sha-workflow" },
              bundle: "Prompt bundle",
              bundle_sha256: "sha-bundle",
              bundle_character_count: "Prompt bundle".length,
              prompt_file_sha256: "prompt-sha",
              input_artifact_ids: [],
              missing_optional_inputs: [],
              required_model: "Gemini",
              output_contract: { response_mode: "SINGLE_ARTIFACT" },
              identity: { channel_slug: "channel-a", project_slug: "project-a", workflow_id: "wf-demo", workflow_version: "2", workflow_definition_sha256: "sha-workflow", step_id: "step-1", bundle_sha256: "sha-bundle" },
            };
            state.pastedOutputDraft = "Draft";
            state.parsedOutputResult = {
              identity: { channel_slug: "channel-a", project_slug: "project-a", workflow_id: "wf-demo", workflow_version: "2", step_id: "step-1", bundle_sha256: "sha-bundle" },
              raw_output: { sha256: "raw-sha", character_count: 5 },
              contract: { response_mode: "SINGLE_ARTIFACT" },
              status: "VALID",
              artifacts: [{ artifact_id: "artifact-a", display_name: "Artifact A", filename: "artifact_a.md", content: "Draft", sha256: "artifact-sha", character_count: 5, validation: { status: "VALID", errors: [], warnings: [], heading_results: [] } }],
              validation: { errors: [], warnings: [] },
            };
            render();
            const saveModel = saveCandidateButtonModel();
            return {
              saveLabel: saveModel.label,
              saveHelper: saveModel.helper,
              panelHtml: document.getElementById("projectDetailPanel").innerHTML,
            };
            """
        )
        self.assertEqual(result["saveLabel"], "Save Replacement Candidate")
        self.assertIn("current approved stable output remains authoritative", result["saveHelper"])

    def test_replacement_candidate_controls_and_stale_badge_render_without_history_ui(self):
        result = run_ui_runtime_scenario(
            """
            await flush();
            state.selectedChannelSlug = "channel-a";
            state.selectedProjectSlug = "project-a";
            state.selectedProjectDetail = { project: { project_slug: "project-a", status: "READY", workflow_input_status: "READY", runnable: true, source_video_id: "VID1", source_video_url: "https://example.com", updated_at: "2026-07-02T00:00:00Z" } };
            state.selectedProjectWorkflow = {
              channel_slug: "channel-a",
              project_slug: "project-a",
              binding: { workflow_id: "wf-demo", workflow_version: "2", workflow_definition_sha256: "sha-workflow", binding_source: "PROJECT_JSON" },
              definition: {
                workflow_id: "wf-demo",
                workflow_version: "2",
                display_name: "Workflow Demo",
                execution_mode: "ASSISTED",
                prompt_set: { status: "AVAILABLE", bundle_available: true },
                steps: [{ step_id: "step-2", order: 2, display_name: "Step 2", required_model: "Gemini", input_artifact_ids: ["artifact-a"], optional_input_artifact_ids: [], output_artifact_ids: ["artifact-b"], resulting_lifecycle_state: "TWO", constraints: [] }],
              },
              state: { current_step_id: "step-2", current_step_status: "APPROVED", next_step_id: null, current_lifecycle_state: "INPUT_READY", state_revision: 6, state_persisted: true, step_states: { "step-2": { status: "APPROVED", approved_group_id: "grp_000001", candidate_group_id: "grp_000002", stale_reason: { upstream_artifact_ids: ["artifact-a"], caused_by_step_ids: ["step-1"], caused_by_group_ids: ["grp_000009"], caused_by_state_revision: 6, invalidated_at: "2026-07-02T00:00:00Z" }, invalidated_candidate_group_id: "grp_000002", updated_at: "2026-07-02T00:00:00Z", candidate_group: { revision_group_id: "grp_000002", artifacts: [] }, approved_group: { revision_group_id: "grp_000001", artifacts: [] } } } },
              available_actions: { "step-2": { save_candidate: false, approve_candidate: false, reject_candidate: false } },
              artifacts: [{ artifact_id: "artifact-a", display_name: "Artifact A", relative_path: "workflow/artifact_a.md", exists: true }, { artifact_id: "artifact-b", display_name: "Artifact B", relative_path: "workflow/artifact_b.md", exists: true }],
            };
            state.selectedWorkflowStepId = "step-2";
            render();
            const html = document.getElementById("projectDetailPanel").innerHTML;
            return {
              hasStaleBadge: html.includes(">STALE<"),
              hasInvalidatedNotice: html.includes("Invalidated Candidate"),
              approveDisabled: html.includes('id="approveCandidateBtn" disabled'),
              rejectDisabled: html.includes('id="rejectCandidateBtn" disabled'),
              containsHistory: html.includes("History"),
              containsRestore: html.includes("Restore"),
              containsDiff: html.includes("Diff"),
            };
            """
        )
        self.assertTrue(result["hasStaleBadge"])
        self.assertTrue(result["hasInvalidatedNotice"])
        self.assertTrue(result["approveDisabled"])
        self.assertTrue(result["rejectDisabled"])
        self.assertFalse(result["containsHistory"])
        self.assertFalse(result["containsRestore"])
        self.assertFalse(result["containsDiff"])

    def test_stale_reason_strings_render_inert_html(self):
        result = run_ui_runtime_scenario(
            """
            await flush();
            state.selectedChannelSlug = "channel-a";
            state.selectedProjectSlug = "project-a";
            state.selectedProjectDetail = { project: { project_slug: "project-a", status: "READY", workflow_input_status: "READY", runnable: true, source_video_id: "VID1", source_video_url: "https://example.com", updated_at: "2026-07-02T00:00:00Z" } };
            state.selectedProjectWorkflow = {
              channel_slug: "channel-a",
              project_slug: "project-a",
              binding: { workflow_id: "wf-demo", workflow_version: "2", workflow_definition_sha256: "sha-workflow", binding_source: "PROJECT_JSON" },
              definition: {
                workflow_id: "wf-demo",
                workflow_version: "2",
                display_name: "Workflow Demo",
                execution_mode: "ASSISTED",
                prompt_set: { status: "AVAILABLE", bundle_available: true },
                steps: [{ step_id: "step-2", order: 2, display_name: "Step 2", required_model: "Gemini", input_artifact_ids: ["artifact-a"], optional_input_artifact_ids: [], output_artifact_ids: ["artifact-b"], resulting_lifecycle_state: "TWO", constraints: [] }],
              },
              state: { current_step_id: "step-2", current_step_status: "APPROVED", next_step_id: null, current_lifecycle_state: "INPUT_READY", state_revision: 6, state_persisted: true, step_states: { "step-2": { status: "APPROVED", approved_group_id: "grp_000001", candidate_group_id: null, stale_reason: { upstream_artifact_ids: ["<img src=x onerror=1>"], caused_by_step_ids: ["step-1"], caused_by_group_ids: ["grp_000009"], caused_by_state_revision: 6, invalidated_at: "2026-07-02T00:00:00Z" }, invalidated_candidate_group_id: null, updated_at: "2026-07-02T00:00:00Z" } } },
              available_actions: { "step-2": { save_candidate: false, approve_candidate: false, reject_candidate: false } },
              artifacts: [{ artifact_id: "artifact-a", display_name: "Artifact A", relative_path: "workflow/artifact_a.md", exists: true }, { artifact_id: "artifact-b", display_name: "Artifact B", relative_path: "workflow/artifact_b.md", exists: true }],
            };
            state.selectedWorkflowStepId = "step-2";
            render();
            const html = document.getElementById("projectDetailPanel").innerHTML;
            return {
              containsRawImgTag: html.includes("<img"),
              containsEscapedString: html.includes("&lt;img src=x onerror=1&gt;"),
            };
            """
        )
        self.assertFalse(result["containsRawImgTag"])
        self.assertTrue(result["containsEscapedString"])

    def test_stale_approve_candidate_response_is_ignored(self):
        result = run_ui_runtime_scenario(
            """
            await flush();
            state.selectedChannelSlug = "channel-a";
            state.selectedProjectSlug = "project-a";
            state.selectedProjectDetail = { project: { project_slug: "project-a", status: "READY", workflow_input_status: "READY", runnable: true, source_video_id: "VID1", source_video_url: "https://example.com", updated_at: "2026-07-02T00:00:00Z" } };
            state.selectedProjectWorkflow = {
              channel_slug: "channel-a",
              project_slug: "project-a",
              binding: { workflow_id: "wf-demo", workflow_version: "2", workflow_definition_sha256: "sha-workflow", binding_source: "PROJECT_JSON" },
              definition: {
                workflow_id: "wf-demo",
                workflow_version: "2",
                display_name: "Workflow Demo",
                execution_mode: "ASSISTED",
                prompt_set: { status: "AVAILABLE", bundle_available: true },
                steps: [{ step_id: "step-1", order: 1, display_name: "Step 1", required_model: "Gemini", input_artifact_ids: [], optional_input_artifact_ids: [], output_artifact_ids: ["artifact-a"], resulting_lifecycle_state: "ONE", constraints: [] }],
              },
              state: { current_step_id: "step-1", current_step_status: "CANDIDATE", next_step_id: null, current_lifecycle_state: "INPUT_READY", state_revision: 1, state_persisted: true, step_states: { "step-1": { step_id: "step-1", status: "CANDIDATE", candidate_group_id: "grp_000001", approved_group_id: null, candidate_group: { revision_group_id: "grp_000001", artifacts: [] }, approved_group: null, candidate_idempotency_sha256: "idem" } } },
              available_actions: { "step-1": { save_candidate: false, approve_candidate: true, reject_candidate: true } },
              artifacts: [{ artifact_id: "artifact-a", display_name: "Artifact A", relative_path: "workflow/artifact_a.md", exists: false }],
            };
            state.selectedWorkflowStepId = "step-1";
            const deferred = makeDeferred();
            fetchHandler = async (path) => {
              if (path.endsWith("/candidate/approve")) return await deferred.promise;
              return jsonResponse({ channels: [] });
            };
            render();
            candidateDecisionAction("APPROVE");
            await flush();
            state.selectedWorkflowStepId = null;
            deferred.resolve(jsonResponse({
              status: "CANDIDATE_APPROVED",
              idempotent_replay: false,
              revision_group_id: "grp_000001",
              state_revision: 2,
              published_artifacts: [],
            }));
            await flush();
            await flush();
            return {
              feedback: state.candidateSaveFeedback.text,
              selectedWorkflowStepId: state.selectedWorkflowStepId,
            };
            """
        )
        self.assertEqual(result["feedback"], "")
        self.assertIsNone(result["selectedWorkflowStepId"])


if __name__ == "__main__":
    unittest.main()
