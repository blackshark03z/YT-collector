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
    this.className = "";
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
  closest(selector) {{
    if (selector === `#${{this.id}}`) return this;
    if (selector === "[data-workspace]" && this.dataset.workspace) return this;
    if (selector === "[data-project-slug]" && this.dataset.projectSlug) return this;
    if (selector === "[data-workflow-step-id]" && this.dataset.workflowStepId) return this;
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
  "openCreateProjectBtn",
  "openChangeProjectBtn",
  "submitCreateProjectBtn",
  "cancelCreateProjectBtn",
  "createProjectUrlInput",
  "createProjectNameInput",
  "createProjectChannelDisplay",
  "createProjectWorkflowBinding",
  "projectListState",
  "projectListPanel",
  "projectCreateState",
  "projectDetailState",
  "projectTranscriptPanel",
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
  "appSelectedChannel",
  "appSelectedProject",
  "appOverallState",
  "workspaceNav",
  "navOverviewBtn",
  "navWorkflowBtn",
  "navAnalyticsBtn",
  "overviewWorkspace",
  "workflowWorkspace",
  "analyticsWorkspace",
  "analyticsPanel",
].forEach(getElement);

getElement("window").value = "28";
getElement("recent").value = "10";
getElement("navOverviewBtn").dataset.workspace = "overview";
getElement("navWorkflowBtn").dataset.workspace = "workflow";
getElement("navAnalyticsBtn").dataset.workspace = "analytics";
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


def validation_first_workflow_setup(
    *,
    validation_js: str = "state.selectedProjectValidation = null;",
    workflow_action_js: str = 'available_actions: { prompt_1_transcript_analysis: { save_candidate: false, approve_candidate: false, reject_candidate: false } },',
    workflow_step_state_js: str = 'step_states: {},',
    pasted_output: str = "Candidate output",
    parsed_output_js: str = "state.parsedOutputResult = null;",
) -> str:
    return textwrap.dedent(
        f"""
        await flush();
        state.selectedChannelSlug = "channel-a";
        state.selectedProjectSlug = "project-a";
        state.selectedProjectDetail = {{
          project: {{
            project_slug: "project-a",
            project_name: "Project A",
            status: "WAITING_FOR_TRANSCRIPT",
            workflow_input_status: "NOT_READY",
            runnable: false,
            updated_at: "2026-07-10T00:00:00Z",
          }},
        }};
        state.selectedProjectWorkflow = {{
          binding: {{ workflow_id: "wf-demo", workflow_version: "2", workflow_definition_sha256: "sha-workflow", binding_source: "PROJECT_JSON" }},
          definition: {{
            workflow_id: "wf-demo",
            workflow_version: "2",
            display_name: "Workflow Demo",
            execution_mode: "ASSISTED",
            prompt_set: {{ status: "AVAILABLE", bundle_available: true }},
            steps: [{{
              step_id: "prompt_1_transcript_analysis",
              order: 1,
              display_name: "Transcript Analysis",
              required_model: "Gemini",
              input_artifact_ids: [],
              optional_input_artifact_ids: [],
              output_artifact_ids: ["transcript_analysis"],
              resulting_lifecycle_state: "ONE",
              constraints: []
            }}],
          }},
          state: {{
            current_step_id: "prompt_1_transcript_analysis",
            current_step_status: "READY",
            next_step_id: null,
            current_lifecycle_state: "INPUT_READY",
            state_revision: 0,
            state_persisted: false,
            {workflow_step_state_js}
          }},
          {workflow_action_js}
          artifacts: [],
        }};
        state.selectedWorkflowStepId = "prompt_1_transcript_analysis";
        state.selectedProjectTranscript = {{ transcript: "Saved transcript", is_template: false, has_real_content: true }};
        state.selectedWorkflowBundle = {{
          channel_slug: "channel-a",
          project_slug: "project-a",
          step_id: "prompt_1_transcript_analysis",
          binding: {{ workflow_id: "wf-demo", workflow_version: "2", workflow_definition_sha256: "sha-workflow" }},
          bundle: "Prompt bundle text",
          bundle_sha256: "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
          bundle_character_count: 18,
          prompt_file_sha256: "BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB",
          input_artifact_ids: [],
          missing_optional_inputs: [],
          required_model: "Gemini",
          output_contract: {{ response_mode: "SINGLE_ARTIFACT" }},
          identity: {{
            channel_slug: "channel-a",
            project_slug: "project-a",
            workflow_id: "wf-demo",
            workflow_version: "2",
            workflow_definition_sha256: "sha-workflow",
            step_id: "prompt_1_transcript_analysis",
            bundle_sha256: "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
          }},
        }};
        state.pastedOutputDraft = {json.dumps(pasted_output)};
        {validation_js}
        {parsed_output_js}
        render();
        """
    )


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
                "channels/${encodeURIComponent(slug)}/analytics",
                "channels/${encodeURIComponent(slug)}/analytics/discover",
                "channels/${encodeURIComponent(slug)}/analytics/sync",
                "channels/${encodeURIComponent(slug)}/sync_metrics",
                "channels/${encodeURIComponent(slug)}/projects",
                "channels/${encodeURIComponent(channelSlug)}/projects/${encodeURIComponent(projectSlug)}",
                "channels/${encodeURIComponent(channelSlug)}/projects/${encodeURIComponent(projectSlug)}/production-package",
                "channels/${encodeURIComponent(channelSlug)}/projects/${encodeURIComponent(projectSlug)}/transcript",
                "channels/${encodeURIComponent(channelSlug)}/projects/${encodeURIComponent(projectSlug)}/workflow",
                "channels/${encodeURIComponent(channelSlug)}/projects/${encodeURIComponent(projectSlug)}/workflow/steps/${encodeURIComponent(step.step_id)}/bundle",
                "channels/${encodeURIComponent(channelSlug)}/projects/${encodeURIComponent(projectSlug)}/workflow/steps/${encodeURIComponent(step.step_id)}/parse-output",
                "channels/${encodeURIComponent(channelSlug)}/projects/${encodeURIComponent(projectSlug)}/workflow/steps/${encodeURIComponent(step.step_id)}/revisions",
                "channels/${encodeURIComponent(slug)}/projects/${encodeURIComponent(projectSlug)}/transcript",
                "channels/${encodeURIComponent(slug)}/projects/${encodeURIComponent(projectSlug)}/validate",
            },
        )

    def test_ui_shell_contains_primary_navigation_and_workspace_regions(self):
        for token in [
            "YT Input Collector",
            "Workspace",
            'data-workspace="overview"',
            'data-workspace="workflow"',
            'data-workspace="analytics"',
            'id="overviewWorkspace"',
            'id="workflowWorkspace"',
            'id="analyticsWorkspace"',
            'id="appSelectedChannel"',
            'id="appSelectedProject"',
            'id="appOverallState"',
        ]:
            self.assertIn(token, self.html)

    def test_workflow_and_analytics_actions_keep_supported_ids_and_routes(self):
        for token in [
            'id="workflowStepSelect"',
            'data-workflow-step-id="${escapeHtml(step.step_id)}"',
            'id="buildBundleBtn"',
            'id="copyBundleBtn"',
            'id="parseOutputBtn"',
            'id="saveCandidateBtn"',
            'id="approveCandidateBtn"',
            'id="rejectCandidateBtn"',
            'id="discoverAnalyticsBtn"',
            'id="syncAnalyticsCollectorBtn"',
            'id="downloadProductionZipLink"',
            'id="downloadAnalyticsZipLink"',
        ]:
            self.assertIn(token, self.html)

    def test_ui_uses_collapsed_technical_details_and_compact_table_markup(self):
        self.assertIn("<details>", self.html)
        self.assertIn("<summary>Technical Details</summary>", self.html)
        self.assertIn('class="compact-table"', self.html)
        self.assertIn("Recommended Next Action", self.html)
        self.assertIn('class="primary"', self.html)
        self.assertIn('class="success"', self.html)

    def test_operator_header_hides_project_slug_and_uses_friendly_status_mapping(self):
        self.assertIn('id="appSelectedChannel"', self.html)
        self.assertIn('id="appSelectedProject"', self.html)
        self.assertIn('id="appOverallState"', self.html)
        self.assertIn("function friendlyStatusLabel(value)", self.html)
        self.assertIn('PRODUCTION_READY: "Production ready"', self.html)
        self.assertIn('APPROVED: "Approved"', self.html)
        self.assertIn('PARTIAL: "Completed with missing data"', self.html)
        self.assertIn('PENDING: "Waiting for YouTube"', self.html)

    def test_sidebar_uses_compact_navigation_and_collapsed_channel_settings(self):
        self.assertIn("Channel Settings", self.html)
        self.assertIn('workspace-tab active', self.html)
        self.assertIn('button.primary', self.html)
        self.assertIn('button.secondary', self.html)
        self.assertIn('button.success', self.html)
        self.assertIn('button.danger', self.html)

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

    def test_project_selection_storage_is_channel_scoped_and_safe(self):
        self.assertIn('const SELECTED_PROJECTS_STORAGE_KEY = "yt_input_collector.selectedProjectsByChannel";', self.html)
        self.assertIn("function loadSavedProjectSelections()", self.html)
        self.assertIn("function rememberProjectSlugForChannel(channelSlug, projectSlug)", self.html)
        self.assertIn("JSON.stringify(normalized)", self.html)
        self.assertNotIn("selectedProjectsByChannelContent", self.html)

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
        self.assertIn("Choose a channel to load its canonical summary. The UI will not guess a fallback channel.", self.html)
        self.assertIn("This channel is disconnected. Read-only summary is available, but workflow actions stay unavailable.", self.html)

    def test_oauth_ui_uses_selected_slug_and_canonical_v2_route(self):
        self.assertIn("oauth/start?channel_slug=${encodeURIComponent(slug)}&mode=${encodeURIComponent(mode)}", self.html)
        self.assertIn('label: busy ? (isConnected ? "Starting reconnect..." : "Starting connection...") : (isConnected ? "Reconnect Channel" : "Connect Channel")', self.html)
        self.assertIn('mode: "reconnect"', self.html)
        self.assertNotIn('window.open("/oauth/start"', self.html)

    def test_metrics_ui_uses_selected_slug_and_canonical_post_route(self):
        self.assertIn('channels/${encodeURIComponent(slug)}/sync_metrics', self.html)

    def test_analytics_collector_ui_uses_selected_slug_routes(self):
        self.assertIn('channels/${encodeURIComponent(slug)}/analytics', self.html)
        self.assertIn('channels/${encodeURIComponent(slug)}/analytics/discover', self.html)
        self.assertIn('channels/${encodeURIComponent(slug)}/analytics/sync', self.html)
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
        self.assertIn("Change Project", self.html)
        self.assertIn("Create New Project", self.html)

    def test_workflow_panel_uses_selected_project_workflow_and_bundle_routes(self):
        self.assertIn('v2Api(`channels/${encodeURIComponent(channelSlug)}/projects/${encodeURIComponent(projectSlug)}/workflow`)', self.html)
        self.assertIn('v2Api(`channels/${encodeURIComponent(channelSlug)}/projects/${encodeURIComponent(projectSlug)}/workflow/steps/${encodeURIComponent(step.step_id)}/bundle`)', self.html)
        self.assertIn('v2Api(`channels/${encodeURIComponent(channelSlug)}/projects/${encodeURIComponent(projectSlug)}/workflow/steps/${encodeURIComponent(step.step_id)}/parse-output`, {', self.html)
        self.assertIn('v2Api(`channels/${encodeURIComponent(channelSlug)}/projects/${encodeURIComponent(projectSlug)}/workflow/steps/${encodeURIComponent(step.step_id)}/revisions`, {', self.html)
        self.assertIn("Content Workflow", self.html)
        self.assertIn("Workflow Steps", self.html)
        self.assertIn("Selected Step Detail", self.html)
        self.assertIn("Build Complete Bundle", self.html)
        self.assertIn("Copy Complete Bundle", self.html)
        self.assertIn("Parse and Preview", self.html)
        self.assertIn("Save Candidate", self.html)
        self.assertIn("Paste AI Output", self.html)
        self.assertIn("Prompt bundle unavailable for this workflow version.", self.html)

    def test_workflow_shell_places_transcript_panel_before_detail_panel(self):
        self.assertIn('id="projectTranscriptPanel"', self.html)
        self.assertLess(self.html.index('id="projectTranscriptPanel"'), self.html.index('id="projectDetailPanel"'))

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
        self.assertIn("Copy Complete Bundle uses the exact full stored bundle.", self.html)
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
        self.assertIn("Compact workflow rail", self.html)
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
        self.assertIn('Select a workflow before creating a project.', self.html)
        self.assertIn('No project workflow is available for this channel.', self.html)
        self.assertIn('Enter a supported YouTube video URL.', self.html)
        create_action = self.html[self.html.index("async function createProjectAction()"):self.html.index("async function loadSelectedProjectDetail(")]
        self.assertNotIn('workflow_definition_sha256', create_action)
        self.assertNotIn('workflow_definition_path', create_action)
        self.assertNotIn('prompt_manifest_path', create_action)
        self.assertIn("Project creation is available only when the selected channel is connected.", self.html)

    def test_workflow_selector_uses_server_owned_options_without_hidden_default(self):
        for token in [
            '<label for="createProjectWorkflowBinding">Workflow Version</label>',
            'createProjectWorkflowBinding',
            'available_workflows',
            'function channelWorkflowOptions()',
            'function createEligibleWorkflowOptions()',
            'function selectedCreateWorkflowOption()',
            'selectedCreateWorkflowValue()',
            'workflowOptionLabel(option)',
            'workflowSelect.disabled = create.workflowDisabled;',
            "return `${option.workflow_id}@@${option.workflow_version}`;",
            'return `${option.display_name || option.workflow_id} - v${option.workflow_version}`;',
            'document.getElementById("projectListPanel").addEventListener("change", (event) => {',
        ]:
            self.assertIn(token, self.html)
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
        self.assertIn("Open Learnings", self.html)
        self.assertIn("Open Project Folder", self.html)
        self.assertIn("Open Transcript File", self.html)

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
        self.assertIn("YT Input Collector", self.html)
        self.assertIn("Refresh Channels", self.html)
        self.assertIn("Operational Workspace", self.html)
        self.assertIn("Overview", self.html)
        self.assertIn("Content Workflow", self.html)
        self.assertIn("Analytics", self.html)
        self.assertIn("Channel Settings", self.html)
        self.assertIn("Change Project", self.html)
        self.assertIn("Create New Project", self.html)
        self.assertIn("Project Detail", self.html)
        self.assertIn("Selected project workflow, candidate controls, and production handoff.", self.html)


