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
    "security_header": (
        "#include <linux/security.h>",
    ),
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

SUSFS_REVIEWED_INCLUDE_PREFIX = tuple("""#include <linux/version.h>
#include <linux/cred.h>
#include <linux/fs.h>
#include <linux/slab.h>
#include <linux/seq_file.h>
#include <linux/printk.h>
#include <linux/namei.h>
#include <linux/list.h>
#include <linux/init_task.h>
#include <linux/mutex.h>
#include <linux/seqlock.h>
#include <linux/stat.h>
#include <linux/uaccess.h>
#include <linux/version.h>
#include <linux/fdtable.h>
#include <linux/statfs.h>
#include <linux/random.h>
#include <linux/kthread.h>
#include <linux/delay.h>
#include <linux/workqueue.h>
#include <linux/fsnotify_backend.h>
#include <linux/jump_label.h>
#include <linux/security.h>
#include <linux/susfs.h>
#include "fuse/fuse_i.h"
#include "mount.h"
""".splitlines())

CLONE_MNT_REVIEWED_PRELUDE = "}\nEXPORT_SYMBOL_GPL(vfs_submount);\n\n"

CLONE_MNT_REVIEWED_PREFIX = tuple(line.strip() for line in """
static struct mount *clone_mnt(struct mount *old, struct dentry *root,
int flag)
{
struct super_block *sb = old->mnt.mnt_sb;
struct mount *mnt;
int err;
#ifdef CONFIG_KSU_SUSFS_SUS_MOUNT
bool is_mnt_ksu_unshared = false;

// - We will just stop checking for ksu process if /sdcard/Android is accessible,
//   for the sake of performance
if (static_branch_unlikely(&susfs_is_sdcard_android_data_not_decrypted)) {
// - If /sdcard/Android is still not accessible, we keep checking for mounts
//   mounted by ksu process
if (susfs_is_current_ksu_domain()) {
// - If it is unsharing, we re-use the old->mnt_id assign it for mnt->mnt_id directly
//   without going thru ida, but we need to set a bit VFSMOUNT_MNT_FLAGS_KSU_UNSHARED_MNT
//   on mnt->mnt.mnt_flags below, otherwise we find no other ways to identify if this
//   mnt->mnt_id is assigned without ida when it is being freed in mnt_free_id().
if (flag & CL_COPY_MNT_NS) {
mnt = susfs_alloc_unshare_ksu_vfsmnt(old->mnt_devname, old->mnt_id);
is_mnt_ksu_unshared = true;
goto bypass_orig_flow;
}
// else we just go assign fake mnt_id starting with DEFAULT_KSU_MNT_ID
mnt = susfs_alloc_non_unshare_ksu_vfsmnt(old->mnt_devname);
goto bypass_orig_flow;
}
}

// - We keep checking all processes and if old->mnt_id >= DEFAULT_KSU_MNT_ID,
//   go assign fake mnt_id starting with DEFAULT_KSU_MNT_ID
if (old->mnt_id >= DEFAULT_KSU_MNT_ID) {
mnt = susfs_alloc_non_unshare_ksu_vfsmnt(old->mnt_devname);
goto bypass_orig_flow;
}
#endif // #ifdef CONFIG_KSU_SUSFS_SUS_MOUNT

mnt = alloc_vfsmnt(old->mnt_devname);
#ifdef CONFIG_KSU_SUSFS_SUS_MOUNT
bypass_orig_flow:
#endif // #ifdef CONFIG_KSU_SUSFS_SUS_MOUNT
if (!mnt)
return ERR_PTR(-ENOMEM);

if (flag & (CL_SLAVE | CL_PRIVATE | CL_SHARED_TO_SLAVE))
mnt->mnt_group_id = 0; /* not a peer of original */
else
mnt->mnt_group_id = old->mnt_group_id;

if ((flag & CL_MAKE_SHARED) && !mnt->mnt_group_id) {
err = mnt_alloc_group_id(mnt);
if (err)
goto out_free;
}

mnt->mnt.mnt_flags = old->mnt.mnt_flags;
mnt->mnt.mnt_flags &= ~(MNT_WRITE_HOLD|MNT_MARKED|MNT_INTERNAL);

#ifdef CONFIG_KSU_SUSFS_SUS_MOUNT
if (unlikely(is_mnt_ksu_unshared))
mnt->mnt.mnt_flags |= VFSMOUNT_MNT_FLAGS_KSU_UNSHARED_MNT;
#endif // #ifdef CONFIG_KSU_SUSFS_SUS_MOUNT

atomic_inc(&sb->s_active);""".strip("\n").splitlines())

CLONE_MNT_REVIEWED_SUFFIX = """
	return mnt;

 out_free:
	mnt_free_id(mnt);
	free_vfsmnt(mnt);
	return ERR_PTR(err);
}""" + "\n\n"

