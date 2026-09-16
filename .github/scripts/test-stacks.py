#!/usr/bin/env python3
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f".github/scripts/{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


resolver = load("resolve-stack")
interface = load("check-susfs-interface")


class StackTests(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads((ROOT / ".github/config/ksu-stacks.json").read_text())
        self.config = json.loads((ROOT / ".github/config/kernel_versions.json").read_text())
        # Resolver logic can be tested independently of pending source delivery.
        self.fixture = copy.deepcopy(self.manifest)
        self.fixture["variants"]["KernelSU-XX"] = dict(
            base="1" * 40, source_spec="backslashxx/KernelSU:master", branch="xx",
            prefix="kernelsu_xx", extra=dict(commit="2" * 40, tree="3" * 40),
            integration=dict(commit="4" * 40, tree="5" * 40))

    def resolve(self, **kwargs):
        args = dict(variant="KernelSU-XX", kernel="6.12", sublevel="23", susfs=True)
        args.update(kwargs)
        return resolver.resolve(self.fixture, self.config, root=ROOT, **args)

    def test_all_kernel_profiles_are_paired(self):
        for kernel, config in self.config.items():
            for sublevel in config["revisions"]:
                for susfs in (False, True):
                    result = self.resolve(kernel=kernel, sublevel=sublevel, susfs=susfs)
                    self.assertEqual(result["ksu_commit"], ("4" if susfs else "2") * 40)
                    self.assertEqual(bool(result["susfs_commit"]), susfs)

    def test_original_failing_pair_is_rejected(self):
        with self.assertRaises(ValueError):
            self.resolve(override="7d91da2d2ce056d1abf378d9199aaf1072d37ab0")

    def test_source_and_hook_overrides_are_not_silently_accepted(self):
        for kwargs in (dict(source="other/repo:main"), dict(source="; echo injected"),
                       dict(hook="tracepoint"), dict(override="main")):
            with self.assertRaises(ValueError):
                self.resolve(**kwargs)

    def test_known_explicit_sha_and_defaults_are_identical(self):
        result = self.resolve()
        self.assertEqual(result, self.resolve(
            source="backslashxx/KernelSU:" + "1" * 40,
            override=result["susfs_commit"]))

    def test_kernel_config_drift_is_rejected(self):
        self.config["6.12"]["revisions"]["23"]["commit"] = "6" * 40
        with self.assertRaises(ValueError):
            self.resolve()

    def test_unreviewed_patch_is_rejected(self):
        self.fixture["profiles"]["android16-6.12"]["patch"]["23"]["sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            self.resolve()

    def test_unknown_revision_is_rejected(self):
        with self.assertRaises(KeyError):
            self.resolve(sublevel="92")

    def test_complete_manifest(self):
        self.assertEqual(set(self.manifest["variants"]),
                         {"KowSU", "KernelSU-Next", "KernelSU-Official", "ReSukiSU", "KernelSU-XX"})
        for name in self.manifest["variants"]:
            for kernel, config in self.config.items():
                for sublevel in config["revisions"]:
                    for susfs in (False, True):
                        resolver.resolve(self.manifest, self.config, name, kernel, sublevel, susfs)

    def test_generated_patches_are_reproducible(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "generated.patch"
            for profile in self.manifest["profiles"].values():
                for item in profile["patch"].values():
                    generated = ROOT / item["path"]
                    original = Path(str(generated).replace("51_susfs_deinlined", "50_add_susfs"))
                    subprocess.run(["bash", str(ROOT / ".github/scripts/susfs_deinlined.sh"),
                                    str(original), str(output)], check=True, capture_output=True)
                    self.assertEqual(output.read_bytes(), generated.read_bytes())
                    subprocess.run(["git", "apply", "--numstat", str(generated)],
                                   check=True, capture_output=True)
                    for removed in ("susfs_open_redirect_spoof_seq_show",
                                    "susfs_open_redirect_spoof_vfs_statfs"):
                        self.assertFalse(removed in generated.read_text(), removed)
            output.write_text("malformed\n")
            rejected = Path(temporary) / "must-not-exist.patch"
            result = subprocess.run(["bash", str(ROOT / ".github/scripts/susfs_deinlined.sh"),
                                     str(output), str(rejected)], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(rejected.exists())

    def test_identical_commit_mirror_fallback(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "source"
            repo.mkdir()
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            (repo / "file").write_text("pinned")
            subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
            subprocess.run(["git", "-C", str(repo), "-c", "user.name=Test",
                            "-c", "user.email=test@example.invalid", "commit", "-qm", "fixture"], check=True)
            sha = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
            dest = Path(temp) / "destination"
            script = str(ROOT / ".github/scripts/fetch-pinned.sh")
            subprocess.run(["bash", script, str(dest), sha, str(Path(temp) / "missing"), str(repo)],
                           check=True, capture_output=True)
            self.assertEqual((dest / "file").read_text(), "pinned")
            rejected = subprocess.run(["bash", script, str(Path(temp) / "wrong"), "0" * 40, str(repo)],
                                      capture_output=True)
            self.assertNotEqual(rejected.returncode, 0)
            self.assertFalse((Path(temp) / "wrong").exists())


if __name__ == "__main__":
    unittest.main()
