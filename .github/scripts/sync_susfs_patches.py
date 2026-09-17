#!/usr/bin/env python3
"""Generate reviewed SUSFS patch candidates without mutating input repositories."""

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[2]
SHA_RE = re.compile(r"[0-9a-f]{40}")
SHA256_RE = re.compile(r"[0-9a-f]{64}")
INLINE_HOOK_RE = re.compile(r"\b(?:ksu_handle_|ksu_hook_)\w+\b")
OFFSET_RE = re.compile(r"\b(?:offset|fuzz)\b", re.IGNORECASE)

SOURCE_FIXES = {
    "free_missing_kstat_entry": (
        "mutex_unlock(&susfs_mutex_lock_sus_kstat);\n\tkfree(new_entry);\n\tinfo.err = -ENOENT;",
    ),
    "snapshot_cmdline_once": (
        "strscpy(buf, fake_cmdline_or_bootconfig, SUSFS_FAKE_CMDLINE_OR_BOOTCONFIG_SIZE);",
        "seq_puts(m, buf);",
        "kfree(buf);",
    ),
}
PATCH_FIXES = {
    "nested_redirect_lookup": ("filename_lookup(old_dfd, fake_filename", 2),
    "ordinary_mount_fast_path": ("if (mnt->mnt_id < DEFAULT_KSU_MNT_ID)", 2),
    "restore_nameidata_before_putname": ("nd->name = old_name;", 1),
}


class SyncError(RuntimeError):
    pass


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def require_sha(value, size=40):
    pattern = SHA_RE if size == 40 else SHA256_RE
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise SyncError(f"expected a full {size}-digit lowercase hash, got {value!r}")
    return value


def relative_path(value):
    if isinstance(value, PurePosixPath):
        path = value
    elif isinstance(value, str):
        path = PurePosixPath(value)
    else:
        raise SyncError(f"unsafe relative path: {value!r}")
    if (path.is_absolute() or ".." in path.parts or ".git" in path.parts or
            not path.parts):
        raise SyncError(f"unsafe relative path: {value!r}")
    return path


def isolated_environment():
    environment = {key: value for key, value in os.environ.items()
                   if not key.startswith("GIT_")}
    environment.update({
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "core.hooksPath",
        "GIT_CONFIG_VALUE_0": os.devnull,
        "GIT_NO_REPLACE_OBJECTS": "1",
    })
    return environment


def run(command, *, cwd=None, input_data=None, check=True):
    result = subprocess.run(
        [str(item) for item in command], cwd=cwd, input=input_data,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
        env=isolated_environment(),
    )
    if check and result.returncode:
        output = result.stdout.decode("utf-8", errors="replace").strip()
        raise SyncError(f"command failed ({result.returncode}): {' '.join(map(str, command))}\n{output}")
    return result


def git_blob(repository, commit, filename):
    repository = Path(repository).resolve()
    require_sha(commit)
    filename = relative_path(filename)
    run(["git", "-C", repository, "cat-file", "-e", f"{commit}^{{commit}}"])
    return run(["git", "-C", repository, "show", f"{commit}:{filename.as_posix()}"]).stdout


def canonical_patch(data, label):
    if b"\x00" in data:
        raise SyncError(f"{label}: NUL byte in patch")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise SyncError(f"{label}: patch is not UTF-8") from error
    if "\r" in text or not text.endswith("\n"):
        raise SyncError(f"{label}: patch must use LF and end with a newline")
    file_headers = re.findall(r"^diff --git a/(\S+) b/(\S+)$", text, re.MULTILINE)
    if not file_headers or not re.search(r"^@@ -\d", text, re.MULTILINE):
        raise SyncError(f"{label}: malformed unified Git patch")
    for source, target in file_headers:
        source_path = relative_path(source)
        target_path = relative_path(target)
        if source_path != target_path:
            raise SyncError(f"{label}: rename patches are not supported")
    return text


