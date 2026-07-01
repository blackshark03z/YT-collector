import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import ui_server


class CollectorTests(unittest.TestCase):
    def test_parse_video_id_variants(self):
        cases = {
            "https://www.youtube.com/watch?v=ABCDEFGHI01&t=10": "ABCDEFGHI01",
            "https://youtu.be/ABCDEFGHI01?si=test": "ABCDEFGHI01",
            "https://www.youtube.com/shorts/ABCDEFGHI01": "ABCDEFGHI01",
            "https://www.youtube.com/embed/ABCDEFGHI01": "ABCDEFGHI01",
        }
        for url, expected in cases.items():
            with self.subTest(url=url):
                self.assertEqual(ui_server.parse_video_id(url), expected)

    def test_parse_video_id_rejects_invalid_url(self):
        with self.assertRaises(ui_server.AppError):
            ui_server.parse_video_id("https://example.com/watch?v=ABCDEFGHI01")

    def test_safe_slug_is_windows_friendly(self):
        slug = ui_server.safe_slug("Why Rome Executed Jesus: Trial / Politics?", "fallback")
        self.assertEqual(slug, "why-rome-executed-jesus-trial-politics")

    def test_transcript_placeholder_fails_until_real_content_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "competitor_transcript.md"
            video = {
                "snippet": {"title": "A Video", "channelTitle": "Channel"},
                "contentDetails": {"duration": "PT12M"},
            }
            ui_server.create_transcript_template(path, video, "https://youtu.be/ABCDEFGHI01")
            self.assertFalse(ui_server.transcript_has_content(path))
            path.write_text(path.read_text(encoding="utf-8") + "\n" + ("real transcript text " * 10), encoding="utf-8")
            self.assertTrue(ui_server.transcript_has_content(path))

    def test_transcript_template_does_not_overwrite_existing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "competitor_transcript.md"
            path.write_text("manual transcript already here", encoding="utf-8")
            ui_server.create_transcript_template(path, {"snippet": {}, "contentDetails": {}}, "url")
            self.assertEqual(path.read_text(encoding="utf-8"), "manual transcript already here")


if __name__ == "__main__":
    unittest.main()