class UiFrontendRuntimeTests(unittest.TestCase):
    def test_three_primary_navigation_areas_render_without_duplicate_fetch(self):
        result = run_ui_runtime_scenario(
            """
            await flush();
            state.selectedChannelSlug = "channel-a";
            state.selectedChannelSummary = { channel: { channel_slug: "channel-a", display_name: "Channel A", status: "CONNECTED" } };
            const before = fetchCalls.length;
            setActiveWorkspace("workflow");
            setActiveWorkspace("analytics");
            setActiveWorkspace("overview");
            return {
              fetchDelta: fetchCalls.length - before,
              overviewDisplay: document.getElementById("overviewWorkspace").style.display,
              workflowDisplay: document.getElementById("workflowWorkspace").style.display,
              analyticsDisplay: document.getElementById("analyticsWorkspace").style.display,
              navHtml: document.getElementById("navOverviewBtn").className + "|" + document.getElementById("navWorkflowBtn").className + "|" + document.getElementById("navAnalyticsBtn").className,
            };
            """
        )
        self.assertEqual(result["fetchDelta"], 0)
        self.assertEqual(result["overviewDisplay"], "grid")
        self.assertEqual(result["workflowDisplay"], "none")
        self.assertEqual(result["analyticsDisplay"], "none")
        self.assertIn("workspace-tab active", result["navHtml"])

    def test_selected_navigation_has_strong_active_styling(self):
        self.assertIn(".workspace-tab.active { background:#102a43; color:#fff; border-color:#102a43;", ui_server.HTML_PAGE)

    def test_each_workspace_exposes_one_dominant_primary_action(self):
        result = run_ui_runtime_scenario(
            """
            await flush();
            state.selectedChannelSlug = "mist_of_ages";
            state.selectedChannelSummary = { channel: { channel_slug: "mist_of_ages", display_name: "Mist of Ages", status: "CONNECTED" } };
            state.selectedChannelAnalytics = { export_url: "/zip", source_results: { analytics_queries: { status: "PARTIAL" } }, report_readiness_counts: { READY: 0, PENDING: 20, ERROR: 0 }, capability_counts: { AVAILABLE: 20, ERROR: 0 }, normalized_tables: [] };
            state.selectedProjectSlug = "project-a";
            state.selectedProjectDetail = { project: { project_slug: "project-a", project_name: "Project A", status: "READY", workflow_input_status: "READY", runnable: true } };
            state.selectedProjectWorkflow = {
              binding: { workflow_id: "wf-demo", workflow_version: "2", workflow_definition_sha256: "abc123", binding_source: "PROJECT_JSON" },
              definition: { workflow_id: "wf-demo", workflow_version: "2", display_name: "Workflow Demo", execution_mode: "ASSISTED", prompt_set: { status: "AVAILABLE", bundle_available: true }, steps: [{ step_id: "prompt_1", order: 1, display_name: "Prompt One", required_model: "Gemini", input_artifact_ids: [], optional_input_artifact_ids: [], output_artifact_ids: [], resulting_lifecycle_state: "READY", constraints: [] }] },
              state: { current_step_id: "prompt_1", current_step_status: "READY", current_lifecycle_state: "INPUT_READY" },
              available_actions: { prompt_1: { save_candidate: false, approve_candidate: false, reject_candidate: false } },
              artifacts: [],
            };
            state.selectedWorkflowStepId = "prompt_1";
            render();
            return {
              overviewPrimaryCount: (document.getElementById("summaryPanel").innerHTML.match(/class="primary"/g) || []).length,
              analyticsPrimaryCount: (document.getElementById("analyticsPanel").innerHTML.match(/class="primary"/g) || []).length,
              workflowPrimaryCount: (document.getElementById("projectDetailPanel").innerHTML.match(/class="primary"|class="action-link success"/g) || []).length,
            };
            """
        )
        self.assertEqual(result["overviewPrimaryCount"], 1)
        self.assertEqual(result["analyticsPrimaryCount"], 1)
        self.assertGreaterEqual(result["workflowPrimaryCount"], 1)

    def test_overview_recommended_next_action_logic_prefers_candidate_review(self):
        result = run_ui_runtime_scenario(
            """
            await flush();
            state.selectedChannelSlug = "channel-a";
            state.selectedProjectSlug = "project-a";
            state.selectedChannelSummary = {
              channel: { channel_slug: "channel-a", display_name: "Channel A", status: "CONNECTED" },
            };
            state.selectedProjectDetail = {
              project: {
                project_slug: "project-a",
                status: "READY",
                workflow_input_status: "READY",
                runnable: true,
                updated_at: "2026-07-05T00:00:00Z",
              },
            };
            state.selectedProjectWorkflow = {
              binding: { workflow_id: "wf", workflow_version: "2", workflow_definition_sha256: "sha", binding_source: "PROJECT_JSON" },
              definition: { workflow_id: "wf", workflow_version: "2", display_name: "Workflow", execution_mode: "ASSISTED", prompt_set: { status: "AVAILABLE", bundle_available: true }, steps: [] },
              state: {
                current_step_id: "prompt_3_creative_package",
                current_step_status: "CANDIDATE",
                current_lifecycle_state: "IN_PROGRESS",
                step_states: {
                  prompt_3_creative_package: { status: "CANDIDATE", candidate_group_id: "grp_000003" },
                },
              },
            };
            render();
            return {
              summaryHtml: document.getElementById("summaryPanel").innerHTML,
              headerProject: document.getElementById("appSelectedProject").textContent,
              overallState: document.getElementById("appOverallState").textContent,
            };
            """
        )
        self.assertIn("Recommended Next Action: Review Candidate", result["summaryHtml"])
        self.assertIn("Project A", result["headerProject"])
        self.assertEqual(result["overallState"], "Candidate review needed")

    def test_workflow_workspace_renders_compact_step_rail_and_single_selected_step(self):
        result = run_ui_runtime_scenario(
            """
            await flush();
            state.activeWorkspace = "workflow";
            state.selectedChannelSlug = "channel-a";
            state.selectedProjectSlug = "project-a";
            state.selectedProjectDetail = {
              project: {
                project_slug: "project-a",
                status: "READY",
                workflow_input_status: "READY",
                runnable: true,
                source_video_url: "https://example.com",
                updated_at: "2026-07-05T00:00:00Z",
              },
            };
            state.selectedProjectWorkflow = {
              binding: { workflow_id: "wf-demo", workflow_version: "2", workflow_definition_sha256: "abc123", binding_source: "PROJECT_JSON" },
              definition: {
                workflow_id: "wf-demo",
                workflow_version: "2",
                display_name: "Workflow Demo",
                execution_mode: "ASSISTED",
                prompt_set: { status: "AVAILABLE", bundle_available: true },
                steps: [
                  { step_id: "prompt_1_transcript_analysis", order: 1, display_name: "Transcript Analysis", required_model: "Gemini", input_artifact_ids: [], optional_input_artifact_ids: [], output_artifact_ids: ["transcript_analysis"], resulting_lifecycle_state: "READY", constraints: [] },
                  { step_id: "prompt_2_historical_research", order: 2, display_name: "Historical Research", required_model: "Gemini", input_artifact_ids: ["transcript_analysis"], optional_input_artifact_ids: [], output_artifact_ids: ["research_pack"], resulting_lifecycle_state: "READY", constraints: [] },
                ],
              },
              state: {
                current_step_id: "prompt_2_historical_research",
                current_step_status: "READY",
                next_step_id: "prompt_2_historical_research",
                current_lifecycle_state: "INPUT_READY",
                step_states: {
                  prompt_1_transcript_analysis: { status: "APPROVED", approved_group_id: "grp_000001" },
                },
              },
              available_actions: {
                prompt_2_historical_research: { save_candidate: false, approve_candidate: false, reject_candidate: false },
              },
              artifacts: [
                { artifact_id: "transcript_analysis", display_name: "Transcript Analysis", relative_path: "workflow/transcript_analysis.md", exists: true },
                { artifact_id: "research_pack", display_name: "Research Pack", relative_path: "workflow/research_pack.md", exists: false },
              ],
            };
            state.selectedWorkflowStepId = "prompt_2_historical_research";
            render();
            return {
              detailHtml: document.getElementById("projectDetailPanel").innerHTML,
            };
            """
        )
        self.assertIn("Transcript Analysis", result["detailHtml"])
        self.assertIn("Historical Research", result["detailHtml"])
        self.assertIn("Prompt 1", result["detailHtml"])
        self.assertIn("Prompt 2", result["detailHtml"])
        self.assertIn("Compact workflow rail", result["detailHtml"])
        self.assertEqual(result["detailHtml"].count("Selected Step Detail"), 1)

    def test_advanced_details_are_collapsed_by_default(self):
        result = run_ui_runtime_scenario(
            """
            await flush();
            state.activeWorkspace = "workflow";
            state.selectedChannelSlug = "channel-a";
            state.selectedProjectSlug = "project-a";
            state.selectedProjectDetail = { project: { project_slug: "project-a", status: "READY", workflow_input_status: "READY", runnable: true, source_video_url: "https://example.com", updated_at: "2026-07-05T00:00:00Z" } };
            state.selectedProjectWorkflow = {
              binding: { workflow_id: "wf", workflow_version: "2", workflow_definition_sha256: "sha", binding_source: "PROJECT_JSON" },
              definition: { workflow_id: "wf", workflow_version: "2", display_name: "Workflow", execution_mode: "ASSISTED", prompt_set: { status: "AVAILABLE", bundle_available: true }, steps: [{ step_id: "prompt_1", order: 1, display_name: "Prompt One", required_model: "Gemini", input_artifact_ids: [], optional_input_artifact_ids: [], output_artifact_ids: [], resulting_lifecycle_state: "READY", constraints: [] }] },
              state: { current_step_id: "prompt_1", current_step_status: "READY", current_lifecycle_state: "INPUT_READY" },
              available_actions: { prompt_1: { save_candidate: false, approve_candidate: false, reject_candidate: false } },
              artifacts: [],
            };
            state.selectedWorkflowStepId = "prompt_1";
            state.selectedProjectValidation = { checks: { transcript_present: true } };
            render();
            return {
              detailHtml: document.getElementById("projectDetailPanel").innerHTML,
              validationHtml: document.getElementById("validationPanel").innerHTML,
            };
            """
        )
        self.assertIn("<details", result["detailHtml"])
        self.assertNotIn("<details open", result["detailHtml"])
        self.assertEqual(result["validationHtml"], "")

    def test_overview_hides_raw_codes_in_default_view_but_keeps_them_in_technical_details(self):
        result = run_ui_runtime_scenario(
            """
            await flush();
            state.selectedChannelSlug = "mist_of_ages";
            state.selectedChannelSummary = { channel: { channel_slug: "mist_of_ages", display_name: "Mist of Ages", status: "CONNECTED" } };
            state.selectedProjectSlug = "20260702_ancient-rome-in-20-minutes";
            state.selectedProjectDetail = { project: { project_slug: "20260702_ancient-rome-in-20-minutes", project_name: "Ancient Rome in 20 Minutes", status: "READY", workflow_input_status: "READY", runnable: true } };
            state.selectedProjectProductionPackage = { lifecycle: "PRODUCTION_READY", ready_for_export: true, approved_group_id: "grp_000007", state_revision: 14 };
            state.selectedChannelAnalytics = { source_results: { analytics_queries: { status: "PARTIAL" } }, report_readiness_counts: { READY: 0, PENDING: 20, ERROR: 0 } };
            state.selectedProjectWorkflow = { state: { current_step_id: "prompt_7_final_content", current_step_status: "APPROVED", state_revision: 14 } };
            render();
            const html = document.getElementById("summaryPanel").innerHTML;
            const defaultView = html.split("<details")[0];
            return { html, defaultView };
            """
        )
        self.assertNotIn("PRODUCTION_READY", result["defaultView"])
        self.assertNotIn("PARTIAL", result["defaultView"])
        self.assertNotIn("prompt_7_final_content", result["defaultView"])
        self.assertIn("Production ready", result["defaultView"])
        self.assertIn("Most analytics data is ready. One YouTube query failed temporarily, and bulk reports are still being prepared.", result["defaultView"])
        self.assertIn("Current Step ID", result["html"])

    def test_project_slug_absent_from_default_header(self):
        result = run_ui_runtime_scenario(
            """
            await flush();
            state.selectedChannelSlug = "mist_of_ages";
            state.selectedChannelSummary = { channel: { channel_slug: "mist_of_ages", display_name: "Mist of Ages", status: "CONNECTED" } };
            state.projects = [{ project_slug: "20260702_ancient-rome-in-20-minutes", status: "READY" }];
            state.selectedProjectSlug = "20260702_ancient-rome-in-20-minutes";
            state.selectedProjectDetail = { project: { project_slug: "20260702_ancient-rome-in-20-minutes", project_name: "Ancient Rome in 20 Minutes", status: "READY", workflow_input_status: "READY", runnable: true } };
            render();
            return {
              projectHeader: document.getElementById("appSelectedProject").textContent,
            };
            """
        )
        self.assertEqual(result["projectHeader"], "Ancient Rome in 20 Minutes")
        self.assertNotIn("20260702_ancient-rome-in-20-minutes", result["projectHeader"])

    def test_selected_project_survives_workspace_switching(self):
        result = run_ui_runtime_scenario(
            """
            await flush();
            state.selectedChannelSlug = "channel-a";
            state.selectedChannelSummary = { channel: { channel_slug: "channel-a", display_name: "Channel A", status: "CONNECTED" } };
            state.projects = [{ project_slug: "project-a", project_name: "Project A", status: "READY" }];
            setSelectedProjectSlug("project-a");
            await flush();
            setActiveWorkspace("analytics");
            render();
            setActiveWorkspace("workflow");
            render();
            return {
              selectedProjectSlug: state.selectedProjectSlug,
              selectedProjectText: document.getElementById("appSelectedProject").textContent,
            };
            """
        )
        self.assertEqual(result["selectedProjectSlug"], "project-a")
        self.assertEqual(result["selectedProjectText"], "Project A")

    def test_project_action_bar_renders_before_completed_handoff(self):
        result = run_ui_runtime_scenario(
            """
            await flush();
            state.activeWorkspace = "workflow";
            state.selectedChannelSlug = "channel-a";
            state.selectedChannelSummary = {
              channel: { channel_slug: "channel-a", display_name: "Channel A", status: "CONNECTED" },
              available_workflows: [{ workflow_id: "wf-alpha", workflow_version: "2", display_name: "Workflow Alpha", version_status: "ACTIVE" }],
            };
            state.selectedProjectSlug = "project-a";
            state.selectedProjectDetail = { project: { project_slug: "project-a", project_name: "Project A", status: "READY", workflow_input_status: "READY", runnable: true } };
            state.selectedProjectProductionPackage = { lifecycle: "PRODUCTION_READY", approved_group_id: "grp_000007", state_revision: 14, ready_for_export: true, download_url: "/download", artifacts: [] };
            state.selectedProjectWorkflow = {
              binding: { workflow_id: "wf-alpha", workflow_version: "2", workflow_definition_sha256: "abc123", binding_source: "PROJECT_JSON" },
              definition: { workflow_id: "wf-alpha", workflow_version: "2", display_name: "Workflow Alpha", execution_mode: "ASSISTED", prompt_set: { status: "AVAILABLE", bundle_available: true }, steps: [{ step_id: "prompt_7", order: 7, display_name: "Final", required_model: "Claude", input_artifact_ids: [], optional_input_artifact_ids: [], output_artifact_ids: [], resulting_lifecycle_state: "PRODUCTION_READY", constraints: [] }] },
              state: { current_step_id: "prompt_7", current_step_status: "APPROVED", next_step_id: null, current_lifecycle_state: "PRODUCTION_READY", state_revision: 14, step_states: { prompt_7: { status: "APPROVED", approved_group_id: "grp_000007", candidate_group_id: null } } },
              available_actions: {},
              artifacts: [],
            };
            state.selectedWorkflowStepId = "prompt_7";
            render();
            return {
              listHtml: document.getElementById("projectListPanel").innerHTML,
              summaryHtml: document.getElementById("projectDetailState").innerHTML,
              shellHeaderHidden: document.getElementById("projectDetailShellHeader").hidden,
              detailHtml: document.getElementById("projectDetailPanel").innerHTML,
            };
            """
        )
        self.assertIn('id="openCreateProjectBtn"', result["listHtml"])
        self.assertIn('id="openChangeProjectBtn"', result["listHtml"])
        self.assertEqual(result["summaryHtml"].strip(), "")
        self.assertTrue(result["shellHeaderHidden"])
        self.assertIn("Workflow completed", result["detailHtml"])

    def test_transcript_required_project_prioritizes_manual_transcript_and_hides_bundle_tools(self):
        result = run_ui_runtime_scenario(
            """
            await flush();
            state.selectedChannelSlug = "channel-a";
            state.selectedProjectSlug = "project-a";
            state.selectedProjectDetail = { project: { project_slug: "project-a", project_name: "Project A", status: "READY", workflow_input_status: "WAITING", runnable: true, source_video_url: "https://example.com" } };
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
                steps: [
                  { step_id: "prompt_1_transcript_analysis", order: 1, display_name: "Transcript Analysis", required_model: "Gemini", input_artifact_ids: [], optional_input_artifact_ids: [], output_artifact_ids: ["transcript_analysis"], resulting_lifecycle_state: "ONE", constraints: [] },
                  { step_id: "prompt_2_historical_research", order: 2, display_name: "Historical Research", required_model: "Gemini", input_artifact_ids: ["transcript_analysis"], optional_input_artifact_ids: [], output_artifact_ids: ["research_pack"], resulting_lifecycle_state: "TWO", constraints: [] },
                ],
              },
              state: { current_step_id: "prompt_1_transcript_analysis", current_step_status: "READY", next_step_id: "prompt_2_historical_research", current_lifecycle_state: "INPUT_READY", state_revision: 0, state_persisted: false, step_states: {} },
              available_actions: { prompt_1_transcript_analysis: { save_candidate: false, approve_candidate: false, reject_candidate: false } },
              artifacts: [{ artifact_id: "transcript_analysis", display_name: "Transcript Analysis", relative_path: "workflow/transcript_analysis.md", exists: false }],
            };
            state.selectedWorkflowStepId = "prompt_1_transcript_analysis";
            state.selectedProjectTranscript = { transcript: "", is_template: true, has_real_content: false };
            render();
            return {
              summaryHtml: document.getElementById("projectDetailState").innerHTML,
              shellHeaderHidden: document.getElementById("projectDetailShellHeader").hidden,
              transcriptHtml: document.getElementById("projectTranscriptPanel").innerHTML,
              detailHtml: document.getElementById("projectDetailPanel").innerHTML,
              validationHtml: document.getElementById("validationPanel").innerHTML,
            };
            """
        )
        self.assertEqual(result["summaryHtml"].strip(), "")
        self.assertTrue(result["shellHeaderHidden"])
        self.assertIn("Manual Transcript", result["transcriptHtml"])
        self.assertIn("Save Transcript", result["transcriptHtml"])
        self.assertNotIn("<details>", result["transcriptHtml"])
        self.assertIn("Workflow Steps", result["detailHtml"])
        self.assertIn("Selected Step Detail", result["detailHtml"])
        self.assertNotIn("Build Complete Bundle", result["detailHtml"])
        self.assertNotIn("Copy Complete Bundle", result["detailHtml"])
        self.assertNotIn("Bundle Preview", result["detailHtml"])
        self.assertIn("Secondary Details", result["validationHtml"])

    def test_transcript_required_project_keeps_manual_transcript_ahead_of_project_detail_summary(self):
        result = run_ui_runtime_scenario(
            """
            await flush();
            state.selectedChannelSlug = "channel-a";
            state.selectedProjectSlug = "project-a";
            state.selectedProjectDetail = { project: { project_slug: "project-a", project_name: "Project A", status: "READY", workflow_input_status: "WAITING", runnable: true } };
            state.selectedProjectWorkflow = {
              binding: { workflow_id: "wf-demo", workflow_version: "2", workflow_definition_sha256: "sha-workflow", binding_source: "PROJECT_JSON" },
              definition: {
                workflow_id: "wf-demo",
                workflow_version: "2",
                display_name: "Workflow Demo",
                execution_mode: "ASSISTED",
                prompt_set: { status: "AVAILABLE", bundle_available: true },
                steps: [{ step_id: "prompt_1_transcript_analysis", order: 1, display_name: "Transcript Analysis", required_model: "Gemini", input_artifact_ids: [], optional_input_artifact_ids: [], output_artifact_ids: ["transcript_analysis"], resulting_lifecycle_state: "ONE", constraints: [] }],
              },
              state: { current_step_id: "prompt_1_transcript_analysis", current_step_status: "READY", next_step_id: null, current_lifecycle_state: "INPUT_READY", state_revision: 0, state_persisted: false, step_states: {} },
              available_actions: { prompt_1_transcript_analysis: { save_candidate: false, approve_candidate: false, reject_candidate: false } },
              artifacts: [],
            };
            state.selectedWorkflowStepId = "prompt_1_transcript_analysis";
            state.selectedProjectTranscript = { transcript: "", is_template: true, has_real_content: false };
            render();
            return {
              projectDetailStateHtml: document.getElementById("projectDetailState").innerHTML,
            };
            """
        )
        self.assertEqual(result["projectDetailStateHtml"].strip(), "")

    def test_transcript_required_project_focuses_textarea_and_keeps_single_transcript_form(self):
        result = run_ui_runtime_scenario(
            """
            await flush();
            state.selectedChannelSlug = "channel-a";
            state.selectedProjectSlug = "project-a";
            state.selectedProjectDetail = { project: { project_slug: "project-a", project_name: "Project A", status: "READY", workflow_input_status: "WAITING", runnable: true } };
            state.selectedProjectWorkflow = {
              binding: { workflow_id: "wf-demo", workflow_version: "2", workflow_definition_sha256: "sha-workflow", binding_source: "PROJECT_JSON" },
              definition: {
                workflow_id: "wf-demo",
                workflow_version: "2",
                display_name: "Workflow Demo",
                execution_mode: "ASSISTED",
                prompt_set: { status: "AVAILABLE", bundle_available: true },
                steps: [{ step_id: "prompt_1_transcript_analysis", order: 1, display_name: "Transcript Analysis", required_model: "Gemini", input_artifact_ids: [], optional_input_artifact_ids: [], output_artifact_ids: ["transcript_analysis"], resulting_lifecycle_state: "ONE", constraints: [] }],
              },
              state: { current_step_id: "prompt_1_transcript_analysis", current_step_status: "READY", next_step_id: null, current_lifecycle_state: "INPUT_READY", state_revision: 0, state_persisted: false, step_states: {} },
              available_actions: { prompt_1_transcript_analysis: { save_candidate: false, approve_candidate: false, reject_candidate: false } },
              artifacts: [],
            };
            state.selectedWorkflowStepId = "prompt_1_transcript_analysis";
            state.selectedProjectTranscript = { transcript: "", is_template: true, has_real_content: false };
            state.transcriptFocusPendingProjectKey = "channel-a::project-a";
            render();
            await flush();
            return {
              activeElementId: document.activeElement && document.activeElement.id,
              transcriptCount: (document.getElementById("projectTranscriptPanel").innerHTML.match(/id="transcript"/g) || []).length + (document.getElementById("projectDetailPanel").innerHTML.match(/id="transcript"/g) || []).length,
            };
            """
        )
        self.assertEqual(result["activeElementId"], "transcript")
        self.assertEqual(result["transcriptCount"], 1)

    def test_switching_to_workflow_workspace_focuses_transcript_when_manual_input_is_required(self):
        result = run_ui_runtime_scenario(
            """
            await flush();
            state.activeWorkspace = "overview";
            state.selectedChannelSlug = "channel-a";
            state.selectedProjectSlug = "project-a";
            state.selectedProjectDetail = { project: { project_slug: "project-a", project_name: "Project A", status: "READY", workflow_input_status: "WAITING", runnable: true } };
            state.selectedProjectWorkflow = {
              binding: { workflow_id: "wf-demo", workflow_version: "2", workflow_definition_sha256: "sha-workflow", binding_source: "PROJECT_JSON" },
              definition: {
                workflow_id: "wf-demo",
                workflow_version: "2",
                display_name: "Workflow Demo",
                execution_mode: "ASSISTED",
                prompt_set: { status: "AVAILABLE", bundle_available: true },
                steps: [{ step_id: "prompt_1_transcript_analysis", order: 1, display_name: "Transcript Analysis", required_model: "Gemini", input_artifact_ids: [], optional_input_artifact_ids: [], output_artifact_ids: ["transcript_analysis"], resulting_lifecycle_state: "ONE", constraints: [] }],
              },
              state: { current_step_id: "prompt_1_transcript_analysis", current_step_status: "READY", next_step_id: null, current_lifecycle_state: "INPUT_READY", state_revision: 0, state_persisted: false, step_states: {} },
              available_actions: { prompt_1_transcript_analysis: { save_candidate: false, approve_candidate: false, reject_candidate: false } },
              artifacts: [],
            };
            state.selectedWorkflowStepId = "prompt_1_transcript_analysis";
            state.selectedProjectTranscript = { transcript: "", is_template: true, has_real_content: false };
            render();
            setActiveWorkspace("workflow");
            await flush();
            return {
              activeElementId: document.activeElement && document.activeElement.id,
              workspace: state.activeWorkspace,
            };
            """
        )
        self.assertEqual(result["workspace"], "workflow")
        self.assertEqual(result["activeElementId"], "transcript")

    def test_transcript_draft_survives_safe_rerender_with_line_breaks(self):
        result = run_ui_runtime_scenario(
            """
            await flush();
            state.selectedChannelSlug = "channel-a";
            state.selectedProjectSlug = "project-a";
            state.selectedProjectDetail = { project: { project_slug: "project-a", status: "READY", workflow_input_status: "WAITING", runnable: true } };
            state.selectedProjectWorkflow = {
              binding: { workflow_id: "wf-demo", workflow_version: "2", workflow_definition_sha256: "sha-workflow", binding_source: "PROJECT_JSON" },
              definition: {
                workflow_id: "wf-demo",
                workflow_version: "2",
                display_name: "Workflow Demo",
                execution_mode: "ASSISTED",
                prompt_set: { status: "AVAILABLE", bundle_available: true },
                steps: [{ step_id: "prompt_1_transcript_analysis", order: 1, display_name: "Transcript Analysis", required_model: "Gemini", input_artifact_ids: [], optional_input_artifact_ids: [], output_artifact_ids: ["transcript_analysis"], resulting_lifecycle_state: "ONE", constraints: [] }],
              },
              state: { current_step_id: "prompt_1_transcript_analysis", current_step_status: "READY", next_step_id: null, current_lifecycle_state: "INPUT_READY", state_revision: 0, state_persisted: false, step_states: {} },
              available_actions: { prompt_1_transcript_analysis: { save_candidate: false, approve_candidate: false, reject_candidate: false } },
              artifacts: [],
            };
            state.selectedWorkflowStepId = "prompt_1_transcript_analysis";
            state.selectedProjectTranscript = { transcript: "", is_template: true, has_real_content: false };
            render();
            const transcriptText = "Line one\\nLine two\\n\\nLine four";
            document.getElementById("workflowWorkspace").listeners["input"]({ target: { id: "transcript", value: transcriptText } });
            state.selectedProjectValidation = { checks: { transcript_present: false } };
            render();
            return {
              draft: state.transcriptDraft,
              savedDraft: state.transcriptDraftByProjectKey["channel-a::project-a"],
              transcriptHtml: document.getElementById("projectTranscriptPanel").innerHTML,
            };
            """
        )
        self.assertEqual(result["draft"], "Line one\nLine two\n\nLine four")
        self.assertEqual(result["savedDraft"], "Line one\nLine two\n\nLine four")
        self.assertIn("Line one", result["transcriptHtml"])

    def test_transcript_draft_is_project_scoped_and_restored_after_switch_back(self):
        result = run_ui_runtime_scenario(
            """
            await flush();
            state.selectedChannelSlug = "channel-a";
            state.projects = [
              { project_slug: "project-a", project_name: "Project A", status: "READY", workflow_input_status: "WAITING" },
              { project_slug: "project-b", project_name: "Project B", status: "READY", workflow_input_status: "WAITING" },
            ];
            const workflowPayload = {
              binding: { workflow_id: "wf-demo", workflow_version: "2", workflow_definition_sha256: "sha-workflow", binding_source: "PROJECT_JSON" },
              definition: {
                workflow_id: "wf-demo",
                workflow_version: "2",
                display_name: "Workflow Demo",
                execution_mode: "ASSISTED",
                prompt_set: { status: "AVAILABLE", bundle_available: true },
                steps: [{ step_id: "prompt_1_transcript_analysis", order: 1, display_name: "Transcript Analysis", required_model: "Gemini", input_artifact_ids: [], optional_input_artifact_ids: [], output_artifact_ids: ["transcript_analysis"], resulting_lifecycle_state: "ONE", constraints: [] }],
              },
              state: { current_step_id: "prompt_1_transcript_analysis", current_step_status: "READY", next_step_id: null, current_lifecycle_state: "INPUT_READY", state_revision: 0, state_persisted: false, step_states: {} },
              available_actions: { prompt_1_transcript_analysis: { save_candidate: false, approve_candidate: false, reject_candidate: false } },
              artifacts: [],
            };
            fetchHandler = async (path) => {
              if (path === "/api/v2/channels/channel-a/projects/project-a") return jsonResponse({ project: { project_slug: "project-a", project_name: "Project A", status: "READY", workflow_input_status: "WAITING", runnable: true } });
              if (path === "/api/v2/channels/channel-a/projects/project-b") return jsonResponse({ project: { project_slug: "project-b", project_name: "Project B", status: "READY", workflow_input_status: "WAITING", runnable: true } });
              if (path === "/api/v2/channels/channel-a/projects/project-a/workflow") return jsonResponse({ channel_slug: "channel-a", project_slug: "project-a", ...workflowPayload });
              if (path === "/api/v2/channels/channel-a/projects/project-b/workflow") return jsonResponse({ channel_slug: "channel-a", project_slug: "project-b", ...workflowPayload });
              if (path === "/api/v2/channels/channel-a/projects/project-a/transcript") return jsonResponse({ transcript: "", is_template: true, has_real_content: false });
              if (path === "/api/v2/channels/channel-a/projects/project-b/transcript") return jsonResponse({ transcript: "", is_template: true, has_real_content: false });
              return jsonResponse({ channels: [] });
            };
            setSelectedProjectSlug("project-a");
            await flush();
            await flush();
            document.getElementById("workflowWorkspace").listeners["input"]({ target: { id: "transcript", value: "draft for A" } });
            setSelectedProjectSlug("project-b");
            await flush();
            await flush();
            const projectBDraft = state.transcriptDraft;
            document.getElementById("workflowWorkspace").listeners["input"]({ target: { id: "transcript", value: "draft for B" } });
            setSelectedProjectSlug("project-a");
            await flush();
            await flush();
            return {
              restoredDraft: state.transcriptDraft,
              projectBDraft,
              draftMap: state.transcriptDraftByProjectKey,
            };
            """
        )
        self.assertEqual(result["restoredDraft"], "draft for A")
        self.assertEqual(result["projectBDraft"], "")
        self.assertEqual(result["draftMap"]["channel-a::project-a"], "draft for A")
        self.assertEqual(result["draftMap"]["channel-a::project-b"], "draft for B")

    def test_clean_new_project_does_not_render_bundle_error_before_bundle_exists(self):
        result = run_ui_runtime_scenario(
            """
            await flush();
            state.selectedChannelSlug = "channel-a";
            state.selectedProjectSlug = "project-a";
            state.selectedProjectDetail = { project: { project_slug: "project-a", status: "READY", workflow_input_status: "WAITING", runnable: true } };
            state.selectedProjectWorkflow = {
              binding: { workflow_id: "wf-demo", workflow_version: "2", workflow_definition_sha256: "sha-workflow", binding_source: "PROJECT_JSON" },
              definition: {
                workflow_id: "wf-demo",
                workflow_version: "2",
                display_name: "Workflow Demo",
                execution_mode: "ASSISTED",
                prompt_set: { status: "AVAILABLE", bundle_available: true },
                steps: [{ step_id: "prompt_1_transcript_analysis", order: 1, display_name: "Transcript Analysis", required_model: "Gemini", input_artifact_ids: [], optional_input_artifact_ids: [], output_artifact_ids: ["transcript_analysis"], resulting_lifecycle_state: "ONE", constraints: [] }],
              },
              state: { current_step_id: "prompt_1_transcript_analysis", current_step_status: "READY", next_step_id: null, current_lifecycle_state: "INPUT_READY", state_revision: 0, state_persisted: false, step_states: {} },
              available_actions: { prompt_1_transcript_analysis: { save_candidate: false, approve_candidate: false, reject_candidate: false } },
              artifacts: [],
            };
            state.selectedWorkflowStepId = "prompt_1_transcript_analysis";
            state.selectedProjectTranscript = { transcript: "", is_template: true, has_real_content: false };
            render();
            return { detailHtml: document.getElementById("projectDetailPanel").innerHTML };
            """
        )
        self.assertNotIn("Bundle Error", result["detailHtml"])
        self.assertNotIn("loaded workflow bundle metadata is inconsistent", result["detailHtml"])

    def test_validation_required_renders_before_parse_and_disables_parse(self):
        result = run_ui_runtime_scenario(
            validation_first_workflow_setup()
            + """
            return {
              detailHtml: document.getElementById("projectDetailPanel").innerHTML,
              validationPanelHtml: document.getElementById("validationPanel").innerHTML,
              parseDisabled: document.getElementById("projectDetailPanel").innerHTML.includes('id="parseOutputBtn" disabled'),
              parseHelperShown: document.getElementById("projectDetailPanel").innerHTML.includes("Run validation first."),
              outputIndex: document.getElementById("projectDetailPanel").innerHTML.indexOf("Paste AI Output"),
              validationIndex: document.getElementById("projectDetailPanel").innerHTML.indexOf('id="validateProjectBtn"'),
              parseIndex: document.getElementById("projectDetailPanel").innerHTML.indexOf('id="parseOutputBtn"'),
            };
            """
        )
        self.assertTrue(result["parseDisabled"])
        self.assertTrue(result["parseHelperShown"])
        self.assertGreater(result["validationIndex"], result["outputIndex"])
        self.assertGreater(result["parseIndex"], result["validationIndex"])
        self.assertEqual(result["validationPanelHtml"], "")

    def test_validation_pending_blocks_duplicate_requests_and_parse(self):
        result = run_ui_runtime_scenario(
            validation_first_workflow_setup(
                validation_js="""
                state.selectedProjectValidation = null;
                state.validationAction = { busy: true, slug: "channel-a", projectSlug: "project-a", requestId: 3 };
                """
            )
            + """
            return {
              validateDisabled: document.getElementById("projectDetailPanel").innerHTML.includes('id="validateProjectBtn" disabled'),
              validateLabelShown: document.getElementById("projectDetailPanel").innerHTML.includes("Validating Inputs..."),
              parseDisabled: document.getElementById("projectDetailPanel").innerHTML.includes('id="parseOutputBtn" disabled'),
              detailHtml: document.getElementById("projectDetailPanel").innerHTML,
            };
            """
        )
        self.assertTrue(result["validateDisabled"])
        self.assertTrue(result["validateLabelShown"])
        self.assertTrue(result["parseDisabled"])
        self.assertIn("Validation running", result["detailHtml"])

    def test_validation_failure_preserves_ai_output_and_keeps_parse_disabled(self):
        result = run_ui_runtime_scenario(
            validation_first_workflow_setup(
                validation_js="""
                state.selectedProjectValidation = {
                  checks: { transcript_real_content: false, workflow_directory: true },
                  project: { workflow_input_status: "NOT_READY", runnable: false }
                };
                """
            )
            + """
            return {
              pastedValue: document.getElementById("pastedOutputText").value,
              parseDisabled: document.getElementById("projectDetailPanel").innerHTML.includes('id="parseOutputBtn" disabled'),
              detailHtml: document.getElementById("projectDetailPanel").innerHTML,
            };
            """
        )
        self.assertEqual(result["pastedValue"], "Candidate output")
        self.assertTrue(result["parseDisabled"])
        self.assertIn("Validation failed", result["detailHtml"])
        self.assertIn("Transcript has real content", result["detailHtml"])

    def test_validation_pass_enables_parse_when_output_exists(self):
        result = run_ui_runtime_scenario(
            validation_first_workflow_setup(
                validation_js="""
                state.selectedProjectValidation = {
                  checks: { transcript_real_content: true, workflow_directory: true },
                  project: { workflow_input_status: "READY", runnable: true }
                };
                """
            )
            + """
            return {
              parseDisabled: document.getElementById("projectDetailPanel").innerHTML.includes('id="parseOutputBtn" disabled'),
              validateSecondary: document.getElementById("projectDetailPanel").innerHTML.includes('class="secondary" id="validateProjectBtn"'),
              parsePrimary: document.getElementById("projectDetailPanel").innerHTML.includes('class="primary" id="parseOutputBtn"'),
              detailHtml: document.getElementById("projectDetailPanel").innerHTML,
            };
            """
        )
        self.assertFalse(result["parseDisabled"])
        self.assertTrue(result["validateSecondary"])
        self.assertTrue(result["parsePrimary"])
        self.assertIn("Validation passed", result["detailHtml"])

    def test_validation_pass_still_keeps_parse_disabled_when_output_is_empty(self):
        result = run_ui_runtime_scenario(
            validation_first_workflow_setup(
                pasted_output="",
                validation_js="""
                state.selectedProjectValidation = {
                  checks: { transcript_real_content: true, workflow_directory: true },
                  project: { workflow_input_status: "READY", runnable: true }
                };
                """
            )
            + """
            return {
              parseDisabled: document.getElementById("projectDetailPanel").innerHTML.includes('id="parseOutputBtn" disabled'),
              detailHtml: document.getElementById("projectDetailPanel").innerHTML,
            };
            """
        )
        self.assertTrue(result["parseDisabled"])
        self.assertIn("Paste the AI output before parsing.", result["detailHtml"])

    def test_parse_pass_enables_save_candidate(self):
        result = run_ui_runtime_scenario(
            validation_first_workflow_setup(
                workflow_action_js='available_actions: { prompt_1_transcript_analysis: { save_candidate: true, approve_candidate: false, reject_candidate: false } },',
                validation_js="""
                state.selectedProjectValidation = {
                  checks: { transcript_real_content: true, workflow_directory: true },
                  project: { workflow_input_status: "READY", runnable: true }
                };
                """,
                parsed_output_js="""
                state.parsedOutputResult = {
                  identity: {
                    channel_slug: "channel-a",
                    project_slug: "project-a",
                    workflow_id: "wf-demo",
                    workflow_version: "2",
                    step_id: "prompt_1_transcript_analysis",
                    bundle_sha256: "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
                  },
                  raw_output: { sha256: "CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC", character_count: 16 },
                  contract: { response_mode: "SINGLE_ARTIFACT" },
                  status: "VALID",
                  artifacts: [{ artifact_id: "transcript_analysis", display_name: "Transcript Analysis", filename: "transcript_analysis.md", content: state.pastedOutputDraft, sha256: "DDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDD", character_count: 16, validation: { status: "VALID", errors: [], warnings: [], heading_results: [] } }],
                  validation: { errors: [], warnings: [] }
                };
                """
            )
            + """
            const saveButton = saveCandidateButtonModel();
            const approveButton = candidateDecisionButtonModel("APPROVE");
            const rejectButton = candidateDecisionButtonModel("REJECT");
            return {
              saveDisabled: saveButton.disabled,
              approveDisabled: approveButton.disabled,
              rejectDisabled: rejectButton.disabled,
            };
            """
        )
        self.assertFalse(result["saveDisabled"])
        self.assertTrue(result["approveDisabled"])
        self.assertTrue(result["rejectDisabled"])

    def test_saved_candidate_enables_approve_and_reject_per_workflow_semantics(self):
        result = run_ui_runtime_scenario(
            validation_first_workflow_setup(
                workflow_action_js='available_actions: { prompt_1_transcript_analysis: { save_candidate: false, approve_candidate: true, reject_candidate: true } },',
                workflow_step_state_js="""
                step_states: {
                  prompt_1_transcript_analysis: {
                    status: "CANDIDATE",
                    candidate_group_id: "grp_000001",
                    approved_group_id: null,
                    candidate_group: { revision_group_id: "grp_000001", artifacts: [] }
                  }
                },
                """,
                validation_js="""
                state.selectedProjectValidation = {
                  checks: { transcript_real_content: true, workflow_directory: true },
                  project: { workflow_input_status: "READY", runnable: true }
                };
                """
            )
            + """
            const saveButton = saveCandidateButtonModel();
            const approveButton = candidateDecisionButtonModel("APPROVE");
            const rejectButton = candidateDecisionButtonModel("REJECT");
            return {
              saveDisabled: saveButton.disabled,
              approveDisabled: approveButton.disabled,
              rejectDisabled: rejectButton.disabled,
            };
            """
        )
        self.assertTrue(result["saveDisabled"])
        self.assertFalse(result["approveDisabled"])
        self.assertFalse(result["rejectDisabled"])

    def test_only_one_validation_control_exists_and_no_duplicate_bottom_panel_is_rendered(self):
        result = run_ui_runtime_scenario(
            validation_first_workflow_setup(
                validation_js="""
                state.selectedProjectValidation = {
                  checks: { transcript_real_content: true, workflow_directory: true },
                  project: { workflow_input_status: "READY", runnable: true }
                };
                """
            )
            + """
            const detailHtml = document.getElementById("projectDetailPanel").innerHTML;
            return {
              validateButtonCount: (detailHtml.match(/id="validateProjectBtn"/g) || []).length,
              validationPanelHtml: document.getElementById("validationPanel").innerHTML,
              detailHtml,
            };
            """
        )
        self.assertEqual(result["validateButtonCount"], 1)
        self.assertEqual(result["validationPanelHtml"], "")
        self.assertNotIn("Validation not run yet", result["detailHtml"])

    def test_bundle_validation_accepts_non_bmp_code_point_count(self):
        result = run_ui_runtime_scenario(
            """
            await flush();
            const bundle = { bundle: "A🎥B", bundle_character_count: 3 };
            return {
              validationError: bundleValidationError(bundle),
              jsLength: bundle.bundle.length,
              codePointLength: unicodeCodePointCount(bundle.bundle),
            };
            """
        )
        self.assertEqual(result["validationError"], "")
        self.assertEqual(result["jsLength"], 4)
        self.assertEqual(result["codePointLength"], 3)

    def test_bundle_validation_accepts_multiple_non_bmp_code_points(self):
        result = run_ui_runtime_scenario(
            """
            await flush();
            const bundle = { bundle: "A🎥🧭B", bundle_character_count: 4 };
            return {
              validationError: bundleValidationError(bundle),
              jsLength: bundle.bundle.length,
              codePointLength: unicodeCodePointCount(bundle.bundle),
            };
            """
        )
        self.assertEqual(result["validationError"], "")
        self.assertEqual(result["jsLength"], 6)
        self.assertEqual(result["codePointLength"], 4)

    def test_bundle_validation_rejects_genuine_non_bmp_count_mismatch(self):
        result = run_ui_runtime_scenario(
            """
            await flush();
            const bundle = { bundle: "A🎥B", bundle_character_count: 4 };
            return {
              validationError: bundleValidationError(bundle),
              codePointLength: unicodeCodePointCount(bundle.bundle),
            };
            """
        )
        self.assertEqual(result["codePointLength"], 3)
        self.assertEqual(result["validationError"], "The loaded workflow bundle metadata is inconsistent.")

    def test_bundle_validation_accepts_ascii_and_bmp_counts(self):
        result = run_ui_runtime_scenario(
            """
            await flush();
            return {
              asciiError: bundleValidationError({ bundle: "Plain ASCII", bundle_character_count: 11 }),
              bmpError: bundleValidationError({ bundle: "Xin chào", bundle_character_count: 8 }),
              asciiCount: unicodeCodePointCount("Plain ASCII"),
              bmpCount: unicodeCodePointCount("Xin chào"),
            };
            """
        )
        self.assertEqual(result["asciiError"], "")
        self.assertEqual(result["bmpError"], "")
        self.assertEqual(result["asciiCount"], 11)
        self.assertEqual(result["bmpCount"], 8)

    def test_only_one_create_project_form_exists_in_dom(self):
        result = run_ui_runtime_scenario(
            """
            await flush();
            state.selectedChannelSlug = "channel-a";
            state.selectedChannelSummary = {
              channel: { channel_slug: "channel-a", display_name: "Channel A", status: "CONNECTED" },
              available_workflows: [{ workflow_id: "wf-alpha", workflow_version: "2", display_name: "Workflow Alpha", version_status: "ACTIVE" }],
            };
            openCreateProjectPanel();
            await flush();
            const html = document.getElementById("projectListPanel").innerHTML;
            return { formCount: (html.match(/id="createProjectPanel"/g) || []).length };
            """
        )
        self.assertEqual(result["formCount"], 1)

    def test_create_project_url_input_is_editable_and_focused_when_panel_opens(self):
        result = run_ui_runtime_scenario(
            """
            await flush();
            state.selectedChannelSlug = "channel-a";
            state.selectedChannelSummary = {
              channel: { channel_slug: "channel-a", display_name: "Channel A", status: "CONNECTED" },
              available_workflows: [{ workflow_id: "wf-alpha", workflow_version: "2", display_name: "Workflow Alpha", version_status: "ACTIVE" }],
            };
            openCreateProjectPanel();
            await flush();
            const input = document.getElementById("createProjectUrlInput");
            return {
              disabled: input.disabled,
              readonly: input.getAttribute("readonly"),
              activeId: document.activeElement && document.activeElement.id,
            };
            """
        )
        self.assertFalse(result["disabled"])
        self.assertIsNone(result["readonly"])
        self.assertEqual(result["activeId"], "createProjectUrlInput")

    def test_existing_selected_project_does_not_disable_create_project_url_input(self):
        result = run_ui_runtime_scenario(
            """
            await flush();
            state.selectedChannelSlug = "channel-a";
            state.selectedChannelSummary = {
              channel: { channel_slug: "channel-a", display_name: "Channel A", status: "CONNECTED" },
              available_workflows: [{ workflow_id: "wf-alpha", workflow_version: "2", display_name: "Workflow Alpha", version_status: "ACTIVE" }],
            };
            state.projects = [{ project_slug: "project-a", project_name: "Project A", status: "READY", workflow_input_status: "READY" }];
            state.selectedProjectSlug = "project-a";
            state.selectedProjectDetail = { project: { project_slug: "project-a", project_name: "Project A", status: "READY", workflow_input_status: "READY", runnable: true } };
            openCreateProjectPanel();
            await flush();
            return { disabled: document.getElementById("createProjectUrlInput").disabled };
            """
        )
        self.assertFalse(result["disabled"])

    def test_create_project_url_typing_and_validation_state_update(self):
        result = run_ui_runtime_scenario(
            """
            await flush();
            state.selectedChannelSlug = "channel-a";
            state.selectedChannelSummary = {
              channel: { channel_slug: "channel-a", display_name: "Channel A", status: "CONNECTED" },
              available_workflows: [{ workflow_id: "wf-alpha", workflow_version: "2", display_name: "Workflow Alpha", version_status: "ACTIVE" }],
            };
            openCreateProjectPanel();
            await flush();
            const input = document.getElementById("createProjectUrlInput");
            input.value = "notaurl";
            state.createProjectUrlDraft = input.value;
            render();
            const invalidHtml = document.getElementById("projectListPanel").innerHTML;
            input.value = "https://www.youtube.com/watch?v=VIDEO12345A";
            state.createProjectUrlDraft = input.value;
            render();
            return {
              invalidHtml,
              buttonDisabledAfterValid: document.getElementById("submitCreateProjectBtn").disabled,
              finalValue: document.getElementById("createProjectUrlInput").value,
            };
            """
        )
        self.assertIn("Enter a supported YouTube video URL.", result["invalidHtml"])
        self.assertFalse(result["buttonDisabledAfterValid"])
        self.assertEqual(result["finalValue"], "https://www.youtube.com/watch?v=VIDEO12345A")

    def test_supported_watch_youtu_be_and_shorts_urls_enable_create(self):
        result = run_ui_runtime_scenario(
            """
            await flush();
            state.selectedChannelSlug = "channel-a";
            state.selectedChannelSummary = {
              channel: { channel_slug: "channel-a", display_name: "Channel A", status: "CONNECTED" },
              available_workflows: [{ workflow_id: "wf-alpha", workflow_version: "2", display_name: "Workflow Alpha", version_status: "ACTIVE" }],
            };
            openCreateProjectPanel();
            await flush();
            const cases = [
              "https://www.youtube.com/watch?v=VIDEO12345A",
              "https://youtu.be/VIDEO12345A",
              "https://www.youtube.com/shorts/VIDEO12345A",
            ];
            const results = [];
            for (const value of cases) {
              state.createProjectUrlDraft = value;
              render();
              results.push({ value, disabled: document.getElementById("submitCreateProjectBtn").disabled });
            }
            return { results };
            """
        )
        self.assertEqual([item["disabled"] for item in result["results"]], [False, False, False])

    def test_cancel_create_panel_preserves_current_selected_project(self):
        result = run_ui_runtime_scenario(
            """
            await flush();
            state.selectedChannelSlug = "channel-a";
            state.selectedChannelSummary = {
              channel: { channel_slug: "channel-a", display_name: "Channel A", status: "CONNECTED" },
              available_workflows: [{ workflow_id: "wf-alpha", workflow_version: "2", display_name: "Workflow Alpha", version_status: "ACTIVE" }],
            };
            state.projects = [{ project_slug: "project-a", project_name: "Project A", status: "READY", workflow_input_status: "READY" }];
            state.selectedProjectSlug = "project-a";
            state.selectedProjectDetail = { project: { project_slug: "project-a", project_name: "Project A", status: "READY", workflow_input_status: "READY", runnable: true } };
            openCreateProjectPanel();
            await flush();
            state.createProjectUrlDraft = "https://youtu.be/VIDEO12345A";
            closeCreateProjectPanel();
            await flush();
            return {
              selectedProjectSlug: state.selectedProjectSlug,
              panelPresent: document.getElementById("projectListPanel").innerHTML.includes('id="createProjectPanel"'),
            };
            """
        )
        self.assertEqual(result["selectedProjectSlug"], "project-a")
        self.assertFalse(result["panelPresent"])

    def test_pending_create_submission_prevents_duplicate_requests(self):
        result = run_ui_runtime_scenario(
            """
            await flush();
            state.selectedChannelSlug = "channel-a";
            state.selectedChannelSummary = {
              channel: { channel_slug: "channel-a", display_name: "Channel A", status: "CONNECTED" },
              available_workflows: [{ workflow_id: "wf-alpha", workflow_version: "2", display_name: "Workflow Alpha", version_status: "ACTIVE" }],
            };
            const deferred = makeDeferred();
            fetchHandler = async (path, config) => {
              if (path === "/api/v2/channels/channel-a/projects" && (config.method || "GET") === "POST") {
                return await deferred.promise;
              }
              return jsonResponse({ projects: [] });
            };
            openCreateProjectPanel();
            await flush();
            state.createProjectUrlDraft = "https://youtu.be/VIDEO12345A";
            render();
            createProjectAction();
            await flush();
            const disabledWhileBusy = document.getElementById("submitCreateProjectBtn").disabled;
            createProjectAction();
            await flush();
            const postCalls = fetchCalls.filter((call) => call.path === "/api/v2/channels/channel-a/projects" && call.method === "POST").length;
            deferred.resolve(jsonResponse({ project: { project_slug: "project-b", channel_slug: "channel-a" } }));
            return { disabledWhileBusy, postCalls };
            """
        )
        self.assertTrue(result["disabledWhileBusy"])
        self.assertEqual(result["postCalls"], 1)

    def test_create_project_failure_preserves_url_selected_project_and_error(self):
        result = run_ui_runtime_scenario(
            """
            await flush();
            state.selectedChannelSlug = "channel-a";
            state.selectedChannelSummary = {
              channel: { channel_slug: "channel-a", display_name: "Channel A", status: "CONNECTED" },
              available_workflows: [{ workflow_id: "wf-alpha", workflow_version: "2", display_name: "Workflow Alpha", version_status: "ACTIVE" }],
            };
            state.projects = [{ project_slug: "project-a", project_name: "Project A", status: "READY", workflow_input_status: "READY" }];
            state.selectedProjectSlug = "project-a";
            fetchHandler = async (path, config) => {
              if (path === "/api/v2/channels/channel-a/projects" && (config.method || "GET") === "POST") {
                return errorResponse("INVALID_INPUT", "Could not create project.");
              }
              return jsonResponse({ projects: [{ project_slug: "project-a", project_name: "Project A", status: "READY", workflow_input_status: "READY" }] });
            };
            openCreateProjectPanel();
            await flush();
            state.createProjectUrlDraft = "https://youtu.be/VIDEO12345A";
            render();
            await createProjectAction();
            await flush();
            return {
              selectedProjectSlug: state.selectedProjectSlug,
              savedValue: document.getElementById("createProjectUrlInput").value,
              panelPresent: document.getElementById("projectListPanel").innerHTML.includes('id="createProjectPanel"'),
              feedback: document.getElementById("projectListPanel").innerHTML,
            };
            """
        )
        self.assertEqual(result["selectedProjectSlug"], "project-a")
        self.assertEqual(result["savedValue"], "https://youtu.be/VIDEO12345A")
        self.assertTrue(result["panelPresent"])
        self.assertIn("Could not create project.", result["feedback"])

    def test_selected_project_survives_channel_summary_and_project_refresh(self):
        result = run_ui_runtime_scenario(
            """
            await flush();
            fetchHandler = async (path, config) => {
              if (path === "/api/v2/channels/channel-a") {
                return jsonResponse({
                  channel: { channel_slug: "channel-a", display_name: "Channel A", status: "CONNECTED" },
                  available_workflows: [],
                });
              }
              if (path === "/api/v2/channels/channel-a/analytics") {
                return jsonResponse({ channel_slug: "channel-a", source_results: { analytics_queries: { status: "SUCCESS" } }, normalized_tables: [] });
              }
              if (path === "/api/v2/channels/channel-a/projects") {
                return jsonResponse({
                  projects: [
                    { project_slug: "project-a", project_name: "Project A", status: "READY", workflow_input_status: "READY" },
                    { project_slug: "project-b", project_name: "Project B", status: "READY", workflow_input_status: "READY" },
                  ],
                });
              }
              if (path === "/api/v2/channels/channel-a/projects/project-a") {
                return jsonResponse({ project: { project_slug: "project-a", project_name: "Project A", status: "READY", workflow_input_status: "READY", runnable: true } });
              }
              if (path === "/api/v2/channels/channel-a/projects/project-a/workflow") {
                return jsonResponse({
                  binding: { workflow_id: "wf", workflow_version: "2", workflow_definition_sha256: "sha", binding_source: "PROJECT_JSON" },
                  definition: { workflow_id: "wf", workflow_version: "2", display_name: "Workflow", execution_mode: "ASSISTED", prompt_set: { status: "AVAILABLE", bundle_available: true }, steps: [] },
                  state: { current_step_id: "prompt_7_final_content", current_step_status: "APPROVED", current_lifecycle_state: "PRODUCTION_READY", state_revision: 14 },
                  available_actions: {},
                  artifacts: [],
                });
              }
              if (path === "/api/v2/channels/channel-a/projects/project-a/production-package") {
                return jsonResponse({
                  production_package: {
                    lifecycle: "PRODUCTION_READY",
                    ready_for_export: true,
                    approved_group_id: "grp_000007",
                    state_revision: 14,
                    download_url: "/api/v2/channels/channel-a/projects/project-a/production-package/download",
                    artifacts: [],
                  },
                });
              }
              if (path === "/api/v2/channels/channel-a/projects/project-a/transcript") {
                return jsonResponse({ transcript: "saved transcript" });
              }
              return jsonResponse({ channels: [] });
            };
            state.selectedChannelSlug = "channel-a";
            state.selectedChannelSummary = { channel: { channel_slug: "channel-a", display_name: "Channel A", status: "CONNECTED" } };
            state.projects = [
              { project_slug: "project-a", project_name: "Project A", status: "READY" },
              { project_slug: "project-b", project_name: "Project B", status: "READY" },
            ];
            setSelectedProjectSlug("project-a");
            await flush();
            const beforeWrites = fetchCalls.filter((call) => call.method !== "GET").length;
            await loadSelectedChannelSummary();
            await flush();
            return {
              selectedProjectSlug: state.selectedProjectSlug,
              selectedProjectText: document.getElementById("appSelectedProject").textContent,
              nonGetCalls: fetchCalls.filter((call) => call.method !== "GET").length - beforeWrites,
            };
            """
        )
        self.assertEqual(result["selectedProjectSlug"], "project-a")
        self.assertEqual(result["selectedProjectText"], "Project A")
        self.assertEqual(result["nonGetCalls"], 0)

    def test_sole_project_is_auto_selected(self):
        result = run_ui_runtime_scenario(
            """
            await flush();
            fetchHandler = async (path) => {
              if (path === "/api/v2/channels/mist_of_ages/projects") {
                return jsonResponse({
                  projects: [
                    { project_slug: "20260702_ancient-rome-in-20-minutes", project_name: "Ancient Rome in 20 Minutes", status: "READY", workflow_input_status: "READY" },
                  ],
                });
              }
              if (path === "/api/v2/channels/mist_of_ages/projects/20260702_ancient-rome-in-20-minutes") {
                return jsonResponse({ project: { project_slug: "20260702_ancient-rome-in-20-minutes", project_name: "Ancient Rome in 20 Minutes", status: "READY", workflow_input_status: "READY", runnable: true } });
              }
              if (path === "/api/v2/channels/mist_of_ages/projects/20260702_ancient-rome-in-20-minutes/workflow") {
                return jsonResponse({
                  binding: { workflow_id: "mist_of_ages_assisted_content", workflow_version: "2", workflow_definition_sha256: "sha", binding_source: "PROJECT_JSON" },
                  definition: { workflow_id: "mist_of_ages_assisted_content", workflow_version: "2", display_name: "Mist of Ages Assisted Content", execution_mode: "ASSISTED", prompt_set: { status: "AVAILABLE", bundle_available: true }, steps: [] },
                  state: { current_step_id: "prompt_7_final_content", current_step_status: "APPROVED", current_lifecycle_state: "PRODUCTION_READY", state_revision: 14 },
                  available_actions: {},
                  artifacts: [],
                });
              }
              if (path === "/api/v2/channels/mist_of_ages/projects/20260702_ancient-rome-in-20-minutes/production-package") {
                return jsonResponse({
                  production_package: {
                    lifecycle: "PRODUCTION_READY",
                    ready_for_export: true,
                    approved_group_id: "grp_000007",
                    state_revision: 14,
                    download_url: "/api/v2/channels/mist_of_ages/projects/20260702_ancient-rome-in-20-minutes/production-package/download",
                    artifacts: [],
                  },
                });
              }
              if (path === "/api/v2/channels/mist_of_ages/projects/20260702_ancient-rome-in-20-minutes/transcript") {
                return jsonResponse({ transcript: "saved transcript" });
              }
              return jsonResponse({ channels: [] });
            };
            state.selectedChannelSlug = "mist_of_ages";
            state.selectedChannelSummary = {
              channel: { channel_slug: "mist_of_ages", display_name: "Mist of Ages", status: "CONNECTED" },
              available_workflows: [],
            };
            await loadProjectsForChannel("mist_of_ages");
            await flush();
            await flush();
            return {
              selectedProjectSlug: state.selectedProjectSlug,
              selectedProjectText: document.getElementById("appSelectedProject").textContent,
              savedProjects: localStorage.getItem("yt_input_collector.selectedProjectsByChannel"),
            };
            """
        )
        self.assertEqual(result["selectedProjectSlug"], "20260702_ancient-rome-in-20-minutes")
        self.assertEqual(result["selectedProjectText"], "Ancient Rome in 20 Minutes")
        self.assertIn('"mist_of_ages":"20260702_ancient-rome-in-20-minutes"', result["savedProjects"])

    def test_saved_project_is_restored_only_for_its_own_channel(self):
        result = run_ui_runtime_scenario(
            """
            state.channels = [
              { channel_slug: "channel-a", display_name: "Channel A", status: "CONNECTED" },
              { channel_slug: "channel-b", display_name: "Channel B", status: "CONNECTED" },
            ];
            localStorage.setItem("yt_input_collector.selectedProjectsByChannel", JSON.stringify({
              "channel-a": "project-a",
              "channel-b": "project-b"
            }));
            fetchHandler = async (path) => {
              if (path === "/api/v2/channels/channel-b") {
                return jsonResponse({
                  channel: { channel_slug: "channel-b", display_name: "Channel B", status: "CONNECTED" },
                  available_workflows: [],
                });
              }
              if (path === "/api/v2/channels/channel-b/analytics") {
                return jsonResponse({ channel_slug: "channel-b", source_results: { analytics_queries: { status: "SUCCESS" } }, normalized_tables: [] });
              }
              if (path === "/api/v2/channels/channel-b/projects") {
                return jsonResponse({ projects: [{ project_slug: "project-b", project_name: "Project B", status: "READY", workflow_input_status: "READY" }] });
              }
              if (path === "/api/v2/channels/channel-b/projects/project-b") {
                return jsonResponse({ project: { project_slug: "project-b", project_name: "Project B", status: "READY", workflow_input_status: "READY", runnable: true } });
              }
              if (path === "/api/v2/channels/channel-b/projects/project-b/workflow") {
                return jsonResponse({ binding: { workflow_id: "wf", workflow_version: "2", workflow_definition_sha256: "sha", binding_source: "PROJECT_JSON" }, definition: { workflow_id: "wf", workflow_version: "2", display_name: "Workflow", execution_mode: "ASSISTED", prompt_set: { status: "AVAILABLE", bundle_available: true }, steps: [] }, state: { current_step_id: "prompt_1", current_step_status: "READY", current_lifecycle_state: "INPUT_READY" }, available_actions: {}, artifacts: [] });
              }
              if (path === "/api/v2/channels/channel-b/projects/project-b/production-package") {
                return jsonResponse({ production_package: null });
              }
              if (path === "/api/v2/channels/channel-b/projects/project-b/transcript") {
                return jsonResponse({ transcript: "" });
              }
              return jsonResponse({ channels: [] });
            };
            refreshStatus();
            await flush();
            setSelectedChannelSlug("channel-b");
            await flush();
            await flush();
            return {
              selectedChannelSlug: state.selectedChannelSlug,
              selectedProjectSlug: state.selectedProjectSlug,
              selectedProjectText: document.getElementById("appSelectedProject").textContent,
            };
            """
        )
        self.assertEqual(result["selectedChannelSlug"], "channel-b")
        self.assertEqual(result["selectedProjectSlug"], "project-b")
        self.assertEqual(result["selectedProjectText"], "Project B")

    def test_stale_saved_project_is_cleared_safely(self):
        result = run_ui_runtime_scenario(
            """
            state.channels = [{ channel_slug: "channel-a", display_name: "Channel A", status: "CONNECTED" }];
            localStorage.setItem("yt_input_collector.selectedProjectsByChannel", JSON.stringify({ "channel-a": "missing-project" }));
            fetchHandler = async (path) => {
              if (path === "/api/v2/channels/channel-a") {
                return jsonResponse({
                  channel: { channel_slug: "channel-a", display_name: "Channel A", status: "CONNECTED" },
                  available_workflows: [],
                });
              }
              if (path === "/api/v2/channels/channel-a/analytics") {
                return jsonResponse({ channel_slug: "channel-a", source_results: { analytics_queries: { status: "SUCCESS" } }, normalized_tables: [] });
              }
              if (path === "/api/v2/channels/channel-a/projects") {
                return jsonResponse({
                  projects: [
                    { project_slug: "project-a", project_name: "Project A", status: "READY", workflow_input_status: "READY" },
                    { project_slug: "project-b", project_name: "Project B", status: "READY", workflow_input_status: "READY" },
                  ],
                });
              }
              return jsonResponse({ channels: [] });
            };
            refreshStatus();
            await flush();
            setSelectedChannelSlug("channel-a");
            await flush();
            await flush();
            return {
              selectedProjectSlug: state.selectedProjectSlug,
              savedProjects: localStorage.getItem("yt_input_collector.selectedProjectsByChannel"),
              helperHtml: document.getElementById("projectListPanel").innerHTML,
            };
            """
        )
        self.assertIsNone(result["selectedProjectSlug"])
        self.assertEqual(result["savedProjects"], None)
        self.assertIn("Change Project", result["helperHtml"])

    def test_project_restore_performs_no_write_request(self):
        result = run_ui_runtime_scenario(
            """
            localStorage.setItem("yt_input_collector.selectedChannelSlug", "channel-a");
            localStorage.setItem("yt_input_collector.selectedProjectsByChannel", JSON.stringify({ "channel-a": "project-a" }));
            fetchHandler = async (path) => {
              if (path === "/api/v2/channels") {
                return jsonResponse({ channels: [{ channel_slug: "channel-a", display_name: "Channel A", status: "CONNECTED" }] });
              }
              if (path === "/api/v2/channels/channel-a") {
                return jsonResponse({
                  channel: { channel_slug: "channel-a", display_name: "Channel A", status: "CONNECTED" },
                  available_workflows: [],
                });
              }
              if (path === "/api/v2/channels/channel-a/analytics") {
                return jsonResponse({ channel_slug: "channel-a", source_results: { analytics_queries: { status: "SUCCESS" } }, normalized_tables: [] });
              }
              if (path === "/api/v2/channels/channel-a/projects") {
                return jsonResponse({ projects: [{ project_slug: "project-a", project_name: "Project A", status: "READY", workflow_input_status: "READY" }] });
              }
              if (path === "/api/v2/channels/channel-a/projects/project-a") {
                return jsonResponse({ project: { project_slug: "project-a", project_name: "Project A", status: "READY", workflow_input_status: "READY", runnable: true } });
              }
              if (path === "/api/v2/channels/channel-a/projects/project-a/workflow") {
                return jsonResponse({ binding: { workflow_id: "wf", workflow_version: "2", workflow_definition_sha256: "sha", binding_source: "PROJECT_JSON" }, definition: { workflow_id: "wf", workflow_version: "2", display_name: "Workflow", execution_mode: "ASSISTED", prompt_set: { status: "AVAILABLE", bundle_available: true }, steps: [] }, state: { current_step_id: "prompt_1", current_step_status: "READY", current_lifecycle_state: "INPUT_READY" }, available_actions: {}, artifacts: [] });
              }
              if (path === "/api/v2/channels/channel-a/projects/project-a/production-package") {
                return jsonResponse({ production_package: null });
              }
              if (path === "/api/v2/channels/channel-a/projects/project-a/transcript") {
                return jsonResponse({ transcript: "" });
              }
              return jsonResponse({ channels: [] });
            };
            await flush();
            await flush();
            return {
              methods: fetchCalls.map((call) => call.method),
              paths: fetchCalls.map((call) => call.path),
            };
            """
        )
        self.assertTrue(result["paths"])
        self.assertEqual(set(result["methods"]), {"GET"})

    def test_header_shows_workflow_status_when_project_is_selected(self):
        result = run_ui_runtime_scenario(
            """
            await flush();
            state.selectedChannelSlug = "mist_of_ages";
            state.selectedChannelSummary = { channel: { channel_slug: "mist_of_ages", display_name: "Mist of Ages", status: "CONNECTED" } };
            state.selectedProjectSlug = "20260702_ancient-rome-in-20-minutes";
            state.selectedProjectDetail = { project: { project_slug: "20260702_ancient-rome-in-20-minutes", project_name: "Ancient Rome in 20 Minutes", status: "READY", workflow_input_status: "READY", runnable: true } };
            state.selectedProjectProductionPackage = { lifecycle: "PRODUCTION_READY", ready_for_export: true, approved_group_id: "grp_000007", state_revision: 14 };
            state.selectedProjectWorkflow = { state: { current_step_id: "prompt_7_final_content", current_step_status: "APPROVED", current_lifecycle_state: "PRODUCTION_READY", state_revision: 14 } };
            render();
            return {
              label: document.getElementById("appOverallStateLabel").textContent,
              value: document.getElementById("appOverallState").textContent,
            };
            """
        )
        self.assertEqual(result["label"], "Workflow Status")
        self.assertEqual(result["value"], "Production ready")

    def test_header_shows_analytics_status_when_no_project_is_selected(self):
        result = run_ui_runtime_scenario(
            """
            await flush();
            state.selectedChannelSlug = "mist_of_ages";
            state.selectedChannelSummary = { channel: { channel_slug: "mist_of_ages", display_name: "Mist of Ages", status: "CONNECTED" } };
            state.selectedChannelAnalytics = { source_results: { analytics_queries: { status: "PARTIAL" } }, report_readiness_counts: { READY: 0, PENDING: 20, ERROR: 0 }, normalized_tables: [] };
            render();
            return {
              label: document.getElementById("appOverallStateLabel").textContent,
              value: document.getElementById("appOverallState").textContent,
            };
            """
        )
        self.assertEqual(result["label"], "Analytics Status")
        self.assertEqual(result["value"], "Completed with missing data")

    def test_production_ready_restored_project_recommends_download_production_package(self):
        result = run_ui_runtime_scenario(
            """
            await flush();
            state.selectedChannelSlug = "mist_of_ages";
            state.selectedChannelSummary = { channel: { channel_slug: "mist_of_ages", display_name: "Mist of Ages", status: "CONNECTED" } };
            state.selectedProjectSlug = "20260702_ancient-rome-in-20-minutes";
            state.selectedProjectDetail = { project: { project_slug: "20260702_ancient-rome-in-20-minutes", project_name: "Ancient Rome in 20 Minutes", status: "READY", workflow_input_status: "READY", runnable: true } };
            state.selectedProjectProductionPackage = {
              lifecycle: "PRODUCTION_READY",
              ready_for_export: true,
              approved_group_id: "grp_000007",
              state_revision: 14,
              download_url: "/api/v2/channels/mist_of_ages/projects/20260702_ancient-rome-in-20-minutes/production-package/download",
            };
            state.selectedProjectWorkflow = { state: { current_step_id: "prompt_7_final_content", current_step_status: "APPROVED", current_lifecycle_state: "PRODUCTION_READY", state_revision: 14 } };
            render();
            return {
              summaryHtml: document.getElementById("summaryPanel").innerHTML,
            };
            """
        )
        self.assertIn("Recommended Next Action: Download Production Package", result["summaryHtml"])
        self.assertIn('id="recommendedActionBtn"', result["summaryHtml"])
        self.assertIn(">Download Production Package<", result["summaryHtml"])

    def test_workspace_intro_matches_selected_navigation(self):
        result = run_ui_runtime_scenario(
            """
            await flush();
            state.selectedChannelSlug = "channel-a";
            state.selectedChannelSummary = { channel: { channel_slug: "channel-a", display_name: "Channel A", status: "CONNECTED" } };
            setActiveWorkspace("overview");
            render();
            const overviewMessage = document.getElementById("message").textContent;
            setActiveWorkspace("workflow");
            render();
            const workflowMessage = document.getElementById("message").textContent;
            setActiveWorkspace("analytics");
            render();
            const analyticsMessage = document.getElementById("message").textContent;
            return { overviewMessage, workflowMessage, analyticsMessage };
            """
        )
        self.assertIn("Overview focuses on current status and the next supported action.", result["overviewMessage"])
        self.assertIn("Content Workflow covers creating, continuing, reviewing, and exporting content", result["workflowMessage"])
        self.assertIn("Analytics focuses on syncing, checking, and exporting channel data.", result["analyticsMessage"])

    def test_overview_copy_absent_from_content_workflow_and_analytics(self):
        result = run_ui_runtime_scenario(
            """
            await flush();
            state.selectedChannelSlug = "channel-a";
            state.selectedChannelSummary = { channel: { channel_slug: "channel-a", display_name: "Channel A", status: "CONNECTED" } };
            setActiveWorkspace("workflow");
            render();
            const workflowMessage = document.getElementById("message").textContent;
            setActiveWorkspace("analytics");
            render();
            const analyticsMessage = document.getElementById("message").textContent;
            return { workflowMessage, analyticsMessage };
            """
        )
        self.assertNotIn("Overview shows the current channel state", result["workflowMessage"])
        self.assertNotIn("Overview shows the current channel state", result["analyticsMessage"])

    def test_orphan_create_waiting_panel_absent_by_default(self):
        result = run_ui_runtime_scenario(
            """
            await flush();
            state.activeWorkspace = "workflow";
            state.selectedChannelSlug = "channel-a";
            state.selectedChannelSummary = {
              channel: { channel_slug: "channel-a", display_name: "Channel A", status: "CONNECTED" },
              available_workflows: [{ workflow_id: "wf-alpha", workflow_version: "2", display_name: "Workflow Alpha", version_status: "ACTIVE" }],
            };
            state.projects = [{ project_slug: "project-a", project_name: "Project A", status: "READY", workflow_input_status: "READY" }];
            render();
            return {
              workflowHtml: document.getElementById("workflowWorkspace").innerHTML,
              stateHtml: document.getElementById("projectListState").textContent,
            };
            """
        )
        self.assertNotIn("Create Status", result["workflowHtml"])
        self.assertNotIn("<strong>Create</strong>", result["workflowHtml"].split('id="createProjectPanel"')[0])
        self.assertNotIn("Waiting", result["stateHtml"])

    def test_create_status_appears_only_inside_expanded_create_new_project(self):
        result = run_ui_runtime_scenario(
            """
            await flush();
            state.activeWorkspace = "workflow";
            state.selectedChannelSlug = "channel-a";
            state.selectedChannelSummary = {
              channel: { channel_slug: "channel-a", display_name: "Channel A", status: "CONNECTED" },
              available_workflows: [{ workflow_id: "wf-alpha", workflow_version: "2", display_name: "Workflow Alpha", version_status: "ACTIVE" }],
            };
            render();
            const html = document.getElementById("projectListPanel").innerHTML;
            return {
              beforeCreateSummary: html.split('id="createProjectPanel"')[0],
              fullHtml: html,
            };
            """
        )
        self.assertNotIn("Create Status", result["beforeCreateSummary"])
        self.assertNotIn("<strong>Create</strong>", result["beforeCreateSummary"])
        self.assertNotIn('id="projectCreateState"', result["fullHtml"])

        opened = run_ui_runtime_scenario(
            """
            await flush();
            state.activeWorkspace = "workflow";
            state.selectedChannelSlug = "channel-a";
            state.selectedChannelSummary = {
              channel: { channel_slug: "channel-a", display_name: "Channel A", status: "CONNECTED" },
              available_workflows: [{ workflow_id: "wf-alpha", workflow_version: "2", display_name: "Workflow Alpha", version_status: "ACTIVE" }],
            };
            render();
            openCreateProjectPanel();
            await flush();
            return { html: document.getElementById("projectListPanel").innerHTML };
            """
        )
        self.assertIn('id="projectCreateState"', opened["html"])

    def test_production_ready_completion_and_handoff_render_before_project_management_controls(self):
        result = run_ui_runtime_scenario(
            """
            await flush();
            state.activeWorkspace = "workflow";
            state.selectedChannelSlug = "channel-a";
            state.selectedProjectSlug = "project-a";
            state.selectedProjectDetail = { project: { project_slug: "project-a", project_name: "Project A", status: "READY", workflow_input_status: "READY", runnable: true } };
            state.selectedProjectProductionPackage = {
              lifecycle: "PRODUCTION_READY",
              approved_group_id: "grp_000007",
              state_revision: 14,
              ready_for_export: true,
              download_url: "/api/v2/channels/channel-a/projects/project-a/production-package/download",
              artifacts: [{ filename: "content.md", character_count: 100, file_url: "/content", exists: true, matches_approved_revision_metadata: true }],
            };
            state.selectedProjectWorkflow = {
              binding: { workflow_id: "wf-demo", workflow_version: "2", workflow_definition_sha256: "abc123", binding_source: "PROJECT_JSON" },
              definition: { workflow_id: "wf-demo", workflow_version: "2", display_name: "Workflow Demo", execution_mode: "ASSISTED", prompt_set: { status: "AVAILABLE", bundle_available: true }, steps: [{ step_id: "prompt_7_final_content", order: 7, display_name: "Final Content", required_model: "Claude", input_artifact_ids: [], optional_input_artifact_ids: [], output_artifact_ids: ["content"], resulting_lifecycle_state: "PRODUCTION_READY", constraints: [] }] },
              state: { current_step_id: "prompt_7_final_content", current_step_status: "APPROVED", next_step_id: null, current_lifecycle_state: "PRODUCTION_READY", state_revision: 14, state_persisted: true, step_states: { "prompt_7_final_content": { status: "APPROVED", approved_group_id: "grp_000007", candidate_group_id: null } } },
              available_actions: { "prompt_7_final_content": { save_candidate: false, approve_candidate: false, reject_candidate: false } },
              artifacts: [],
            };
            state.selectedWorkflowStepId = "prompt_7_final_content";
            render();
            return {
              detailHtml: document.getElementById("projectDetailPanel").innerHTML,
              listHtml: document.getElementById("projectListPanel").innerHTML,
            };
            """
        )
        self.assertIn("openCreateProjectBtn", result["listHtml"])
        self.assertIn("openChangeProjectBtn", result["listHtml"])
        self.assertLess(result["listHtml"].index("openCreateProjectBtn"), result["detailHtml"].index("Workflow completed"))
        self.assertIn("content.md", result["detailHtml"])

    def test_project_management_is_collapsed_by_default(self):
        result = run_ui_runtime_scenario(
            """
            await flush();
            state.activeWorkspace = "workflow";
            state.selectedChannelSlug = "channel-a";
            state.selectedChannelSummary = {
              channel: { channel_slug: "channel-a", display_name: "Channel A", status: "CONNECTED" },
              available_workflows: [{ workflow_id: "wf-alpha", workflow_version: "2", display_name: "Workflow Alpha", version_status: "ACTIVE" }],
            };
            state.projects = [{ project_slug: "project-a", project_name: "Project A", status: "READY", workflow_input_status: "READY" }];
            render();
            return {
              html: document.getElementById("projectListPanel").innerHTML,
            };
            """
        )
        self.assertIn('id="openCreateProjectBtn"', result["html"])
        self.assertIn('id="openChangeProjectBtn"', result["html"])
        self.assertNotIn('id="createProjectPanel"', result["html"])
        self.assertNotIn('id="changeProjectPanel"', result["html"])

    def test_completed_workflow_defaults_to_completion_and_download_view(self):
        result = run_ui_runtime_scenario(
            """
            await flush();
            state.activeWorkspace = "workflow";
            state.selectedChannelSlug = "channel-a";
            state.selectedProjectSlug = "project-a";
            state.selectedProjectDetail = { project: { project_slug: "project-a", project_name: "Project A", status: "READY", workflow_input_status: "READY", runnable: true } };
            state.selectedProjectProductionPackage = {
              lifecycle: "PRODUCTION_READY",
              approved_group_id: "grp_000007",
              state_revision: 14,
              ready_for_export: true,
              download_url: "/api/v2/channels/channel-a/projects/project-a/production-package/download",
              artifacts: [{ filename: "content.md", character_count: 100, file_url: "/content", exists: true, matches_approved_revision_metadata: true }],
            };
            state.selectedProjectWorkflow = {
              binding: { workflow_id: "wf-demo", workflow_version: "2", workflow_definition_sha256: "abc123", binding_source: "PROJECT_JSON" },
              definition: { workflow_id: "wf-demo", workflow_version: "2", display_name: "Workflow Demo", execution_mode: "ASSISTED", prompt_set: { status: "AVAILABLE", bundle_available: true }, steps: [{ step_id: "prompt_7_final_content", order: 7, display_name: "Final Content", required_model: "Claude", input_artifact_ids: [], optional_input_artifact_ids: [], output_artifact_ids: ["content"], resulting_lifecycle_state: "PRODUCTION_READY", constraints: [] }] },
              state: { current_step_id: "prompt_7_final_content", current_step_status: "APPROVED", next_step_id: null, current_lifecycle_state: "PRODUCTION_READY", state_revision: 14, state_persisted: true, step_states: { "prompt_7_final_content": { status: "APPROVED", approved_group_id: "grp_000007", candidate_group_id: null } } },
              available_actions: { "prompt_7_final_content": { save_candidate: false, approve_candidate: false, reject_candidate: false } },
              artifacts: [],
            };
            state.selectedWorkflowStepId = "prompt_7_final_content";
            render();
            return { html: document.getElementById("projectDetailPanel").innerHTML };
            """
        )
        self.assertIn("Workflow completed", result["html"])
        self.assertIn("Download Production Package", result["html"])
        self.assertNotIn('id="parseOutputBtn"', result["html"])

    def test_completed_workflow_has_only_one_primary_production_download_action(self):
        result = run_ui_runtime_scenario(
            """
            await flush();
            state.activeWorkspace = "workflow";
            state.selectedChannelSlug = "channel-a";
            state.selectedProjectSlug = "project-a";
            state.selectedProjectDetail = { project: { project_slug: "project-a", project_name: "Project A", status: "READY", workflow_input_status: "READY", runnable: true } };
            state.selectedProjectProductionPackage = {
              lifecycle: "PRODUCTION_READY",
              approved_group_id: "grp_000007",
              state_revision: 14,
              ready_for_export: true,
              download_url: "/api/v2/channels/channel-a/projects/project-a/production-package/download",
              artifacts: [
                { filename: "content.md", character_count: 100, file_url: "/content", exists: true, matches_approved_revision_metadata: true },
                { filename: "publishing_package.md", character_count: 50, file_url: "/publishing", exists: true, matches_approved_revision_metadata: true }
              ],
            };
            state.selectedProjectWorkflow = {
              binding: { workflow_id: "wf-demo", workflow_version: "2", workflow_definition_sha256: "abc123", binding_source: "PROJECT_JSON" },
              definition: { workflow_id: "wf-demo", workflow_version: "2", display_name: "Workflow Demo", execution_mode: "ASSISTED", prompt_set: { status: "AVAILABLE", bundle_available: true }, steps: [{ step_id: "prompt_7_final_content", order: 7, display_name: "Final Content", required_model: "Claude", input_artifact_ids: [], optional_input_artifact_ids: [], output_artifact_ids: ["content"], resulting_lifecycle_state: "PRODUCTION_READY", constraints: [] }] },
              state: { current_step_id: "prompt_7_final_content", current_step_status: "APPROVED", next_step_id: null, current_lifecycle_state: "PRODUCTION_READY", state_revision: 14, state_persisted: true, step_states: { "prompt_7_final_content": { status: "APPROVED", approved_group_id: "grp_000007", candidate_group_id: null } } },
              available_actions: { "prompt_7_final_content": { save_candidate: false, approve_candidate: false, reject_candidate: false } },
              artifacts: [],
            };
            state.selectedWorkflowStepId = "prompt_7_final_content";
            render();
            const html = document.getElementById("projectDetailPanel").innerHTML;
            return {
              html,
              downloadCount: (html.match(/Download Production Package/g) || []).length,
              zipCount: (html.match(/Download Production ZIP/g) || []).length,
            };
            """
        )
        self.assertEqual(result["downloadCount"], 1)
        self.assertEqual(result["zipCount"], 0)

    def test_completed_workflow_has_only_one_completed_message(self):
        result = run_ui_runtime_scenario(
            """
            await flush();
            state.activeWorkspace = "workflow";
            state.selectedChannelSlug = "channel-a";
            state.selectedProjectSlug = "project-a";
            state.selectedProjectDetail = { project: { project_slug: "project-a", project_name: "Project A", status: "READY", workflow_input_status: "READY", runnable: true } };
            state.selectedProjectProductionPackage = {
              lifecycle: "PRODUCTION_READY",
              approved_group_id: "grp_000007",
              state_revision: 14,
              ready_for_export: true,
              download_url: "/api/v2/channels/channel-a/projects/project-a/production-package/download",
              artifacts: [{ filename: "content.md", character_count: 100, file_url: "/content", exists: true, matches_approved_revision_metadata: true }],
            };
            state.selectedProjectWorkflow = {
              binding: { workflow_id: "wf-demo", workflow_version: "2", workflow_definition_sha256: "abc123", binding_source: "PROJECT_JSON" },
              definition: { workflow_id: "wf-demo", workflow_version: "2", display_name: "Workflow Demo", execution_mode: "ASSISTED", prompt_set: { status: "AVAILABLE", bundle_available: true }, steps: [{ step_id: "prompt_7_final_content", order: 7, display_name: "Final Content", required_model: "Claude", input_artifact_ids: [], optional_input_artifact_ids: [], output_artifact_ids: ["content"], resulting_lifecycle_state: "PRODUCTION_READY", constraints: [] }] },
              state: { current_step_id: "prompt_7_final_content", current_step_status: "APPROVED", next_step_id: null, current_lifecycle_state: "PRODUCTION_READY", state_revision: 14, state_persisted: true, step_states: { "prompt_7_final_content": { status: "APPROVED", approved_group_id: "grp_000007", candidate_group_id: null } } },
              available_actions: { "prompt_7_final_content": { save_candidate: false, approve_candidate: false, reject_candidate: false } },
              artifacts: [],
            };
            state.selectedWorkflowStepId = "prompt_7_final_content";
            render();
            const html = document.getElementById("projectDetailPanel").innerHTML;
            return { completedCount: (html.match(/Workflow completed/g) || []).length };
            """
        )
        self.assertEqual(result["completedCount"], 1)

    def test_completed_workflow_uses_compact_rail_markup_instead_of_large_cards(self):
        self.assertIn(".step-rail-top", ui_server.HTML_PAGE)
        result = run_ui_runtime_scenario(
            """
            await flush();
            state.activeWorkspace = "workflow";
            state.selectedChannelSlug = "channel-a";
            state.selectedProjectSlug = "project-a";
            state.selectedProjectDetail = { project: { project_slug: "project-a", project_name: "Project A", status: "READY", workflow_input_status: "READY", runnable: true } };
            state.selectedProjectProductionPackage = { lifecycle: "PRODUCTION_READY", approved_group_id: "grp_000007", state_revision: 14, ready_for_export: true, download_url: "/download", artifacts: [] };
            const steps = [];
            const stepStates = {};
            for (let index = 1; index <= 7; index += 1) {
              steps.push({ step_id: "prompt_" + index, order: index, display_name: "Prompt " + index + " Title", required_model: "Claude", input_artifact_ids: [], optional_input_artifact_ids: [], output_artifact_ids: [], resulting_lifecycle_state: "PRODUCTION_READY", constraints: [] });
              stepStates["prompt_" + index] = { status: "APPROVED", approved_group_id: "grp_" + index, candidate_group_id: null };
            }
            state.selectedProjectWorkflow = {
              binding: { workflow_id: "wf-demo", workflow_version: "2", workflow_definition_sha256: "abc123", binding_source: "PROJECT_JSON" },
              definition: { workflow_id: "wf-demo", workflow_version: "2", display_name: "Workflow Demo", execution_mode: "ASSISTED", prompt_set: { status: "AVAILABLE", bundle_available: true }, steps },
              state: { current_step_id: "prompt_7", current_step_status: "APPROVED", next_step_id: null, current_lifecycle_state: "PRODUCTION_READY", state_revision: 14, state_persisted: true, step_states: stepStates },
              available_actions: {},
              artifacts: [],
            };
            state.selectedWorkflowStepId = "prompt_7";
            render();
            return {
              html: document.getElementById("projectDetailPanel").innerHTML,
            };
            """
        )
        self.assertEqual(result["html"].count('data-workflow-step-id='), 7)
        self.assertEqual(result["html"].count('class="step-rail-top"'), 7)

    def test_all_seven_approved_steps_display_completed_semantics(self):
        result = run_ui_runtime_scenario(
            """
            await flush();
            state.activeWorkspace = "workflow";
            state.selectedChannelSlug = "mist_of_ages";
            state.selectedProjectSlug = "20260702_ancient-rome-in-20-minutes";
            state.selectedProjectDetail = { project: { project_slug: "20260702_ancient-rome-in-20-minutes", project_name: "Ancient Rome in 20 Minutes", status: "READY", workflow_input_status: "READY", runnable: true } };
            state.selectedProjectProductionPackage = { lifecycle: "PRODUCTION_READY", approved_group_id: "grp_000007", state_revision: 14, ready_for_export: true, download_url: "/download", artifacts: [] };
            const steps = [];
            const stepStates = {};
            for (let index = 1; index <= 7; index += 1) {
              steps.push({ step_id: "prompt_" + index, order: index, display_name: "Prompt " + index, required_model: "Claude", input_artifact_ids: [], optional_input_artifact_ids: [], output_artifact_ids: [], resulting_lifecycle_state: "PRODUCTION_READY", constraints: [] });
              stepStates["prompt_" + index] = { status: "APPROVED", approved_group_id: "grp_" + index, candidate_group_id: null };
            }
            state.selectedProjectWorkflow = {
              binding: { workflow_id: "wf-demo", workflow_version: "2", workflow_definition_sha256: "abc123", binding_source: "PROJECT_JSON" },
              definition: { workflow_id: "wf-demo", workflow_version: "2", display_name: "Workflow Demo", execution_mode: "ASSISTED", prompt_set: { status: "AVAILABLE", bundle_available: true }, steps },
              state: { current_step_id: "prompt_7", current_step_status: "APPROVED", next_step_id: null, current_lifecycle_state: "PRODUCTION_READY", state_revision: 14, state_persisted: true, step_states: stepStates },
              available_actions: {},
              artifacts: [],
            };
            state.selectedWorkflowStepId = "prompt_7";
            render();
            return {
              html: document.getElementById("projectDetailPanel").innerHTML,
            };
            """
        )
        self.assertGreaterEqual(result["html"].count("Approved"), 7)

    def test_selected_approved_prompt_seven_remains_approved_not_ready(self):
        result = run_ui_runtime_scenario(
            """
            await flush();
            state.activeWorkspace = "workflow";
            state.selectedChannelSlug = "channel-a";
            state.selectedProjectSlug = "project-a";
            state.selectedProjectDetail = { project: { project_slug: "project-a", project_name: "Project A", status: "READY", workflow_input_status: "READY", runnable: true } };
            state.selectedProjectProductionPackage = { lifecycle: "PRODUCTION_READY", approved_group_id: "grp_000007", state_revision: 14, ready_for_export: true, download_url: "/download", artifacts: [] };
            const steps = [];
            const stepStates = {};
            for (let index = 1; index <= 7; index += 1) {
              steps.push({ step_id: "prompt_" + index, order: index, display_name: "Prompt " + index, required_model: "Claude", input_artifact_ids: [], optional_input_artifact_ids: [], output_artifact_ids: [], resulting_lifecycle_state: "PRODUCTION_READY", constraints: [] });
              stepStates["prompt_" + index] = { status: "APPROVED", approved_group_id: "grp_" + index, candidate_group_id: null };
            }
            state.selectedProjectWorkflow = {
              binding: { workflow_id: "wf-demo", workflow_version: "2", workflow_definition_sha256: "abc123", binding_source: "PROJECT_JSON" },
              definition: { workflow_id: "wf-demo", workflow_version: "2", display_name: "Workflow Demo", execution_mode: "ASSISTED", prompt_set: { status: "AVAILABLE", bundle_available: true }, steps },
              state: { current_step_id: "prompt_7", current_step_status: "APPROVED", next_step_id: null, current_lifecycle_state: "PRODUCTION_READY", state_revision: 14, state_persisted: true, step_states: stepStates },
              available_actions: {},
              artifacts: [],
            };
            state.selectedWorkflowStepId = "prompt_7";
            render();
            return {
              html: document.getElementById("projectDetailPanel").innerHTML,
            };
            """
        )
        self.assertIn('class="active"', result["html"])
        self.assertIn("Prompt 7", result["html"])
        active_match = re.search(r'class="active"[^>]*>(.*?)</button>', result["html"], re.DOTALL)
        self.assertIsNotNone(active_match)
        self.assertIn("Approved", active_match.group(1))
        self.assertNotIn("Ready", active_match.group(1))

    def test_completed_workflow_removes_redundant_project_summary_grid(self):
        result = run_ui_runtime_scenario(
            """
            await flush();
            state.activeWorkspace = "workflow";
            state.selectedChannelSlug = "channel-a";
            state.selectedProjectSlug = "project-a";
            state.selectedProjectDetail = { project: { project_slug: "project-a", project_name: "Project A", status: "READY", workflow_input_status: "READY", runnable: true } };
            state.selectedProjectProductionPackage = { lifecycle: "PRODUCTION_READY", approved_group_id: "grp_000007", state_revision: 14, ready_for_export: true, download_url: "/download", artifacts: [] };
            state.selectedProjectWorkflow = {
              binding: { workflow_id: "wf-demo", workflow_version: "2", workflow_definition_sha256: "abc123", binding_source: "PROJECT_JSON" },
              definition: { workflow_id: "wf-demo", workflow_version: "2", display_name: "Workflow Demo", execution_mode: "ASSISTED", prompt_set: { status: "AVAILABLE", bundle_available: true }, steps: [{ step_id: "prompt_7", order: 7, display_name: "Final Content", required_model: "Claude", input_artifact_ids: [], optional_input_artifact_ids: [], output_artifact_ids: ["content"], resulting_lifecycle_state: "PRODUCTION_READY", constraints: [] }] },
              state: { current_step_id: "prompt_7", current_step_status: "APPROVED", next_step_id: null, current_lifecycle_state: "PRODUCTION_READY", state_revision: 14, state_persisted: true, step_states: { "prompt_7": { status: "APPROVED", approved_group_id: "grp_000007", candidate_group_id: null } } },
              available_actions: {},
              artifacts: [],
            };
            state.selectedWorkflowStepId = "prompt_7";
            render();
            return { html: document.getElementById("projectDetailPanel").innerHTML };
            """
        )
        self.assertNotIn("<strong>Ready state</strong>", result["html"])
        self.assertNotIn("<strong>Workflow progress</strong>", result["html"])
        self.assertNotIn("<strong>Production handoff</strong>", result["html"])

    def test_completed_workflow_details_are_collapsed_by_default(self):
        result = run_ui_runtime_scenario(
            """
            await flush();
            state.activeWorkspace = "workflow";
            state.selectedChannelSlug = "channel-a";
            state.selectedProjectSlug = "project-a";
            state.selectedProjectDetail = { project: { project_slug: "project-a", project_name: "Project A", status: "READY", workflow_input_status: "READY", runnable: true } };
            state.selectedProjectProductionPackage = { lifecycle: "PRODUCTION_READY", approved_group_id: "grp_000007", state_revision: 14, ready_for_export: true, download_url: "/download", artifacts: [] };
            state.selectedProjectWorkflow = {
              binding: { workflow_id: "wf-demo", workflow_version: "2", workflow_definition_sha256: "abc123", binding_source: "PROJECT_JSON" },
              definition: { workflow_id: "wf-demo", workflow_version: "2", display_name: "Workflow Demo", execution_mode: "ASSISTED", prompt_set: { status: "AVAILABLE", bundle_available: true }, steps: [{ step_id: "prompt_7", order: 7, display_name: "Final Content", required_model: "Claude", input_artifact_ids: [], optional_input_artifact_ids: [], output_artifact_ids: ["content"], resulting_lifecycle_state: "PRODUCTION_READY", constraints: [] }] },
              state: { current_step_id: "prompt_7", current_step_status: "APPROVED", next_step_id: null, current_lifecycle_state: "PRODUCTION_READY", state_revision: 14, state_persisted: true, step_states: { "prompt_7": { status: "APPROVED", approved_group_id: "grp_000007", candidate_group_id: null } } },
              available_actions: {},
              artifacts: [],
            };
            state.selectedWorkflowStepId = "prompt_7";
            render();
            return { html: document.getElementById("projectDetailPanel").innerHTML };
            """
        )
        self.assertIn("<summary>Workflow Details</summary>", result["html"])
        self.assertIn("<summary>Technical Details</summary>", result["html"])
        self.assertNotIn("<details open", result["html"])
    def test_multiple_workflows_require_selection_before_create(self):
        result = run_ui_runtime_scenario(
            """
            await flush();
            state.selectedChannelSlug = "channel-a";
            state.selectedChannelSummary = {
              channel: { channel_slug: "channel-a", status: "CONNECTED" },
              available_workflows: [
                { workflow_id: "wf-alpha", workflow_version: "2", display_name: "Workflow <Alpha>", version_status: "ACTIVE" },
                { workflow_id: "wf-beta", workflow_version: "1", display_name: "Workflow <Beta>", version_status: "ACTIVE" },
              ],
            };
            render();
            openCreateProjectPanel();
            await flush();
            const select = document.getElementById("createProjectWorkflowBinding");
            const button = document.getElementById("submitCreateProjectBtn");
            return {
              createDisabled: button.disabled,
              selectDisabled: select.disabled,
              selectedValue: select.value,
              helperHtml: document.getElementById("projectListPanel").innerHTML,
            };
            """
        )
        self.assertTrue(result["createDisabled"])
        self.assertFalse(result["selectDisabled"])
        self.assertEqual(result["selectedValue"], "")
        self.assertIn("Select a workflow before creating a project.", result["helperHtml"])
        self.assertIn("Workflow &lt;Alpha&gt; - v2", result["helperHtml"])
        self.assertIn("Workflow &lt;Beta&gt; - v1", result["helperHtml"])

    def test_single_active_workflow_is_auto_selected_and_selector_hidden(self):
        result = run_ui_runtime_scenario(
            """
            await flush();
            state.selectedChannelSlug = "mist_of_ages";
            state.selectedChannelSummary = {
              channel: { channel_slug: "mist_of_ages", status: "CONNECTED" },
              available_workflows: [
                { workflow_id: "mist_of_ages_assisted_content", workflow_version: "1", display_name: "Mist of Ages Assisted Content", version_status: "ACTIVE" },
                { workflow_id: "mist_of_ages_assisted_content", workflow_version: "2", display_name: "Mist of Ages Assisted Content", version_status: "ACTIVE" },
              ],
            };
            openCreateProjectPanel();
            await flush();
            state.createProjectUrlDraft = "https://www.youtube.com/watch?v=VIDEO12345A";
            render();
            return {
              selectedWorkflowValue: state.createProjectWorkflowValue,
              selectedWorkflowVersion: selectedCreateWorkflowOption() && selectedCreateWorkflowOption().workflow_version,
              createDisabled: document.getElementById("submitCreateProjectBtn").disabled,
              helperHtml: document.getElementById("projectListPanel").innerHTML,
            };
            """
        )
        self.assertEqual(result["selectedWorkflowValue"], "mist_of_ages_assisted_content@@2")
        self.assertEqual(result["selectedWorkflowVersion"], "2")
        self.assertNotIn('id="createProjectWorkflowBinding"', result["helperHtml"])
        self.assertFalse(result["createDisabled"])
        self.assertNotIn("mist_of_ages_assisted_content@@2", result["helperHtml"])

    def test_multiple_workflow_selection_enables_create_after_choice(self):
        result = run_ui_runtime_scenario(
            """
            await flush();
            state.selectedChannelSlug = "channel-a";
            state.selectedChannelSummary = {
              channel: { channel_slug: "channel-a", status: "CONNECTED" },
              available_workflows: [
                { workflow_id: "wf-alpha", workflow_version: "1", display_name: "Workflow Alpha", version_status: "ACTIVE" },
                { workflow_id: "wf-beta", workflow_version: "2", display_name: "Workflow Beta", version_status: "ACTIVE" },
              ],
            };
            openCreateProjectPanel();
            await flush();
            state.createProjectUrlDraft = "https://youtu.be/VIDEO12345A";
            render();
            const before = document.getElementById("submitCreateProjectBtn").disabled;
            state.createProjectWorkflowValue = "wf-beta@@2";
            render();
            return {
              before,
              after: document.getElementById("submitCreateProjectBtn").disabled,
              helperHtml: document.getElementById("projectListPanel").innerHTML,
              visibleText: document.getElementById("projectListPanel").textContent,
            };
            """
        )
        self.assertTrue(result["before"])
        self.assertFalse(result["after"])
        self.assertIn("Workflow Beta - v2", result["helperHtml"])
        self.assertNotIn("wf-beta@@2", result["visibleText"])

    def test_no_active_workflow_keeps_url_editable_and_create_disabled(self):
        result = run_ui_runtime_scenario(
            """
            await flush();
            state.selectedChannelSlug = "channel-a";
            state.selectedChannelSummary = {
              channel: { channel_slug: "channel-a", status: "CONNECTED" },
              available_workflows: [
                { workflow_id: "wf-alpha", workflow_version: "1", display_name: "Workflow Alpha", version_status: "DEPRECATED" },
              ],
            };
            openCreateProjectPanel();
            await flush();
            state.createProjectUrlDraft = "https://youtu.be/VIDEO12345A";
            render();
            return {
              inputDisabled: document.getElementById("createProjectUrlInput").disabled,
              createDisabled: document.getElementById("submitCreateProjectBtn").disabled,
              helperHtml: document.getElementById("projectListPanel").innerHTML,
            };
            """
        )
        self.assertNotIn('id="createProjectWorkflowBinding"', result["helperHtml"])
        self.assertFalse(result["inputDisabled"])
        self.assertTrue(result["createDisabled"])
        self.assertIn("No project workflow is available for this channel.", result["helperHtml"])

    def test_channel_change_clears_incompatible_selection_and_auto_selects_sole_workflow(self):
        result = run_ui_runtime_scenario(
            """
            await flush();
            state.selectedChannelSlug = "channel-a";
            state.selectedChannelSummary = {
              channel: { channel_slug: "channel-a", status: "CONNECTED" },
              available_workflows: [
                { workflow_id: "wf-alpha", workflow_version: "1", display_name: "Workflow Alpha", version_status: "ACTIVE" },
                { workflow_id: "wf-alpha", workflow_version: "2", display_name: "Workflow Alpha", version_status: "ACTIVE" },
              ],
            };
            openCreateProjectPanel();
            await flush();
            state.createProjectUrlDraft = "https://youtu.be/VIDEO12345A";
            state.createProjectWorkflowValue = "wf-alpha@@1";
            state.selectedChannelSlug = "channel-b";
            state.selectedChannelSummary = {
              channel: { channel_slug: "channel-b", status: "CONNECTED" },
              available_workflows: [
                { workflow_id: "wf-beta", workflow_version: "7", display_name: "Workflow Beta", version_status: "ACTIVE" },
              ],
            };
            syncCreateProjectWorkflowSelection();
            render();
            return {
              workflowValue: state.createProjectWorkflowValue,
              workflowVersion: selectedCreateWorkflowOption() && selectedCreateWorkflowOption().workflow_version,
              urlDraft: state.createProjectUrlDraft,
              helperHtml: document.getElementById("projectListPanel").innerHTML,
            };
            """
        )
        self.assertEqual(result["workflowValue"], "wf-beta@@7")
        self.assertEqual(result["workflowVersion"], "7")
        self.assertEqual(result["urlDraft"], "https://youtu.be/VIDEO12345A")
        self.assertNotIn('id="createProjectWorkflowBinding"', result["helperHtml"])

    def test_existing_selected_project_does_not_block_sole_workflow_auto_selection(self):
        result = run_ui_runtime_scenario(
            """
            await flush();
            state.selectedChannelSlug = "channel-a";
            state.selectedChannelSummary = {
              channel: { channel_slug: "channel-a", display_name: "Channel A", status: "CONNECTED" },
              available_workflows: [{ workflow_id: "wf-alpha", workflow_version: "2", display_name: "Workflow Alpha", version_status: "ACTIVE" }],
            };
            state.projects = [{ project_slug: "project-a", project_name: "Project A", status: "READY", workflow_input_status: "READY" }];
            state.selectedProjectSlug = "project-a";
            state.selectedProjectDetail = { project: { project_slug: "project-a", project_name: "Project A", status: "READY", workflow_input_status: "READY", runnable: true } };
            openCreateProjectPanel();
            await flush();
            return {
              selectedProjectSlug: state.selectedProjectSlug,
              workflowValue: state.createProjectWorkflowValue,
              createDisabledBeforeUrl: document.getElementById("submitCreateProjectBtn").disabled,
            };
            """
        )
        self.assertEqual(result["selectedProjectSlug"], "project-a")
        self.assertEqual(result["workflowValue"], "wf-alpha@@2")
        self.assertTrue(result["createDisabledBeforeUrl"])

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
            openCreateProjectPanel();
            await flush();
            document.getElementById("createProjectUrlInput").value = "https://youtube.com/watch?v=VIDEO12345A";
            state.createProjectUrlDraft = "https://youtube.com/watch?v=VIDEO12345A";
            render();
            await createProjectAction();
            await flush();
            await flush();
            if (state.selectedProjectSlug === "project-a" && !state.selectedProjectWorkflow) {
              await loadSelectedProjectDetail("project-a", "channel-a");
              await flush();
            }
            const createCall = fetchCalls.find((call) => call.path === "/api/v2/channels/channel-a/projects" && call.method === "POST");
            return {
              createPanelStillOpen: document.getElementById("projectListPanel").innerHTML.includes('id="createProjectPanel"'),
              createBody: JSON.parse(createCall.body),
              feedback: state.projectFeedback.text,
              workflowSummaryVisible: document.getElementById("projectDetailPanel").innerHTML.includes("Workflow Alpha"),
              workflowVersionState: state.selectedProjectWorkflow && state.selectedProjectWorkflow.binding ? state.selectedProjectWorkflow.binding.workflow_version : null,
            };
            """
        )
        self.assertFalse(result["createPanelStillOpen"])
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
        self.assertTrue(result["workflowSummaryVisible"])
        self.assertEqual(result["workflowVersionState"], "2")

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
            openCreateProjectPanel();
            await flush();
            state.createProjectWorkflowValue = "wf-alpha@@2";
            render();
            setSelectedChannelSlug("channel-b");
            await flush();
            openCreateProjectPanel();
            await flush();
            const select = document.getElementById("createProjectWorkflowBinding");
            return {
              selectedChannelSlug: state.selectedChannelSlug,
              selectedChannelSummary: state.selectedChannelSummary,
              selectedProjectSlug: state.selectedProjectSlug,
              selectValue: select.value,
              selectDisabled: select.disabled,
              createDisabled: document.getElementById("submitCreateProjectBtn").disabled,
            };
            """
        )
        self.assertEqual(result["selectedChannelSlug"], "channel-b")
        self.assertEqual(result["selectedChannelSummary"]["channel"]["channel_slug"], "channel-b")
        self.assertEqual(result["selectedChannelSummary"]["available_workflows"], [])
        self.assertIsNone(result["selectedProjectSlug"])
        self.assertTrue(result["selectDisabled"])
        self.assertTrue(result["createDisabled"])
        self.assertEqual(result["selectValue"], "")

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
            state.selectedProjectValidation = { checks: { transcript_real_content: true }, project: { workflow_input_status: "READY", runnable: true } };
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

    def test_parse_output_refreshes_workflow_capabilities_and_enables_save_for_ready_step(self):
        result = run_ui_runtime_scenario(
            """
            await flush();
            state.selectedChannelSlug = "channel-a";
            state.selectedProjectSlug = "project-a";
            state.selectedProjectDetail = { project: { project_slug: "project-a", status: "READY", workflow_input_status: "READY", runnable: true, source_video_id: "VID1", source_video_url: "https://example.com", updated_at: "2026-07-02T00:00:00Z" } };
            const workflowDefinition = {
              workflow_id: "wf-demo",
              workflow_version: "2",
              display_name: "Workflow Demo",
              execution_mode: "ASSISTED",
              prompt_set: { status: "AVAILABLE", bundle_available: true },
              steps: [{ step_id: "step-3", order: 3, display_name: "Step 3", required_model: "GPT", input_artifact_ids: [], optional_input_artifact_ids: [], output_artifact_ids: ["locked-creative-package"], resulting_lifecycle_state: "THREE", constraints: [] }],
            };
            state.selectedProjectWorkflow = {
              channel_slug: "channel-a",
              project_slug: "project-a",
              binding: { workflow_id: "wf-demo", workflow_version: "2", workflow_definition_sha256: "sha-workflow", binding_source: "PROJECT_JSON" },
              definition: workflowDefinition,
              state: { current_step_id: "step-3", current_step_status: "READY", next_step_id: null, current_lifecycle_state: "TWO", state_revision: 4, state_persisted: true, step_states: { "step-3": { step_id: "step-3", status: "READY", candidate_group_id: null, approved_group_id: null } } },
              available_actions: { "step-3": { save_candidate: false, approve_candidate: false, reject_candidate: false } },
              artifacts: [{ artifact_id: "locked-creative-package", display_name: "Locked Creative Package", relative_path: "workflow/locked_creative_package.md", exists: false }],
            };
            state.selectedWorkflowStepId = "step-3";
            state.selectedWorkflowBundle = {
              channel_slug: "channel-a",
              project_slug: "project-a",
              step_id: "step-3",
              binding: { workflow_id: "wf-demo", workflow_version: "2", workflow_definition_sha256: "sha-workflow" },
              bundle: "Prompt bundle",
              bundle_sha256: "sha-bundle",
              bundle_character_count: "Prompt bundle".length,
              prompt_file_sha256: "prompt-sha",
              input_artifact_ids: [],
              missing_optional_inputs: [],
              required_model: "GPT",
              output_contract: { response_mode: "SINGLE_ARTIFACT" },
              identity: { channel_slug: "channel-a", project_slug: "project-a", workflow_id: "wf-demo", workflow_version: "2", workflow_definition_sha256: "sha-workflow", step_id: "step-3", bundle_sha256: "sha-bundle" },
            };
            state.selectedProjectValidation = { checks: { transcript_real_content: true }, project: { workflow_input_status: "READY", runnable: true } };
            state.pastedOutputDraft = "# Locked Creative Package\\n## Topic Verdict\\nPRODUCE\\n";
            fetchHandler = async (path) => {
              if (path.endsWith("/steps/step-3/parse-output")) {
                return jsonResponse({
                  identity: { channel_slug: "channel-a", project_slug: "project-a", workflow_id: "wf-demo", workflow_version: "2", step_id: "step-3", bundle_sha256: "sha-bundle" },
                  raw_output: { sha256: "raw-sha", character_count: state.pastedOutputDraft.length },
                  contract: { response_mode: "SINGLE_ARTIFACT" },
                  status: "VALID",
                  artifacts: [{ artifact_id: "locked-creative-package", display_name: "Locked Creative Package", filename: "locked_creative_package.md", content: state.pastedOutputDraft, sha256: "artifact-sha", character_count: state.pastedOutputDraft.length, validation: { status: "VALID", errors: [], warnings: [], heading_results: [] } }],
                  validation: { errors: [], warnings: [] },
                });
              }
              if (path.endsWith("/workflow")) {
                return jsonResponse({
                  channel_slug: "channel-a",
                  project_slug: "project-a",
                  binding: { workflow_id: "wf-demo", workflow_version: "2", workflow_definition_sha256: "sha-workflow", binding_source: "PROJECT_JSON" },
                  definition: workflowDefinition,
                  state: { current_step_id: "step-3", current_step_status: "READY", next_step_id: null, current_lifecycle_state: "TWO", state_revision: 4, state_persisted: true, step_states: { "step-3": { step_id: "step-3", status: "READY", candidate_group_id: null, approved_group_id: null } } },
                  available_actions: { "step-3": { save_candidate: true, approve_candidate: false, reject_candidate: false } },
                  artifacts: [{ artifact_id: "locked-creative-package", display_name: "Locked Creative Package", relative_path: "workflow/locked_creative_package.md", exists: false }],
                });
              }
              return jsonResponse({ channels: [] });
            };
            render();
            await parseOutputAction();
            await flush();
            const saveButton = saveCandidateButtonModel();
            return {
              workflowFetchCount: fetchCalls.filter((call) => call.path.endsWith("/workflow")).length,
              previewStatus: state.parsedOutputResult && state.parsedOutputResult.status,
              previewValue: document.getElementById("parsedArtifactPreview0").value,
              saveDisabled: saveButton.disabled,
              saveHelper: saveButton.helper,
              saveReady: state.selectedProjectWorkflow.available_actions["step-3"].save_candidate,
              panelShowsBlockedHelper: document.getElementById("projectDetailPanel").innerHTML.includes("This workflow step does not currently allow candidate save."),
            };
            """
        )
        self.assertEqual(result["workflowFetchCount"], 1)
        self.assertEqual(result["previewStatus"], "VALID")
        self.assertEqual(result["previewValue"], "# Locked Creative Package\n## Topic Verdict\nPRODUCE\n")
        self.assertTrue(result["saveReady"])
        self.assertFalse(result["saveDisabled"])
        self.assertFalse(result["panelShowsBlockedHelper"])
        self.assertNotIn("does not currently allow candidate save", result["saveHelper"])

    def test_parse_output_refresh_keeps_save_blocked_when_backend_capability_is_false(self):
        result = run_ui_runtime_scenario(
            """
            await flush();
            state.selectedChannelSlug = "channel-a";
            state.selectedProjectSlug = "project-a";
            state.selectedProjectDetail = { project: { project_slug: "project-a", status: "READY", workflow_input_status: "READY", runnable: true, source_video_id: "VID1", source_video_url: "https://example.com", updated_at: "2026-07-02T00:00:00Z" } };
            const workflowDefinition = {
              workflow_id: "wf-demo",
              workflow_version: "2",
              display_name: "Workflow Demo",
              execution_mode: "ASSISTED",
              prompt_set: { status: "AVAILABLE", bundle_available: true },
              steps: [{ step_id: "step-3", order: 3, display_name: "Step 3", required_model: "GPT", input_artifact_ids: [], optional_input_artifact_ids: [], output_artifact_ids: ["locked-creative-package"], resulting_lifecycle_state: "THREE", constraints: [] }],
            };
            state.selectedProjectWorkflow = {
              channel_slug: "channel-a",
              project_slug: "project-a",
              binding: { workflow_id: "wf-demo", workflow_version: "2", workflow_definition_sha256: "sha-workflow", binding_source: "PROJECT_JSON" },
              definition: workflowDefinition,
              state: { current_step_id: "step-3", current_step_status: "READY", next_step_id: null, current_lifecycle_state: "TWO", state_revision: 4, state_persisted: true, step_states: { "step-3": { step_id: "step-3", status: "READY", candidate_group_id: null, approved_group_id: null } } },
              available_actions: { "step-3": { save_candidate: true, approve_candidate: false, reject_candidate: false } },
              artifacts: [{ artifact_id: "locked-creative-package", display_name: "Locked Creative Package", relative_path: "workflow/locked_creative_package.md", exists: false }],
            };
            state.selectedProjectValidation = { checks: { transcript_real_content: true }, project: { workflow_input_status: "READY", runnable: true } };
            state.selectedWorkflowStepId = "step-3";
            state.selectedWorkflowBundle = {
              channel_slug: "channel-a",
              project_slug: "project-a",
              step_id: "step-3",
              binding: { workflow_id: "wf-demo", workflow_version: "2", workflow_definition_sha256: "sha-workflow" },
              bundle: "Prompt bundle",
              bundle_sha256: "sha-bundle",
              bundle_character_count: "Prompt bundle".length,
              prompt_file_sha256: "prompt-sha",
              input_artifact_ids: [],
              missing_optional_inputs: [],
              required_model: "GPT",
              output_contract: { response_mode: "SINGLE_ARTIFACT" },
              identity: { channel_slug: "channel-a", project_slug: "project-a", workflow_id: "wf-demo", workflow_version: "2", workflow_definition_sha256: "sha-workflow", step_id: "step-3", bundle_sha256: "sha-bundle" },
            };
            state.pastedOutputDraft = "# Locked Creative Package\\n## Topic Verdict\\nPRODUCE\\n";
            fetchHandler = async (path) => {
              if (path.endsWith("/steps/step-3/parse-output")) {
                return jsonResponse({
                  identity: { channel_slug: "channel-a", project_slug: "project-a", workflow_id: "wf-demo", workflow_version: "2", step_id: "step-3", bundle_sha256: "sha-bundle" },
                  raw_output: { sha256: "raw-sha", character_count: state.pastedOutputDraft.length },
                  contract: { response_mode: "SINGLE_ARTIFACT" },
                  status: "VALID",
                  artifacts: [{ artifact_id: "locked-creative-package", display_name: "Locked Creative Package", filename: "locked_creative_package.md", content: state.pastedOutputDraft, sha256: "artifact-sha", character_count: state.pastedOutputDraft.length, validation: { status: "VALID", errors: [], warnings: [], heading_results: [] } }],
                  validation: { errors: [], warnings: [] },
                });
              }
              if (path.endsWith("/workflow")) {
                return jsonResponse({
                  channel_slug: "channel-a",
                  project_slug: "project-a",
                  binding: { workflow_id: "wf-demo", workflow_version: "2", workflow_definition_sha256: "sha-workflow", binding_source: "PROJECT_JSON" },
                  definition: workflowDefinition,
                  state: { current_step_id: "step-3", current_step_status: "READY", next_step_id: null, current_lifecycle_state: "TWO", state_revision: 4, state_persisted: true, step_states: { "step-3": { step_id: "step-3", status: "READY", candidate_group_id: null, approved_group_id: null } } },
                  available_actions: { "step-3": { save_candidate: false, approve_candidate: false, reject_candidate: false } },
                  artifacts: [{ artifact_id: "locked-creative-package", display_name: "Locked Creative Package", relative_path: "workflow/locked_creative_package.md", exists: false }],
                });
              }
              return jsonResponse({ channels: [] });
            };
            render();
            await parseOutputAction();
            await flush();
            const saveButton = saveCandidateButtonModel();
            return {
              saveDisabled: saveButton.disabled,
              saveHelper: saveButton.helper,
              saveReady: state.selectedProjectWorkflow.available_actions["step-3"].save_candidate,
            };
            """
        )
        self.assertFalse(result["saveReady"])
        self.assertTrue(result["saveDisabled"])
        self.assertEqual(result["saveHelper"], "This workflow step does not currently allow candidate save.")

    def test_invalid_preview_keeps_save_disabled_even_when_backend_capability_is_true(self):
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
                steps: [{ step_id: "step-3", order: 3, display_name: "Step 3", required_model: "GPT", input_artifact_ids: [], optional_input_artifact_ids: [], output_artifact_ids: ["locked-creative-package"], resulting_lifecycle_state: "THREE", constraints: [] }],
              },
              state: { current_step_id: "step-3", current_step_status: "READY", next_step_id: null, current_lifecycle_state: "TWO", state_revision: 4, state_persisted: true, step_states: { "step-3": { step_id: "step-3", status: "READY", candidate_group_id: null, approved_group_id: null } } },
              available_actions: { "step-3": { save_candidate: true, approve_candidate: false, reject_candidate: false } },
              artifacts: [{ artifact_id: "locked-creative-package", display_name: "Locked Creative Package", relative_path: "workflow/locked_creative_package.md", exists: false }],
            };
            state.selectedProjectValidation = { checks: { transcript_real_content: true }, project: { workflow_input_status: "READY", runnable: true } };
            state.selectedWorkflowStepId = "step-3";
            state.selectedWorkflowBundle = {
              channel_slug: "channel-a",
              project_slug: "project-a",
              step_id: "step-3",
              binding: { workflow_id: "wf-demo", workflow_version: "2", workflow_definition_sha256: "sha-workflow" },
              bundle: "Prompt bundle",
              bundle_sha256: "sha-bundle",
              bundle_character_count: "Prompt bundle".length,
              prompt_file_sha256: "prompt-sha",
              input_artifact_ids: [],
              missing_optional_inputs: [],
              required_model: "GPT",
              output_contract: { response_mode: "SINGLE_ARTIFACT" },
              identity: { channel_slug: "channel-a", project_slug: "project-a", workflow_id: "wf-demo", workflow_version: "2", workflow_definition_sha256: "sha-workflow", step_id: "step-3", bundle_sha256: "sha-bundle" },
            };
            state.pastedOutputDraft = "# bad\\n";
            state.parsedOutputResult = {
              identity: { channel_slug: "channel-a", project_slug: "project-a", workflow_id: "wf-demo", workflow_version: "2", step_id: "step-3", bundle_sha256: "sha-bundle" },
              raw_output: { sha256: "raw-sha", character_count: state.pastedOutputDraft.length },
              contract: { response_mode: "SINGLE_ARTIFACT" },
              status: "INVALID",
              artifacts: [{ artifact_id: "locked-creative-package", display_name: "Locked Creative Package", filename: "locked_creative_package.md", content: state.pastedOutputDraft, sha256: "artifact-sha", character_count: state.pastedOutputDraft.length, validation: { status: "INVALID", errors: ["Missing heading"], warnings: [], heading_results: [] } }],
              validation: { errors: ["Artifact invalid"], warnings: [] },
            };
            render();
            const saveButton = saveCandidateButtonModel();
            return { saveDisabled: saveButton.disabled, saveHelper: saveButton.helper };
            """
        )
        self.assertTrue(result["saveDisabled"])
        self.assertEqual(result["saveHelper"], "Only a valid parsed output preview can be saved as a candidate.")

    def test_candidate_decision_buttons_follow_backend_capabilities_and_candidate_presence(self):
        result = run_ui_runtime_scenario(
            """
            await flush();
            state.selectedChannelSlug = "channel-a";
            state.selectedProjectSlug = "project-a";
            state.selectedProjectDetail = { project: { project_slug: "project-a", status: "READY", workflow_input_status: "READY", runnable: true, source_video_id: "VID1", source_video_url: "https://example.com", updated_at: "2026-07-02T00:00:00Z" } };
            const workflowDefinition = {
              workflow_id: "wf-demo",
              workflow_version: "2",
              display_name: "Workflow Demo",
              execution_mode: "ASSISTED",
              prompt_set: { status: "AVAILABLE", bundle_available: true },
              steps: [{ step_id: "step-3", order: 3, display_name: "Step 3", required_model: "GPT", input_artifact_ids: [], optional_input_artifact_ids: [], output_artifact_ids: ["locked-creative-package"], resulting_lifecycle_state: "THREE", constraints: [] }],
            };
            state.selectedProjectWorkflow = {
              channel_slug: "channel-a",
              project_slug: "project-a",
              binding: { workflow_id: "wf-demo", workflow_version: "2", workflow_definition_sha256: "sha-workflow", binding_source: "PROJECT_JSON" },
              definition: workflowDefinition,
              state: { current_step_id: "step-3", current_step_status: "READY", next_step_id: null, current_lifecycle_state: "TWO", state_revision: 4, state_persisted: true, step_states: { "step-3": { step_id: "step-3", status: "READY", candidate_group_id: null, approved_group_id: null } } },
              available_actions: { "step-3": { save_candidate: true, approve_candidate: false, reject_candidate: false } },
              artifacts: [{ artifact_id: "locked-creative-package", display_name: "Locked Creative Package", relative_path: "workflow/locked_creative_package.md", exists: false }],
            };
            state.selectedWorkflowStepId = "step-3";
            render();
            const noCandidateApprove = candidateDecisionButtonModel("APPROVE");
            const noCandidateReject = candidateDecisionButtonModel("REJECT");
            state.selectedProjectWorkflow = {
              ...state.selectedProjectWorkflow,
              state: { current_step_id: "step-3", current_step_status: "CANDIDATE", next_step_id: null, current_lifecycle_state: "THREE", state_revision: 5, state_persisted: true, step_states: { "step-3": { step_id: "step-3", status: "CANDIDATE", candidate_group_id: "grp_000003", approved_group_id: null, candidate_group: { revision_group_id: "grp_000003", artifacts: [] }, approved_group: null } } },
              available_actions: { "step-3": { save_candidate: false, approve_candidate: true, reject_candidate: true } },
            };
            render();
            const withCandidateApprove = candidateDecisionButtonModel("APPROVE");
            const withCandidateReject = candidateDecisionButtonModel("REJECT");
            return {
              noCandidateApproveDisabled: noCandidateApprove.disabled,
              noCandidateRejectDisabled: noCandidateReject.disabled,
              withCandidateApproveDisabled: withCandidateApprove.disabled,
              withCandidateRejectDisabled: withCandidateReject.disabled,
            };
            """
        )
        self.assertTrue(result["noCandidateApproveDisabled"])
        self.assertTrue(result["noCandidateRejectDisabled"])
        self.assertFalse(result["withCandidateApproveDisabled"])
        self.assertFalse(result["withCandidateRejectDisabled"])

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
            state.selectedProjectValidation = { checks: { transcript_real_content: true }, project: { workflow_input_status: "READY", runnable: true } };
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
            state.selectedProjectValidation = { checks: { transcript_real_content: true }, project: { workflow_input_status: "READY", runnable: true } };
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

    def test_bundle_ready_render_accepts_non_bmp_bundle_and_keeps_copy_available(self):
        result = run_ui_runtime_scenario(
            """
            await flush();
            state.selectedChannelSlug = "channel-a";
            state.selectedProjectSlug = "project-a";
            state.selectedProjectDetail = { project: { project_slug: "project-a", status: "READY", workflow_input_status: "READY", runnable: true, source_video_id: "VID1", source_video_url: "https://example.com", updated_at: "2026-07-02T00:00:00Z" } };
            state.selectedProjectTranscript = { transcript: "Saved transcript", is_template: false, has_real_content: true };
            state.selectedProjectWorkflow = {
              binding: { workflow_id: "wf-demo", workflow_version: "2", workflow_definition_sha256: "sha-workflow", binding_source: "PROJECT_JSON" },
              definition: {
                workflow_id: "wf-demo",
                workflow_version: "2",
                display_name: "Workflow Demo",
                execution_mode: "ASSISTED",
                prompt_set: { status: "AVAILABLE", bundle_available: true },
                steps: [{ step_id: "prompt_1_transcript_analysis", order: 1, display_name: "Transcript Analysis", required_model: "Gemini", input_artifact_ids: [], optional_input_artifact_ids: [], output_artifact_ids: ["transcript_analysis"], resulting_lifecycle_state: "ONE", constraints: [] }],
              },
              state: { current_step_id: "prompt_1_transcript_analysis", current_step_status: "READY", next_step_id: null, current_lifecycle_state: "INPUT_READY", state_revision: 0, state_persisted: false, step_states: {} },
              available_actions: { prompt_1_transcript_analysis: { save_candidate: true, approve_candidate: false, reject_candidate: false } },
              artifacts: [],
            };
            state.selectedWorkflowStepId = "prompt_1_transcript_analysis";
            state.selectedWorkflowBundle = {
              channel_slug: "channel-a",
              project_slug: "project-a",
              step_id: "prompt_1_transcript_analysis",
              binding: { workflow_id: "wf-demo", workflow_version: "2", workflow_definition_sha256: "sha-workflow" },
              bundle: "A🎥B",
              bundle_sha256: "sha-bundle",
              bundle_character_count: 3,
              prompt_file_sha256: "prompt-sha",
              input_artifact_ids: [],
              missing_optional_inputs: [],
              required_model: "Gemini",
              output_contract: { response_mode: "SINGLE_ARTIFACT" },
              identity: { channel_slug: "channel-a", project_slug: "project-a", workflow_id: "wf-demo", workflow_version: "2", workflow_definition_sha256: "sha-workflow", step_id: "prompt_1_transcript_analysis", bundle_sha256: "sha-bundle" },
            };
            render();
            return {
              detailHtml: document.getElementById("projectDetailPanel").innerHTML,
              previewValue: document.getElementById("bundlePreviewText").value,
              copyDisabled: document.getElementById("projectDetailPanel").innerHTML.includes('id="copyBundleBtn" disabled'),
            };
            """
        )
        self.assertNotIn("Bundle Error", result["detailHtml"])
        self.assertNotIn("loaded workflow bundle metadata is inconsistent", result["detailHtml"])
        self.assertIn("Bundle Status", result["detailHtml"])
        self.assertIn("Bundle Preview", result["detailHtml"])
        self.assertFalse(result["copyDisabled"])

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
              hasStaleNotice: html.includes("Stale Output"),
              hasInvalidatedNotice: html.includes("Invalidated Candidate"),
              approveDisabled: html.includes('id="approveCandidateBtn" disabled'),
              rejectDisabled: html.includes('id="rejectCandidateBtn" disabled'),
              containsHistory: html.includes("History"),
              containsRestore: html.includes("Restore"),
              containsDiff: html.includes("Diff"),
            };
            """
        )
        self.assertTrue(result["hasStaleNotice"])
        self.assertTrue(result["hasInvalidatedNotice"])
        self.assertTrue(result["approveDisabled"])
        self.assertTrue(result["rejectDisabled"])
        self.assertFalse(result["containsHistory"])
        self.assertFalse(result["containsRestore"])
        self.assertFalse(result["containsDiff"])

    def test_production_handoff_panel_renders_ready_download_and_artifact_links(self):
        result = run_ui_runtime_scenario(
            """
            await flush();
            state.activeWorkspace = "workflow";
            state.selectedChannelSlug = "channel-a";
            state.selectedProjectSlug = "project-a";
            state.selectedProjectDetail = { project: { project_slug: "project-a", status: "READY", workflow_input_status: "READY", runnable: true, source_video_url: "https://example.com", updated_at: "2026-07-05T00:00:00Z" } };
            state.selectedProjectProductionPackage = {
              lifecycle: "PRODUCTION_READY",
              approved_group_id: "grp_000007",
              state_revision: 14,
              ready_for_export: true,
              download_url: "/api/v2/channels/channel-a/projects/project-a/production-package/download",
              artifacts: [
                { filename: "content.md", relative_path: "workflow/content.md", sha256: "AAA", character_count: 100, file_url: "/content", exists: true, matches_approved_revision_metadata: true },
                { filename: "publishing_package.md", relative_path: "workflow/publishing_package.md", sha256: "BBB", character_count: 50, file_url: "/publishing", exists: true, matches_approved_revision_metadata: true },
              ],
            };
            render();
            return {
              html: document.getElementById("projectDetailPanel").innerHTML,
            };
            """
        )
        self.assertIn("Workflow completed", result["html"])
        self.assertIn("Download Production Package", result["html"])
        self.assertIn("content.md", result["html"])
        self.assertIn("publishing_package.md", result["html"])

    def test_analytics_collector_panel_renders_actions_counts_and_export_link(self):
        result = run_ui_runtime_scenario(
            """
            await flush();
            state.activeWorkspace = "analytics";
            state.selectedChannelSlug = "mist_of_ages";
            state.selectedChannelSummary = {
              channel: { channel_slug: "mist_of_ages", display_name: "Mist of Ages", status: "CONNECTED" },
              reporting: { status: "SUCCESS" },
            };
            state.selectedChannelAnalytics = {
              export_url: "/api/v2/channels/mist_of_ages/analytics/export",
              last_completed_sync_at: "2026-07-05T12:00:00Z",
              last_successful_sync_at: "2026-07-05T11:00:00Z",
              capability_counts: { AVAILABLE: 20, ERROR: 0 },
              report_readiness_counts: { READY: 0, PENDING: 20, ERROR: 0 },
              query_group_counts: { SUCCESS: 8, EMPTY: 1, UNAVAILABLE: 0, UNAUTHORIZED: 0, ERROR: 1 },
              normalized_tables: [
                { filename: "video_daily.csv", row_count: 200, status: "SUCCESS", technical_status: "SUCCESS" },
                { filename: "subscriber_status_daily.csv", row_count: 0, status: "ERROR", technical_status: "ERROR", availability_reason: "temporary YouTube error" },
              ],
              source_results: {
                analytics_queries: { status: "PARTIAL" },
                subscriber_status_daily: { status: "ERROR" },
              },
            };
            render();
            return {
              html: document.getElementById("analyticsPanel").innerHTML,
            };
            """
        )
        self.assertIn("Download Analytics ZIP", result["html"])
        self.assertIn("Completed with some unavailable data", result["html"])
        self.assertIn("Tables with data", result["html"])
        self.assertIn("20 bulk reports still pending", result["html"])
        self.assertNotIn("Query Groups", result["html"].split("<details")[0])

    def test_analytics_workspace_keeps_report_types_separate_from_generated_report_readiness(self):
        result = run_ui_runtime_scenario(
            """
            await flush();
            state.activeWorkspace = "analytics";
            state.selectedChannelSlug = "mist_of_ages";
            state.selectedChannelSummary = {
              channel: { channel_slug: "mist_of_ages", display_name: "Mist of Ages", status: "CONNECTED" },
              reporting: { status: "SUCCESS" },
            };
            state.selectedChannelAnalytics = {
              capability_counts: { AVAILABLE: 20, ERROR: 0 },
              report_readiness_counts: { READY: 0, PENDING: 20, ERROR: 0 },
              query_group_counts: { SUCCESS: 8, EMPTY: 1, UNAVAILABLE: 0, UNAUTHORIZED: 0, ERROR: 1 },
              normalized_tables: [
                { filename: "reach_end_screens.csv", row_count: 0, status: "PENDING", technical_status: "PENDING", availability_reason: "waiting for bulk report" },
                { filename: "subscriber_status_daily.csv", row_count: 0, status: "ERROR", technical_status: "ERROR", availability_reason: "temporary YouTube error" },
              ],
              source_results: { analytics_queries: { status: "PARTIAL" } },
            };
            render();
            return {
              html: document.getElementById("analyticsPanel").innerHTML,
            };
            """
        )
        self.assertIn("Report Type Availability", result["html"])
        self.assertIn("Generated Report Readiness", result["html"])
        self.assertIn("Waiting for YouTube bulk report", result["html"])
        self.assertIn("Temporary YouTube error", result["html"])
        self.assertIn("Technical Details", result["html"])

    def test_discover_capabilities_is_secondary_in_technical_details(self):
        result = run_ui_runtime_scenario(
            """
            await flush();
            state.activeWorkspace = "analytics";
            state.selectedChannelSlug = "mist_of_ages";
            state.selectedChannelSummary = {
              channel: { channel_slug: "mist_of_ages", display_name: "Mist of Ages", status: "CONNECTED" },
              reporting: { status: "SUCCESS" },
            };
            state.selectedChannelAnalytics = {
              export_url: "/api/v2/channels/mist_of_ages/analytics/export",
              source_results: { analytics_queries: { status: "PARTIAL" } },
              report_readiness_counts: { READY: 0, PENDING: 20, ERROR: 0 },
              capability_counts: { AVAILABLE: 20, ERROR: 0 },
              normalized_tables: [],
            };
            render();
            return { html: document.getElementById("analyticsPanel").innerHTML };
            """
        )
        self.assertIn('id="discoverAnalyticsBtn" class="secondary"', result["html"])
        self.assertIn("<summary>Technical Details</summary>", result["html"])

    def test_busy_action_state_disables_repeat_submission(self):
        result = run_ui_runtime_scenario(
            """
            await flush();
            state.activeWorkspace = "analytics";
            state.selectedChannelSlug = "mist_of_ages";
            state.selectedChannelSummary = {
              channel: { channel_slug: "mist_of_ages", display_name: "Mist of Ages", status: "CONNECTED" },
              reporting: { status: "SUCCESS" },
            };
            state.analyticsSyncAction = { busy: true, slug: "mist_of_ages", requestId: 1 };
            render();
            return {
              html: document.getElementById("analyticsPanel").innerHTML,
            };
            """
        )
        self.assertIn("Syncing Analytics...", result["html"])
        self.assertIn('id="syncAnalyticsCollectorBtn" class="primary" disabled', result["html"])

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