def validate_fix_coverage(source_text, patch_50, patch_51):
    coverage = {}
    for name, markers in SOURCE_FIXES.items():
        if not all(marker in source_text for marker in markers):
            raise SyncError(f"missing reviewed SUSFS source fix: {name}")
        coverage[name] = True
    if "seq_puts(m, fake_cmdline_or_bootconfig);" in source_text:
        raise SyncError("cmdline output still occurs inside the seqlock retry loop")
    for name, (marker, minimum) in PATCH_FIXES.items():
        for label, text in (("50", patch_50), ("51", patch_51)):
            if text.count(marker) < minimum:
                raise SyncError(f"{label} patch lost reviewed kernel fix: {name}")
        coverage[name] = True
    hooks = sorted(set(INLINE_HOOK_RE.findall(patch_51)))
    if hooks:
        raise SyncError(f"de-inlined patch still contains inline KSU hooks: {hooks}")
    return coverage


def run_converter(converter, source_patch, output_patch):
    result = run(["bash", converter, source_patch, output_patch], check=False)
    if result.returncode:
        output = result.stdout.decode("utf-8", errors="replace").strip()
        raise SyncError(f"de-inline conversion failed\n{output}")
    if not output_patch.is_file():
        raise SyncError("converter succeeded without producing an output patch")


