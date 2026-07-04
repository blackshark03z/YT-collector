import hashlib
import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import channel_prompt_bundle, channel_workflow_write, channel_workspace, ui_server
from tests.test_channel_prompt_bundle import make_v2_bound_project, prepare_prompt7_inputs, prepare_step2_inputs


FINAL_CONTENT = "# Title\nBody\n"
FINAL_PACKAGE = "# Package\nTags\n"
FINAL_OUTPUT = (
    "=== FILE 1: content.md ===\n"
    f"{FINAL_CONTENT}"
    "=== FILE 2: publishing_package.md ===\n"
    f"{FINAL_PACKAGE}"
)


def tree_hashes(root: Path) -> dict[str, str]:
    entries: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            entries[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest().upper()
    return entries


def make_production_ready_project(root: Path) -> tuple[dict, Path]:
    project = make_v2_bound_project(root)
    project_dir = channel_workspace.canonical_channel_paths(root, "mist_of_ages").projects_dir / project["project_slug"]
    prepare_step2_inputs(root, "mist_of_ages", project["project_slug"])
    prepare_prompt7_inputs(root, "mist_of_ages", project["project_slug"])
    bundle = channel_prompt_bundle.build_prompt_bundle(
        root,
        "mist_of_ages",
        project["project_slug"],
        "prompt_7_final_content",
        project,
        project_dir,
    )
    _, saved = channel_workflow_write.save_candidate(
        root,
        "mist_of_ages",
        project["project_slug"],
        "prompt_7_final_content",
        bundle["bundle_sha256"],
        FINAL_OUTPUT,
        6,
    )
    channel_workflow_write.approve_candidate(
        root,
        "mist_of_ages",
        project["project_slug"],
        "prompt_7_final_content",
        saved["revision_group"]["revision_group_id"],
        7,
    )
    return project, project_dir


class ProductionExportTests(unittest.TestCase):
    def test_summary_route_returns_ready_identity_for_production_ready_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project, _ = make_production_ready_project(root)
            status, data = ui_server.dispatch_v2_request(
                "GET",
                f"/api/v2/channels/mist_of_ages/projects/{project['project_slug']}/production-package",
                context=ui_server.build_app_context(root=root),
            )
            self.assertEqual(status, 200)
            summary = data["production_package"]
            self.assertTrue(summary["ready_for_export"])
            self.assertEqual(summary["lifecycle"], "PRODUCTION_READY")
            self.assertEqual(summary["approved_group_id"], "grp_000007")
            self.assertEqual([item["filename"] for item in summary["artifacts"]], ["content.md", "publishing_package.md"])

    def test_download_route_returns_zip_with_manifest_and_exact_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project, _ = make_production_ready_project(root)
            status, data = ui_server.dispatch_v2_request(
                "GET",
                f"/api/v2/channels/mist_of_ages/projects/{project['project_slug']}/production-package/download",
                context=ui_server.build_app_context(root=root),
            )
            self.assertEqual(status, 200)
            self.assertEqual(data["content_type"], "application/zip")
            archive = zipfile.ZipFile(io.BytesIO(data["__binary__"]))
            self.assertEqual(archive.namelist(), ["content.md", "publishing_package.md", "manifest.json"])
            self.assertEqual(archive.read("content.md").decode("utf-8"), FINAL_CONTENT)
            self.assertEqual(archive.read("publishing_package.md").decode("utf-8"), FINAL_PACKAGE)
            manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
            self.assertEqual(manifest["workflow_id"], "mist_of_ages_assisted_content")
            self.assertEqual(manifest["workflow_version"], "2")
            self.assertEqual(manifest["lifecycle"], "PRODUCTION_READY")
            self.assertEqual(manifest["approved_group_id"], "grp_000007")
            self.assertEqual([item["filename"] for item in manifest["artifacts"]], ["content.md", "publishing_package.md"])

    def test_download_rejects_non_production_ready_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_v2_bound_project(root)
            prepare_prompt7_inputs(root, "mist_of_ages", project["project_slug"])
            with self.assertRaises(ui_server.V2Error) as ctx:
                ui_server.dispatch_v2_request(
                    "GET",
                    f"/api/v2/channels/mist_of_ages/projects/{project['project_slug']}/production-package/download",
                    context=ui_server.build_app_context(root=root),
                )
            self.assertEqual(ctx.exception.code, "PRODUCTION_EXPORT_NOT_READY")

    def test_download_rejects_missing_required_stable_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project, project_dir = make_production_ready_project(root)
            (project_dir / "publishing_package.md").unlink()
            with self.assertRaises(ui_server.V2Error) as ctx:
                ui_server.dispatch_v2_request(
                    "GET",
                    f"/api/v2/channels/mist_of_ages/projects/{project['project_slug']}/production-package/download",
                    context=ui_server.build_app_context(root=root),
                )
            self.assertEqual(ctx.exception.code, "PRODUCTION_EXPORT_MISSING_ARTIFACT")

    def test_download_rejects_hash_revision_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project, project_dir = make_production_ready_project(root)
            (project_dir / "content.md").write_text("corrupted\n", encoding="utf-8", newline="\n")
            with self.assertRaises(ui_server.V2Error) as ctx:
                ui_server.dispatch_v2_request(
                    "GET",
                    f"/api/v2/channels/mist_of_ages/projects/{project['project_slug']}/production-package/download",
                    context=ui_server.build_app_context(root=root),
                )
            self.assertEqual(ctx.exception.code, "PRODUCTION_EXPORT_IDENTITY_MISMATCH")

    def test_summary_and_download_do_not_mutate_project_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project, project_dir = make_production_ready_project(root)
            before = tree_hashes(project_dir)
            ui_server.dispatch_v2_request(
                "GET",
                f"/api/v2/channels/mist_of_ages/projects/{project['project_slug']}/production-package",
                context=ui_server.build_app_context(root=root),
            )
            ui_server.dispatch_v2_request(
                "GET",
                f"/api/v2/channels/mist_of_ages/projects/{project['project_slug']}/production-package/download",
                context=ui_server.build_app_context(root=root),
            )
            after = tree_hashes(project_dir)
            self.assertEqual(after, before)
