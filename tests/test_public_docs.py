# Copyright 2026 InsightOS
# SPDX-License-Identifier: Apache-2.0
"""Public documentation checks use synthetic data and never print matches."""

import contextlib
import importlib.util
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location(
    "public_docs", Path(__file__).resolve().parents[1] / "maintenance/check_public_docs.py"
)
docs = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(docs)


class PublicDocsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        (self.root / "repo-versions.json").write_text(json.dumps({"repos": {}}))
        for name in ("README.md", "README.zh-CN.md", "README.reference.md"):
            (self.root / name).write_text(
                "# Project\n\n[English](README.md) | [中文](README.zh-CN.md)\n"
            )

    def findings(self):
        return docs.check(self.root)[1]

    def test_valid_bilingual_pair(self):
        self.assertEqual(docs.check(self.root), (1, []))

    def test_missing_translation(self):
        (self.root / "README.zh-CN.md").unlink()
        self.assertIn((Path("README.zh-CN.md"), "missing-language-or-reference"), self.findings())

    def test_missing_component_is_not_silently_skipped(self):
        (self.root / "repo-versions.json").write_text(json.dumps({"repos": {"component": {}}}))
        self.assertIn((Path("component"), "missing-repository-or-readme"), self.findings())

    def test_broken_relative_link(self):
        with (self.root / "README.md").open("a") as stream:
            stream.write("\n[Guide](missing.md)\n")
        self.assertIn((Path("README.md"), "broken-local-link"), self.findings())

    def test_public_urls_and_loopback_are_allowed(self):
        with (self.root / "README.md").open("a") as stream:
            stream.write("\n[Source](https://github.com/example/project) http://127.0.0.1:8080\n")
        self.assertEqual(self.findings(), [])

    def test_escaped_path_and_anchor(self):
        (self.root / "Guide Notes.md").write_text("# Notes\n")
        with (self.root / "README.md").open("a") as stream:
            stream.write("\n[Notes](Guide%20Notes.md#notes)\n")
        self.assertEqual(self.findings(), [])

    def test_private_markdown_is_flagged(self):
        path = self.root / "guide.md"
        path.write_text("https://git.example.invalid/project\n/home/developer/work/\n")
        subprocess.run(["git", "-C", str(self.root), "add", "guide.md"], check=True)
        self.assertIn((Path("guide.md"), "internal-host"), self.findings())
        self.assertIn((Path("guide.md"), "personal-home"), self.findings())

    def test_vendor_documents_are_excluded(self):
        path = self.root / "_vendor" / "README.md"
        path.parent.mkdir()
        path.write_text("https://git.example.invalid/upstream\n")
        subprocess.run(["git", "-C", str(self.root), "add", str(path)], check=True)
        self.assertEqual(self.findings(), [])

    def test_conflict_marker(self):
        with (self.root / "README.md").open("a") as stream:
            stream.write("\n<<<<<<< branch\n")
        self.assertIn((Path("README.md"), "conflict-marker"), self.findings())

    def test_output_never_contains_token(self):
        token = "ghp_" + "x" * 24
        with (self.root / "README.md").open("a") as stream:
            stream.write("\n" + token + "\n")
        output = io.StringIO()
        with patch("sys.argv", ["check_public_docs.py", "--root", str(self.root)]):
            with contextlib.redirect_stdout(output):
                self.assertEqual(docs.main(), 1)
        self.assertNotIn(token, output.getvalue())
        self.assertIn("README.md: token", output.getvalue())


if __name__ == "__main__":
    unittest.main()