def load_baseline_manifest(filename):
    try:
        manifest = json.loads(Path(filename).read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise SyncError(f"cannot read baseline manifest: {error}") from error
    if (manifest.get("schema") != 1 or manifest.get("tree_kind") != "partial" or
            not isinstance(manifest.get("baselines"), dict)):
        raise SyncError("unsupported kernel baseline manifest")
    return manifest


def baseline_manifest_hash(entry):
    canonical = json.dumps(entry, sort_keys=True, separators=(",", ":")).encode()
    return sha256(canonical)


def verify_partial_tree(root, manifest):
    root = Path(root)
    if not isinstance(manifest, dict):
        raise SyncError("invalid partial-tree baseline entry")
    try:
        root_stat = root.lstat()
    except FileNotFoundError as error:
        raise SyncError(f"missing kernel baseline cache: {root}") from error
    if stat.S_ISLNK(root_stat.st_mode) or not stat.S_ISDIR(root_stat.st_mode):
        raise SyncError(f"kernel baseline root is not a real directory: {root}")
    expected = manifest.get("files")
    if not isinstance(expected, dict) or manifest.get("file_count") != len(expected):
        raise SyncError("invalid partial-tree file manifest")
    for name, metadata in expected.items():
        relative_path(name)
        if (not isinstance(metadata, dict) or
                metadata.get("mode") not in ("100644", "100755")):
            raise SyncError(f"invalid mode metadata for {name}")
        require_sha(metadata.get("sha256"), 64)

    verified = {}

    def walk(directory, prefix=PurePosixPath()):
        try:
            entries = sorted(os.scandir(directory), key=lambda item: item.name)
        except OSError as error:
            raise SyncError(f"cannot scan baseline directory {directory}: {error}") from error
        for item in entries:
            relative = prefix / item.name
            if item.name == ".git":
                raise SyncError(f"baseline contains forbidden .git entry: {relative}")
            try:
                item_stat = item.stat(follow_symlinks=False)
            except OSError as error:
                raise SyncError(f"cannot stat baseline entry {relative}: {error}") from error
            if stat.S_ISLNK(item_stat.st_mode):
                raise SyncError(f"baseline contains symlink: {relative}")
            if stat.S_ISDIR(item_stat.st_mode):
                walk(Path(item.path), relative)
                continue
            if not stat.S_ISREG(item_stat.st_mode):
                raise SyncError(f"baseline contains special file: {relative}")
            key = relative.as_posix()
            if key not in expected:
                raise SyncError(f"baseline contains unreviewed file: {key}")
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            try:
                descriptor = os.open(item.path, flags)
                with os.fdopen(descriptor, "rb") as source:
                    opened_stat = os.fstat(source.fileno())
                    if (not stat.S_ISREG(opened_stat.st_mode) or
                            (opened_stat.st_dev, opened_stat.st_ino) !=
                            (item_stat.st_dev, item_stat.st_ino)):
                        raise SyncError(f"baseline entry changed during verification: {key}")
                    data = source.read()
            except OSError as error:
                raise SyncError(f"cannot safely read baseline file {key}: {error}") from error
            metadata = expected[key]
            expected_permissions = 0o755 if metadata["mode"] == "100755" else 0o644
            if (stat.S_IMODE(item_stat.st_mode) != expected_permissions or
                    stat.S_IMODE(opened_stat.st_mode) != expected_permissions or
                    sha256(data) != metadata["sha256"]):
                raise SyncError(f"baseline file does not match reviewed manifest: {key}")
            verified[key] = (data, metadata["mode"])

    walk(root)
    missing = sorted(set(expected) - set(verified))
    if missing:
        raise SyncError(f"baseline is missing reviewed files: {missing}")
    return verified


def materialize_partial_tree(files, destination):
    destination.mkdir()
    for name, (data, mode) in files.items():
        target = destination / PurePosixPath(name)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        target.chmod(0o755 if mode == "100755" else 0o644)


def strict_replay(patch_path, baseline_path, baseline_manifest):
    baseline_path = Path(os.path.abspath(baseline_path))
    verified_files = verify_partial_tree(baseline_path, baseline_manifest)
    with tempfile.TemporaryDirectory(prefix="susfs-replay-") as temporary:
        checkout = Path(temporary) / "kernel"
        materialize_partial_tree(verified_files, checkout)
        dry_run = run(
            ["patch", "--dry-run", "--batch", "--forward", "--fuzz=0",
             "-p1", "-d", checkout],
            input_data=patch_path.read_bytes(), check=False,
        )
        dry_output = dry_run.stdout.decode("utf-8", errors="replace")
        if dry_run.returncode:
            raise SyncError(f"strict patch replay failed on {baseline_path.name}\n{dry_output.strip()}")
        if OFFSET_RE.search(dry_output):
            raise SyncError(f"offset or fuzz detected on {baseline_path.name}\n{dry_output.strip()}")

        run(["git", "init", "-q", checkout])
        run(["git", "-C", checkout, "add", "-A"])
        check = run(["git", "-C", checkout, "apply", "--check", "--verbose", patch_path])
        check_output = check.stdout.decode("utf-8", errors="replace")
        if OFFSET_RE.search(check_output):
            raise SyncError(f"git apply reported offset or fuzz on {baseline_path.name}")
        run(["git", "-C", checkout, "apply", "--index", patch_path])
        tree = run(["git", "-C", checkout, "write-tree"]).stdout.decode().strip()
        duplicate = run(["git", "-C", checkout, "apply", "--check", patch_path], check=False)
        if duplicate.returncode == 0:
            raise SyncError(f"duplicate patch application was accepted on {baseline_path.name}")
        return tree


def ensure_output_isolated(output, inputs):
    output = output.resolve()
    for item in inputs:
        item = Path(item).resolve()
        if output == item or output.is_relative_to(item):
            raise SyncError(f"candidate output must be outside input tree: {item}")
    if output.exists():
        raise SyncError(f"candidate output already exists: {output}")


def load_config(filename):
    try:
        config = json.loads(Path(filename).read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise SyncError(f"cannot read sync config: {error}") from error
    if config.get("schema") != 1 or not isinstance(config.get("profiles"), list):
        raise SyncError("unsupported SUSFS sync config")
    require_sha(config.get("reference_workflow"))
    relative_path(config.get("baseline_manifest"))
    relative_path(config.get("source_path"))
    if not config["profiles"]:
        raise SyncError("sync config has no profiles")
    names = set()
    for profile in config["profiles"]:
        if not isinstance(profile, dict):
            raise SyncError("sync config profile must be an object")
        name = profile.get("name")
        if not isinstance(name, str) or not name:
            raise SyncError("profile name is required")
        if name in names:
            raise SyncError(f"duplicate profile name: {name}")
        names.add(name)
        baselines = profile.get("baselines")
        if not isinstance(baselines, list) or not baselines:
            raise SyncError(f"{name}: baselines must be a non-empty list")
    return config


def generate(config_path, workflow_repo, susfs_repo, kernel_cache, converter, output):
    config_path = Path(config_path).resolve()
    config = load_config(config_path)
    baseline_manifest_path = config_path.parent / relative_path(config["baseline_manifest"])
    baseline_data = load_baseline_manifest(baseline_manifest_path)
    workflow_repo = Path(workflow_repo).resolve()
    susfs_repo = Path(susfs_repo).resolve()
    kernel_cache = Path(os.path.abspath(kernel_cache))
    if kernel_cache.is_symlink():
        raise SyncError(f"kernel cache root must not be a symlink: {kernel_cache}")
    converter = Path(converter).resolve()
    output = Path(output).resolve()
    if not converter.is_file():
        raise SyncError(f"missing converter: {converter}")
    ensure_output_isolated(
        output,
        (ROOT, workflow_repo, susfs_repo, kernel_cache,
         config_path.parent, converter.parent),
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{output.name}.staging-", dir=output.parent))
    try:
        report = {
            "schema": 1,
            "candidate_only": True,
            "reference_workflow": config["reference_workflow"],
            "converter_sha256": sha256(converter.read_bytes()),
            "baseline_manifest_sha256": sha256(baseline_manifest_path.read_bytes()),
            "profiles": [],
        }
        seen_outputs = set()
        for profile in config["profiles"]:
            name = profile.get("name")
            commit = require_sha(profile.get("susfs_commit"))
            source_data = git_blob(susfs_repo, commit, config["source_path"])
            expected_source = require_sha(profile.get("source_sha256"), 64)
            if sha256(source_data) != expected_source:
                raise SyncError(f"{name}: SUSFS source hash mismatch")
            source_text = source_data.decode("utf-8")

            input_path = relative_path(profile.get("input_path"))
            patch_50_data = git_blob(
                workflow_repo, config["reference_workflow"], input_path)
            expected_input = require_sha(profile.get("input_sha256"), 64)
            if sha256(patch_50_data) != expected_input:
                raise SyncError(f"{name}: upstream patch hash mismatch")
            patch_50 = canonical_patch(patch_50_data, f"{name} input")

            output_50 = relative_path(profile.get("output_50"))
            output_51 = relative_path(profile.get("output_51"))
            for candidate in (output_50, output_51):
                if candidate == PurePosixPath("report.json"):
                    raise SyncError("report.json is reserved for the batch report")
                if candidate in seen_outputs:
                    raise SyncError(f"duplicate candidate output: {candidate}")
                seen_outputs.add(candidate)
            target_50 = stage / output_50
            target_51 = stage / output_51
            target_50.parent.mkdir(parents=True, exist_ok=True)
            target_51.parent.mkdir(parents=True, exist_ok=True)
            target_50.write_bytes(patch_50_data)
            run_converter(converter, target_50, target_51)
            patch_51_data = target_51.read_bytes()
            patch_51 = canonical_patch(patch_51_data, f"{name} generated")
            coverage = validate_fix_coverage(source_text, patch_50, patch_51)

            baselines = []
            for baseline in profile["baselines"]:
                baseline = require_sha(baseline)
                try:
                    baseline_manifest = baseline_data["baselines"][baseline]
                except KeyError as error:
                    raise SyncError(f"{name}: unreviewed kernel baseline key {baseline}") from error
                tree = strict_replay(
                    target_51, kernel_cache / baseline, baseline_manifest)
                baselines.append({
                    "cache_key": baseline,
                    "tree_kind": "partial",
                    "file_count": baseline_manifest["file_count"],
                    "manifest_sha256": baseline_manifest_hash(baseline_manifest),
                    "result_partial_tree": tree,
                    "offset": 0,
                    "fuzz": 0,
                })
            report["profiles"].append({
                "name": name,
                "susfs_commit": commit,
                "susfs_source_sha256": expected_source,
                "patch_50": {"path": output_50.as_posix(), "sha256": sha256(patch_50_data)},
                "patch_51": {"path": output_51.as_posix(), "sha256": sha256(patch_51_data)},
                "fix_coverage": coverage,
                "baselines": baselines,
            })
        (stage / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        os.replace(stage, output)
        return report
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=ROOT / ".github/config/susfs-sync.json", type=Path)
    parser.add_argument("--workflow-repo", required=True, type=Path)
    parser.add_argument("--susfs-repo", required=True, type=Path)
    parser.add_argument("--kernel-cache", required=True, type=Path)
    parser.add_argument("--converter", default=ROOT / ".github/scripts/susfs_deinlined.sh", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        report = generate(args.config, args.workflow_repo, args.susfs_repo,
                          args.kernel_cache, args.converter, args.output)
    except (OSError, UnicodeDecodeError, SyncError) as error:
        parser.exit(1, f"SUSFS sync failed: {error}\n")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
