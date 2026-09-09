# Copyright 2026 InsightOS
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import repo_versions as rv
from repo_profiles import detect_profile, effective_manifest, load_profile, read_env, url_key


ROOT = Path(__file__).resolve().parents[1]


class RepoProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def file(self, name, content):
        path = self.root / name
        path.write_text(content, encoding="utf-8")
        return path

    def profile(self, url="https://example.test/upstream/repo.git"):
        return self.file("custom.env", 'REPO_PROFILE=custom\nREPO_LIST="nested/repo"\n'
                         f'REPO_URL_NESTED_REPO={url}\nREPO_VERSIONS_FILE=versions.json\n')

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.root), *args], check=True,
                              capture_output=True, text=True)

    def git_profiles(self):
        self.git("init")
        for name in (".env", "staging.env", "upstream.env", "github.env"):
            self.file(name, (ROOT / name).read_text(encoding="utf-8"))

    def test_auto_detects_gitlab_groups_in_supported_url_formats(self):
        self.git_profiles()
        self.git("remote", "add", "origin", "placeholder")
        cases = [
            ("ssh://git@gitlab.example.invalid:22/staging/quick-start.git", "staging"),
            ("https://gitlab.example.invalid/example/semantic/quick-start.git", "upstream"),
            ("git@gitlab.example.invalid:example/semantic/quick-start.git", "upstream"),
            ("ssh://git@gitlab.example.invalid:22/example/ability/quick-start.git", "upstream"),
        ]
        with patch.dict(os.environ, {"GITLAB_SSH_ROOT": "ssh://git@gitlab.example.invalid:22"}):
            for url, expected in cases:
                with self.subTest(url=url):
                    self.git("remote", "set-url", "origin", url)
                    profile = load_profile(cwd=self.root, script_dir=self.root)
                    self.assertEqual(profile.name, expected)
                    self.assertIn("自动识别 origin", profile.selection)
                    self.assertEqual(profile.requested_path, "")

    def test_origin_wins_over_upstream_and_upstream_is_used_without_origin(self):
        self.git_profiles()
        self.git("remote", "add", "origin", "git@gitlab.example.invalid:staging/quick-start.git")
        self.git("remote", "add", "upstream", "git@gitlab.example.invalid:example/semantic/quick-start.git")
        self.assertEqual(load_profile(cwd=self.root, script_dir=self.root).name, "staging")
        self.git("remote", "remove", "origin")
        profile = load_profile(cwd=self.root, script_dir=self.root)
        self.assertEqual(profile.name, "upstream")
        self.assertIn("自动识别 upstream", profile.selection)

    def test_unrecognized_origin_falls_back_to_dotenv_not_unrelated_upstream(self):
        self.git_profiles()
        self.git("remote", "add", "origin", "https://example.test/personal/quick-start.git")
        self.git("remote", "add", "upstream", "git@gitlab.example.invalid:example/semantic/quick-start.git")
        self.file(".env", "REPO_ENV_FILE=staging.env\n")
        profile = load_profile(cwd=self.root, script_dir=self.root)
        self.assertEqual(profile.name, "staging")
        self.assertIn("回退 .env", profile.selection)

    def test_github_org_is_inferred_without_changing_environment(self):
        self.git_profiles()
        self.git("remote", "add", "origin", "git@github.com:semantic-public/quick-start.git")
        with patch.dict(os.environ, {"GITHUB_ORG": ""}):
            profile = load_profile(cwd=self.root, script_dir=self.root)
            self.assertEqual(profile.name, "github")
            self.assertEqual(profile.urls["semantic-framework"],
                             "https://github.com/semantic-public/Sementic-Framework.git")
            self.assertEqual(os.environ["GITHUB_ORG"], "")
        with patch.dict(os.environ, {"GITHUB_ORG": "explicit-org"}):
            profile = load_profile(cwd=self.root, script_dir=self.root)
            self.assertIn("/explicit-org/", profile.urls["semantic-framework"])

    def test_explicit_env_bypasses_detection(self):
        self.git_profiles()
        self.git("remote", "add", "origin", "git@github.com:semantic-public/quick-start.git")
        with patch("repo_profiles.detect_profile") as detect:
            profile = load_profile(self.root / "upstream.env", script_dir=self.root)
            detect.assert_not_called()
        self.assertEqual(profile.name, "upstream")
        self.assertEqual(profile.requested_path, str(self.root / "upstream.env"))

    def test_detects_script_repository_not_unrelated_working_directory(self):
        self.git_profiles()
        self.git("remote", "add", "origin", "git@gitlab.example.invalid:example/semantic/quick-start.git")
        elsewhere = self.root / "unrelated"
        elsewhere.mkdir()
        subprocess.run(["git", "init", str(elsewhere)], capture_output=True, check=True)
        subprocess.run(["git", "-C", str(elsewhere), "remote", "add", "origin",
                        "git@github.com:unrelated/project.git"], capture_output=True, check=True)
        profile = load_profile(cwd=elsewhere, script_dir=self.root)
        self.assertEqual(profile.name, "upstream")

    def test_missing_git_and_lookalike_hosts_do_not_misidentify_source(self):
        with patch("repo_profiles.subprocess.run", side_effect=FileNotFoundError):
            self.assertIsNone(detect_profile(self.root))
        self.git_profiles()
        self.git("remote", "add", "origin", "https://github.com.example.test/org/quick-start.git")
        self.assertIsNone(detect_profile(self.root))

    def test_dotenv_parsing_and_expansion_never_runs_shell(self):
        path = self.file("input.env", '# comment\nexport HOST=${HOST:-example.test}\n'
                         'URL="https://${HOST}/path#fragment" # note\n'
                         "LITERAL='$NOT_DEFINED'\nEMPTY=\n")
        values = read_env(path, {"HOST": "override.test"})
        self.assertEqual(values["URL"], "https://override.test/path#fragment")
        self.assertEqual(values["LITERAL"], "$NOT_DEFINED")
        self.assertEqual(values["EMPTY"], "")
        self.assertNotIn("REPO_PROFILE", os.environ)
        for line in ("VALUE=$(touch sentinel)", "VALUE=${MISSING}", "broken line"):
            path = self.file("bad.env", line)
            with self.assertRaises(ValueError):
                read_env(path, {})
        self.assertFalse((self.root / "sentinel").exists())

    def test_default_selector_and_explicit_selection(self):
        path = self.profile()
        self.file(".env", "REPO_ENV_FILE=custom.env\n")
        profile = load_profile(cwd=self.root, script_dir=self.root)
        self.assertEqual(profile.source, path)
        self.assertEqual(profile.name, "custom")
        self.assertEqual(profile.manifest, str(self.root / "versions.json"))
        other = self.file("other.env", "REPO_LIST=other\nREPO_URL_OTHER=https://other.test/repo.git\n")
        self.assertEqual(list(load_profile(other).urls), ["other"])

    def test_script_directory_fallback_and_legacy_mode(self):
        elsewhere = self.root / "elsewhere"
        elsewhere.mkdir()
        self.assertIsNone(load_profile(cwd=elsewhere, script_dir=self.root))
        self.profile()
        self.file(".env", "REPO_ENV_FILE=custom.env\n")
        self.assertEqual(load_profile(cwd=elsewhere, script_dir=self.root).name, "custom")

    def test_invalid_or_missing_explicit_profile_does_not_fallback(self):
        with self.assertRaises(FileNotFoundError):
            load_profile(self.root / "missing.env")
        for content in ("REPO_LIST=repo", "REPO_LIST=", "REPO_LIST=../escape\n",
                        "REPO_LIST='a-b a/b'\nREPO_URL_A_B=https://example.test/repo.git"):
            with self.assertRaises(ValueError):
                load_profile(self.file("invalid.env", content))

    def test_three_bundled_profiles_have_matching_local_repos(self):
        with patch.dict(os.environ, {"GITHUB_ORG": "example-org"}):
            profiles = [load_profile(ROOT / name) for name in
                        ("staging.env", "upstream.env", "github.env")]
        self.assertEqual(len(profiles[0].urls), 13)
        self.assertEqual(list(profiles[0].urls), list(profiles[1].urls))
        self.assertEqual(list(profiles[1].urls), list(profiles[2].urls))
        self.assertIn("/example/semantic/semantic-ability/r1pro-ability.git",
                      profiles[1].urls["semantic-ability/r1pro-ability"])
        self.assertEqual(profiles[2].urls["semantic-framework"],
                         "https://github.com/example-org/Sementic-Framework.git")

    def test_github_defaults_to_public_organization(self):
        with patch.dict(os.environ, {"GITHUB_ORG": ""}):
            profile = load_profile(ROOT / "github.env")
        self.assertEqual(profile.urls["semantic-web"],
                         "https://github.com/insightos-community/semantic-web.git")

    def test_profile_switch_save_and_snapshot_do_not_overwrite_manifest_urls(self):
        profile = load_profile(self.profile())
        data = {"version": 1, "repos": {"nested/repo": {
            "url": "https://example.test/fork/repo.git", "ref": "v1", "commit": ""},
            "excluded": {"url": "https://example.test/excluded.git", "ref": "v2"}}}
        cfg = self.root / "versions.json"
        rv.save_manifest(cfg, data)
        tui = rv.TUI(str(cfg), str(self.root / "workspace"), profile)
        self.addCleanup(tui.close)
        self.assertEqual(tui.repo_names, ["nested/repo"])
        self.assertFalse(tui.dirty_changed())
        with patch.object(tui, "input_dlg", return_value="v3"):
            tui.do_edit(None, "nested/repo")
        rv.save_manifest(cfg, tui.data)
        self.assertEqual(rv.load_manifest(cfg)["repos"]["nested/repo"]["url"],
                         "https://example.test/fork/repo.git")
        self.assertIn("excluded", rv.load_manifest(cfg)["repos"])
        with patch.object(rv, "current_ref", return_value=("tag", "v3", "abcd1234")):
            snapshot, count = rv.freeze_release(str(self.root), tui.effective_data(),
                                                 "v3", self.root / "releases")
        self.assertEqual(count, 1)
        self.assertEqual(rv.load_manifest(snapshot)["repos"]["nested/repo"]["url"],
                         profile.urls["nested/repo"])

    def test_profile_can_add_repositories_not_in_manifest(self):
        profile = load_profile(self.profile())
        original = {"repos": {}}
        effective = effective_manifest(original, profile)
        self.assertEqual(list(effective["repos"]), ["nested/repo"])
        self.assertEqual(original, {"repos": {}})
        self.assertEqual(url_key("nested/repo"), "REPO_URL_NESTED_REPO")

    def test_cli_explicit_env_and_overrides_without_network(self):
        env_file = self.profile()
        cfg = self.file("override.json", '{"repos": {"nested/repo": {"ref": "v4"}}}')
        argv = ["repo_versions.py", "--env", str(env_file), "--config", str(cfg),
                "--semantic", str(self.root / "checkout"), "--show-config"]
        output = io.StringIO()
        with patch.object(sys, "argv", argv), contextlib.redirect_stdout(output), \
                patch.object(rv, "remote_refs") as query:
            self.assertEqual(rv.main(), 0)
            query.assert_not_called()
        result = json.loads(output.getvalue())
        self.assertEqual(result["profile"], "custom")
        self.assertEqual(result["config"], str(cfg))
        self.assertEqual(result["semantic"], str(self.root / "checkout"))
        self.assertEqual(result["repos"]["nested/repo"]["ref"], "v4")

    def test_cli_no_env_preserves_legacy_custom_manifest(self):
        cfg = self.file("custom.json", '{"repos": {"only": {"url": "https://example.test/only.git"}}}')
        result = subprocess.run([sys.executable, "-B", str(ROOT / "repo_versions.py"),
                                 "--no-env", "--config", str(cfg), "--show-config"],
                                capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        self.assertEqual(data["profile"], "manifest")
        self.assertEqual(list(data["repos"]), ["only"])


if __name__ == "__main__":
    unittest.main()