STATIC_KEY_CALL_RE = re.compile(
    r"\bstatic_branch_unlikely\s*\(\s*"
    r"&susfs_is_sdcard_android_data_not_decrypted\s*\)", re.MULTILINE)


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


def select_patch_files(patch_text, filenames, label):
    wanted = {relative_path(name).as_posix() for name in filenames}
    selected = []
    found = set()
    for part in re.split(r"(?=^diff --git )", patch_text, flags=re.MULTILINE):
        match = re.match(r"^diff --git a/(\S+) b/(\S+)$", part, re.MULTILINE)
        if not match or match.group(1) not in wanted:
            continue
        filename = match.group(1)
        if match.group(2) != filename or filename in found:
            raise SyncError(f"{label}: ambiguous patch section for {filename}")
        selected.append(part)
        found.add(filename)
    missing = sorted(wanted - found)
    if missing:
        raise SyncError(f"{label}: missing source patch sections: {missing}")
    return "".join(selected).encode()


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


def validate_applied_source(namespace_text, susfs_text, label):
    susfs_lines = tuple(line.strip() for line in susfs_text.splitlines())
    if susfs_lines[:len(SUSFS_REVIEWED_INCLUDE_PREFIX)] != SUSFS_REVIEWED_INCLUDE_PREFIX:
        raise SyncError(
            f"{label}: fs/susfs.c reviewed include prefix is not active at file start")
    security_headers = re.findall(
        r"(?m)^#include <linux/security\.h>[ \t]*$", susfs_text)
    if len(security_headers) != 1:
        raise SyncError(f"{label}: fs/susfs.c must include linux/security.h exactly once")

    starts = list(re.finditer(
        r"(?m)^static struct mount \*clone_mnt\(", namespace_text))
    if len(starts) != 1:
        raise SyncError(f"{label}: expected one clone_mnt definition")
    start = starts[0].start()
    end_match = re.search(
        r"(?m)^static void cleanup_mnt\(", namespace_text[starts[0].end():])
    if not end_match:
        raise SyncError(f"{label}: clone_mnt boundary before cleanup_mnt is missing")
    end = starts[0].end() + end_match.start()
    clone_mnt = namespace_text[start:end]
    if not namespace_text[:start].endswith(CLONE_MNT_REVIEWED_PRELUDE):
        raise SyncError(f"{label}: clone_mnt reviewed live-code prelude changed")
    clone_lines = tuple(line.strip() for line in clone_mnt.splitlines())
    if clone_lines[:len(CLONE_MNT_REVIEWED_PREFIX)] != CLONE_MNT_REVIEWED_PREFIX:
        raise SyncError(f"{label}: clone_mnt reviewed live-code prefix changed")
    if not clone_mnt.endswith(CLONE_MNT_REVIEWED_SUFFIX):
        raise SyncError(f"{label}: clone_mnt reviewed live-code suffix changed")

    declaration_matches = list(re.finditer(
        r"(?m)^[ \t]*bool is_mnt_ksu_unshared = false;[ \t]*$", clone_mnt)
    )
    if len(declaration_matches) != 1:
        raise SyncError(
            f"{label}: clone_mnt must initialize is_mnt_ksu_unshared to false")

    assignments = re.findall(
        r"(?m)^[ \t]*is_mnt_ksu_unshared[ \t]*=[^;\n]+;[ \t]*$", clone_mnt)
    if (len(assignments) != 1 or
            assignments[0].strip() != "is_mnt_ksu_unshared = true;"):
        raise SyncError(
            f"{label}: clone_mnt must record one true unshared-allocation decision")

    allocation_sequence = re.compile(
        r"(?m)^[ \t]*mnt = susfs_alloc_unshare_ksu_vfsmnt\([^;\n]+\);[ \t]*\n"
        r"^[ \t]*is_mnt_ksu_unshared = true;[ \t]*\n"
        r"^[ \t]*goto bypass_orig_flow;[ \t]*$")
    allocation_matches = list(allocation_sequence.finditer(clone_mnt))
    allocation_calls = re.findall(
        r"(?m)^[ \t]*mnt = susfs_alloc_unshare_ksu_vfsmnt\([^;\n]+\);[ \t]*$",
        clone_mnt)
    if len(allocation_calls) != 1 or len(allocation_matches) != 1:
        raise SyncError(
            f"{label}: the true record must immediately follow the unshared allocation")

    flag_sequence = re.compile(
        r"(?m)^[ \t]*if \(unlikely\(is_mnt_ksu_unshared\)\)[ \t]*\n"
        r"^[ \t]*mnt->mnt\.mnt_flags \|= VFSMOUNT_MNT_FLAGS_KSU_UNSHARED_MNT;[ \t]*$")
    flag_matches = list(flag_sequence.finditer(clone_mnt))
    flag_writes = re.findall(
        r"(?m)^[ \t]*mnt->mnt\.mnt_flags \|= "
        r"VFSMOUNT_MNT_FLAGS_KSU_UNSHARED_MNT;[ \t]*$", clone_mnt)
    if len(flag_writes) != 1 or len(flag_matches) != 1:
        raise SyncError(
            f"{label}: KSU_UNSHARED_MNT must be set from the recorded decision")

    bypass = re.search(r"(?m)^bypass_orig_flow:[ \t]*$", clone_mnt)
    flags_reset = clone_mnt.find("mnt->mnt.mnt_flags &=")
    if (not bypass or flags_reset < 0 or
            not declaration_matches[0].start() < allocation_matches[0].start() <
            bypass.start() < flags_reset < flag_matches[0].start()):
        raise SyncError(f"{label}: clone_mnt allocation/flag control-flow order changed")
    static_key_calls = STATIC_KEY_CALL_RE.findall(clone_mnt)
    if len(static_key_calls) != 1:
        raise SyncError(
            f"{label}: clone_mnt must have exactly one reviewed static-key decision")

    return {
        "security_header": True,
        "clone_mnt_false_initialization": True,
        "clone_mnt_unshare_recording": True,
        "clone_mnt_recorded_flag_gate": True,
    }


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


