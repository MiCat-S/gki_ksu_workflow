#!/usr/bin/env python3
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]


def load_sync_module():
    filename = ROOT / ".github/scripts/sync_susfs_patches.py"
    spec = importlib.util.spec_from_file_location("sync_susfs_patches", filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sync = load_sync_module()


def run(command, cwd=None):
    return subprocess.check_output([str(item) for item in command], cwd=cwd)


def init_repo(path, files):
    path.mkdir(parents=True)
    run(["git", "init", "-q", path])
    for name, content in files.items():
        target = path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    run(["git", "-C", path, "add", "-A"])
    run(["git", "-C", path, "-c", "user.name=Test",
         "-c", "user.email=test@example.invalid", "commit", "-qm", "fixture"])
    return run(["git", "-C", path, "rev-parse", "HEAD"]).decode().strip()


def status_and_refs(repository):
    status = run(["git", "-C", repository, "status", "--porcelain=v1", "-z"])
    refs = subprocess.run(
        ["git", "-C", repository, "show-ref"], stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, check=False,
    ).stdout
    return status, refs


def directory_digest(root):
    digest = hashlib.sha256()
    for filename in sorted(path for path in root.rglob("*") if path.is_file()):
        digest.update(filename.relative_to(root).as_posix().encode())
        digest.update(b"\0")
        digest.update(filename.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


PATCH = """diff --git a/fs/namei.c b/fs/namei.c
--- a/fs/namei.c
+++ b/fs/namei.c
@@ -1 +1,4 @@
 base-namei
+filename_lookup(old_dfd, fake_filename, flags, &fake_path, NULL);
+filename_lookup(old_dfd, fake_filename, flags, &fake_path, NULL);
+nd->name = old_name;
diff --git a/fs/namespace.c b/fs/namespace.c
--- a/fs/namespace.c
+++ b/fs/namespace.c
@@ -1 +1,3 @@
 base-namespace
+if (mnt->mnt_id < DEFAULT_KSU_MNT_ID)
+if (mnt->mnt_id < DEFAULT_KSU_MNT_ID)
"""

SOURCE = """void susfs_update_sus_kstat(void)
{
	mutex_unlock(&susfs_mutex_lock_sus_kstat);
	kfree(new_entry);
	info.err = -ENOENT;
}

void susfs_spoof_cmdline_or_bootconfig(struct seq_file *m)
{
	strscpy(buf, fake_cmdline_or_bootconfig, SUSFS_FAKE_CMDLINE_OR_BOOTCONFIG_SIZE);
	seq_puts(m, buf);
	kfree(buf);
}
"""


class SyncFixture:
    def __init__(self, root):
        self.root = root
        self.workflow = root / "workflow"
        self.susfs = root / "susfs"
        self.cache = root / "cache"
        self.baseline = "1" * 40
        self.input_path = ".github/patches/50.patch"
        self.workflow_commit = init_repo(self.workflow, {self.input_path: PATCH, "notes": "clean\n"})
        self.susfs_commit = init_repo(
            self.susfs, {"kernel_patches/fs/susfs.c": SOURCE, "notes": "clean\n"})
        baseline = self.cache / self.baseline
        (baseline / "fs").mkdir(parents=True)
        (baseline / "fs/namei.c").write_text("base-namei\n")
        (baseline / "fs/namespace.c").write_text("base-namespace\n")
        tools = root / "tools"
        tools.mkdir()
        self.converter = tools / "converter.sh"
        self.converter.write_text("#!/bin/sh\nset -eu\ncp \"$1\" \"$2\"\n")
        self.config_dir = root / "config"
        self.config_dir.mkdir()
        self.config = self.config_dir / "sync.json"
        self.baseline_manifest = self.config_dir / "baselines.json"
        self.data = {
            "schema": 1,
            "reference_workflow": self.workflow_commit,
            "baseline_manifest": "baselines.json",
            "source_path": "kernel_patches/fs/susfs.c",
            "profiles": [self.profile("fixture")],
        }
        self.write_baseline_manifest()
        self.write_config()

    def profile(self, name):
        return {
            "name": name,
            "susfs_commit": self.susfs_commit,
            "source_sha256": hashlib.sha256(SOURCE.encode()).hexdigest(),
            "input_path": self.input_path,
            "input_sha256": hashlib.sha256(PATCH.encode()).hexdigest(),
            "output_50": f"{name}/50.patch",
            "output_51": f"{name}/51.patch",
            "baselines": [self.baseline],
        }

    def write_config(self):
        self.config.write_text(json.dumps(self.data, indent=2) + "\n")

    def write_baseline_manifest(self):
        baseline = self.cache / self.baseline
        files = {}
        for filename in sorted(path for path in baseline.rglob("*") if path.is_file()):
            relative = filename.relative_to(baseline).as_posix()
            mode = "100755" if filename.stat().st_mode & 0o111 else "100644"
            files[relative] = {
                "mode": mode,
                "sha256": hashlib.sha256(filename.read_bytes()).hexdigest(),
            }
        data = {
            "schema": 1,
            "tree_kind": "partial",
            "baselines": {
                self.baseline: {"file_count": len(files), "files": files},
            },
        }
        self.baseline_manifest.write_text(json.dumps(data, indent=2) + "\n")

    def generate(self, output):
        return sync.generate(self.config, self.workflow, self.susfs, self.cache,
                             self.converter, output)


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="test-susfs-sync-")
        self.root = Path(self.temporary.name)
        self.fixture = SyncFixture(self.root)

    def tearDown(self):
        self.temporary.cleanup()

    def test_reproducible_generation_preserves_fixes_and_inputs(self):
        (self.fixture.workflow / "notes").write_text("dirty workflow\n")
        (self.fixture.workflow / "untracked").write_text("keep\n")
        (self.fixture.susfs / "notes").write_text("dirty susfs\n")
        before_workflow = status_and_refs(self.fixture.workflow)
        before_susfs = status_and_refs(self.fixture.susfs)
        before_cache = directory_digest(self.fixture.cache)

        first = self.root / "candidate-one"
        second = self.root / "candidate-two"
        report = self.fixture.generate(first)
        self.fixture.generate(second)

        self.assertEqual(directory_digest(first), directory_digest(second))
        self.assertEqual((first / "fixture/50.patch").read_text(), PATCH)
        self.assertEqual((first / "fixture/51.patch").read_text(), PATCH)
        self.assertTrue(report["candidate_only"])
        self.assertEqual(
            set(report["profiles"][0]["fix_coverage"]),
            set(sync.SOURCE_FIXES) | set(sync.PATCH_FIXES),
        )
        self.assertTrue(all(report["profiles"][0]["fix_coverage"].values()))
        replay = report["profiles"][0]["baselines"][0]
        self.assertEqual((replay["offset"], replay["fuzz"]), (0, 0))
        self.assertEqual(replay["tree_kind"], "partial")
        self.assertEqual(replay["file_count"], 2)
        self.assertIn("result_partial_tree", replay)
        self.assertNotIn("commit", replay)
        self.assertNotIn("result_tree", replay)
        self.assertEqual(status_and_refs(self.fixture.workflow), before_workflow)
        self.assertEqual(status_and_refs(self.fixture.susfs), before_susfs)
        self.assertEqual(directory_digest(self.fixture.cache), before_cache)

    def test_offset_is_rejected_without_candidate_publication(self):
        baseline = self.fixture.cache / self.fixture.baseline / "fs/namei.c"
        baseline.write_text("shifted\nbase-namei\n")
        self.fixture.write_baseline_manifest()
        output = self.root / "must-not-exist"
        with self.assertRaises(sync.SyncError):
            self.fixture.generate(output)
        self.assertFalse(output.exists())
        self.assertFalse(list(self.root.glob(".must-not-exist.staging-*")))

    def test_late_failure_leaves_no_partial_batch(self):
        second = self.fixture.profile("second")
        second["input_sha256"] = "0" * 64
        self.fixture.data["profiles"].append(second)
        self.fixture.write_config()
        output = self.root / "batch"
        with self.assertRaises(sync.SyncError):
            self.fixture.generate(output)
        self.assertFalse(output.exists())
        self.assertFalse(list(self.root.glob(".batch.staging-*")))

    def test_invalid_profile_schema_fails_closed(self):
        for profile in (None, {"name": "fixture", "baselines": None}):
            data = copy.deepcopy(self.fixture.data)
            data["profiles"] = [profile]
            self.fixture.config.write_text(json.dumps(data, indent=2) + "\n")
            output = self.root / "invalid-profile"
            with self.subTest(profile=profile), self.assertRaises(sync.SyncError):
                self.fixture.generate(output)
            self.assertFalse(output.exists())

        data = copy.deepcopy(self.fixture.data)
        data["profiles"].append(copy.deepcopy(data["profiles"][0]))
        self.fixture.config.write_text(json.dumps(data, indent=2) + "\n")
        with self.assertRaises(sync.SyncError):
            self.fixture.generate(self.root / "duplicate-profile")
        self.assertFalse((self.root / "duplicate-profile").exists())
        self.fixture.write_config()

    def test_malformed_and_unknown_inputs_fail_closed(self):
        bad_repo = self.root / "bad-workflow"
        bad_patch = "not a patch\n"
        bad_commit = init_repo(bad_repo, {self.fixture.input_path: bad_patch})
        self.fixture.data["reference_workflow"] = bad_commit
        self.fixture.data["profiles"][0]["input_sha256"] = hashlib.sha256(
            bad_patch.encode()).hexdigest()
        self.fixture.write_config()
        output = self.root / "malformed"
        with self.assertRaises(sync.SyncError):
            sync.generate(self.fixture.config, bad_repo, self.fixture.susfs,
                          self.fixture.cache, self.fixture.converter, output)
        self.assertFalse(output.exists())

        unsafe_patch = """diff --git a/.git/config b/.git/config
--- a/.git/config
+++ b/.git/config
@@ -1 +1,2 @@
 safe
+unsafe
"""
        unsafe_repo = self.root / "unsafe-workflow"
        unsafe_commit = init_repo(unsafe_repo, {self.fixture.input_path: unsafe_patch})
        self.fixture.data["reference_workflow"] = unsafe_commit
        self.fixture.data["profiles"][0]["input_sha256"] = hashlib.sha256(
            unsafe_patch.encode()).hexdigest()
        self.fixture.write_config()
        unsafe_output = self.root / "unsafe-path"
        with self.assertRaises(sync.SyncError):
            sync.generate(self.fixture.config, unsafe_repo, self.fixture.susfs,
                          self.fixture.cache, self.fixture.converter, unsafe_output)
        self.assertFalse(unsafe_output.exists())

        unknown = self.root / "unknown.patch"
        unknown.write_text(PATCH + "# unreviewed\n")
        converted = self.root / "converted.patch"
        result = subprocess.run(
            ["bash", ROOT / ".github/scripts/susfs_deinlined.sh", unknown, converted],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(converted.exists())

    def test_git_environment_and_gitdir_pointer_cannot_escape(self):
        external_git = self.root / "external.git"
        run(["git", "init", "--bare", "-q", external_git])
        before_external = directory_digest(external_git)
        inherited = {
            "GIT_DIR": str(external_git),
            "GIT_WORK_TREE": str(self.fixture.workflow),
            "GIT_INDEX_FILE": str(self.root / "external-index"),
            "GIT_COMMON_DIR": str(external_git),
        }
        previous = {key: os.environ.get(key) for key in inherited}
        try:
            os.environ.update(inherited)
            self.fixture.generate(self.root / "environment-safe")
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
        self.assertEqual(directory_digest(external_git), before_external)
        self.assertFalse((self.root / "external-index").exists())

        git_pointer = self.fixture.cache / self.fixture.baseline / ".git"
        git_pointer.write_text(f"gitdir: {external_git}\n")
        output = self.root / "gitdir-rejected"
        with self.assertRaises(sync.SyncError):
            self.fixture.generate(output)
        self.assertFalse(output.exists())
        self.assertEqual(directory_digest(external_git), before_external)

    def test_symlink_parent_is_rejected_without_external_writes(self):
        baseline = self.fixture.cache / self.fixture.baseline
        outside = self.root / "outside"
        outside.mkdir()
        sentinel = outside / "sentinel"
        sentinel.write_text("unchanged\n")
        before = directory_digest(outside)
        shutil.rmtree(baseline / "fs")
        os.symlink(outside, baseline / "fs")
        output = self.root / "symlink-rejected"
        with self.assertRaises(sync.SyncError):
            self.fixture.generate(output)
        self.assertFalse(output.exists())
        self.assertEqual(directory_digest(outside), before)

    def test_baseline_mode_mismatch_is_rejected(self):
        filename = self.fixture.cache / self.fixture.baseline / "fs/namei.c"
        filename.chmod(0o600)
        output = self.root / "mode-rejected"
        with self.assertRaises(sync.SyncError):
            self.fixture.generate(output)
        self.assertFalse(output.exists())

    def test_output_paths_cannot_target_protected_or_reserved_locations(self):
        forbidden = ROOT / "sync-output-must-not-exist"
        self.assertFalse(forbidden.exists())
        with self.assertRaises(sync.SyncError):
            self.fixture.generate(forbidden)
        self.assertFalse(forbidden.exists())

        for value in ("report.json", ".git/50.patch", "nested/.git/51.patch"):
            fixture = copy.deepcopy(self.fixture.data)
            fixture["profiles"][0]["output_50"] = value
            self.fixture.config.write_text(json.dumps(fixture, indent=2) + "\n")
            output = self.root / ("rejected-" + value.replace("/", "-"))
            with self.subTest(path=value), self.assertRaises(sync.SyncError):
                self.fixture.generate(output)
            self.assertFalse(output.exists())
        self.fixture.write_config()

    def test_each_reviewed_fix_is_required(self):
        for name, markers in sync.SOURCE_FIXES.items():
            broken = SOURCE.replace(markers[0], "missing", 1)
            with self.subTest(fix=name), self.assertRaises(sync.SyncError):
                sync.validate_fix_coverage(broken, PATCH, PATCH)
        for name, (marker, _) in sync.PATCH_FIXES.items():
            broken = PATCH.replace(marker, "missing")
            with self.subTest(fix=name), self.assertRaises(sync.SyncError):
                sync.validate_fix_coverage(SOURCE, PATCH, broken)

    def test_reviewed_sync_inputs_match_the_production_stack(self):
        config_path = ROOT / ".github/config/susfs-sync.json"
        config = sync.load_config(config_path)
        baselines = sync.load_baseline_manifest(
            config_path.parent / config["baseline_manifest"])
        production = json.loads((ROOT / ".github/config/ksu-stacks.json").read_text())
        self.assertEqual(config["reference_workflow"], production["reference_workflow"])
        patches = {}
        expected_baselines = set()
        for profile in production["profiles"].values():
            for key, patch in profile["patch"].items():
                sources = {item["commit"] for item in profile["kernels"].values()
                           if item["patch_key"] == key}
                patches[patch["path"]] = (profile["commit"], patch["sha256"], sources)
                expected_baselines.update(sources)
        self.assertEqual(len(config["profiles"]), len(patches))
        actual_paths = set()
        for profile in config["profiles"]:
            path_51 = ".github/patches/" + profile["output_51"]
            actual_paths.add(path_51)
            commit, digest, sources = patches[path_51]
            self.assertEqual(profile["susfs_commit"], commit)
            self.assertEqual(set(profile["baselines"]), sources)
            self.assertEqual(hashlib.sha256((ROOT / path_51).read_bytes()).hexdigest(), digest)
            path_50 = ROOT / ".github/patches" / profile["output_50"]
            self.assertEqual(hashlib.sha256(path_50.read_bytes()).hexdigest(),
                             profile["input_sha256"])
        self.assertEqual(actual_paths, set(patches))
        self.assertEqual(set(baselines["baselines"]), expected_baselines)


if __name__ == "__main__":
    unittest.main()