def strict_replay(patch_data, baseline_path, baseline_manifest, patch_label,
                  susfs_source_text):
    baseline_path = Path(os.path.abspath(baseline_path))
    verified_files = verify_partial_tree(baseline_path, baseline_manifest)
    with tempfile.TemporaryDirectory(prefix="susfs-replay-") as temporary:
        checkout = Path(temporary) / "kernel"
        materialize_partial_tree(verified_files, checkout)
        dry_run = run(
            ["patch", "--dry-run", "--batch", "--forward", "--fuzz=0",
             "-p1", "-d", checkout],
            input_data=patch_data, check=False,
        )
        dry_output = dry_run.stdout.decode("utf-8", errors="replace")
        if dry_run.returncode:
            raise SyncError(
                f"{patch_label} strict patch replay failed on {baseline_path.name}\n"
                f"{dry_output.strip()}")
        if OFFSET_RE.search(dry_output):
            raise SyncError(
                f"{patch_label} offset or fuzz detected on {baseline_path.name}\n"
                f"{dry_output.strip()}")

        run(["git", "init", "-q", checkout])
        run(["git", "-C", checkout, "add", "-A"])
        check = run(
            ["git", "-C", checkout, "apply", "--check", "--verbose", "-"],
            input_data=patch_data)
        check_output = check.stdout.decode("utf-8", errors="replace")
        if OFFSET_RE.search(check_output):
            raise SyncError(
                f"{patch_label} git apply reported offset or fuzz on {baseline_path.name}\n"
                f"{check_output.strip()}")
        run(["git", "-C", checkout, "apply", "--index", "-"], input_data=patch_data)
        applied_checks = validate_applied_source(
            (checkout / "fs/namespace.c").read_text(),
            susfs_source_text,
            f"{patch_label} patch on {baseline_path.name}",
        )
        tree = run(["git", "-C", checkout, "write-tree"]).stdout.decode().strip()
        duplicate = run(
            ["git", "-C", checkout, "apply", "--check", "-"],
            input_data=patch_data, check=False)
        if duplicate.returncode == 0:
            raise SyncError(
                f"{patch_label} duplicate patch application was accepted on "
                f"{baseline_path.name}")
        return {
            "result_partial_tree": tree,
            "offset": 0,
            "fuzz": 0,
            "applied_source_checks": applied_checks,
        }


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
            patch_50_source_data = select_patch_files(
                patch_50, ("fs/namespace.c",), f"{name} input")

            baselines = []
            for baseline in profile["baselines"]:
                baseline = require_sha(baseline)
                try:
                    baseline_manifest = baseline_data["baselines"][baseline]
                except KeyError as error:
                    raise SyncError(f"{name}: unreviewed kernel baseline key {baseline}") from error
                replays = {}
                replay_inputs = (
                    ("50", patch_50_source_data, "selected-source-files",
                     ["fs/namespace.c"]),
                    ("51", patch_51_data, "full-patch", None),
                )
                for patch_label, patch_data, scope, files in replay_inputs:
                    replay = strict_replay(
                        patch_data, kernel_cache / baseline, baseline_manifest,
                        patch_label, source_text)
                    replay["patch_scope"] = scope
                    if files:
                        replay["files"] = files
                    replays[patch_label] = replay
                baselines.append({
                    "cache_key": baseline,
                    "tree_kind": "partial",
                    "file_count": baseline_manifest["file_count"],
                    "manifest_sha256": baseline_manifest_hash(baseline_manifest),
                    "replays": replays,
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
