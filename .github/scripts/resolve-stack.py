#!/usr/bin/env python3
"""Resolve a reviewed, immutable kernel/KSU/SUSFS combination before building."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]


def require_sha(value, size=40):
    if not isinstance(value, str) or not re.fullmatch(rf"[0-9a-f]{{{size}}}", value):
        raise ValueError(f"Expected a full {size}-digit object identity, got {value!r}")
    return value


def resolve(manifest, configs, variant, kernel, sublevel, susfs, source="", override="",
            hook="manual", root=ROOT):
    if manifest["schema"] != 1:
        raise ValueError("Unsupported stack manifest schema")
    stack = manifest["variants"][variant]
    config = configs[kernel]
    revision = config["revisions"][sublevel]
    profile = manifest["profiles"][f'{config["android_version"]}-{kernel}']
    base = require_sha(stack["base"])
    # Public source inputs remain recognizable, but never resolve mutable refs.
    if source not in ("", stack["source_spec"], f'{stack["source_spec"].split(":")[0]}:{base}'):
        raise ValueError("Unreviewed source override; add and validate a complete stack first")
    if variant == "KernelSU-XX" and hook not in ("manual", "hookless"):
        raise ValueError("KernelSU-XX requires manual or hookless hooks")
    if variant == "ReSukiSU" and hook not in ("manual", "tracepoint"):
        raise ValueError("ReSukiSU requires manual or tracepoint hooks")
    susfs_sha = require_sha(profile["commit"])
    if override and (not susfs or override != susfs_sha):
        raise ValueError("SUSFS override is not paired with this reviewed KMI stack")
    snapshot = stack["integration"] if susfs else stack["extra"]
    result = {
        "ksu_repo": manifest["source_repo"],
        "ksu_base": base,
        "ksu_commit": require_sha(snapshot["commit"]),
        "ksu_tree": require_sha(snapshot["tree"]),
        "ksu_branch": stack["branch"],
        "ksu_prefix": stack["prefix"],
        "susfs_commit": susfs_sha if susfs else "",
        "kernel_commit": require_sha(revision["commit"]),
    }
    for key in ("rekernel", "rekernel_x", "anykernel"):
        result[f"{key}_commit"] = require_sha(manifest["auxiliary"][key])
    result["rekernel_x_version"] = manifest["auxiliary"]["rekernel_x_version"]
    kernel_pin = profile["kernels"][sublevel]
    if kernel_pin["commit"] != result["kernel_commit"]:
        raise ValueError("Kernel config changed without a matching stack review")
    result["kernel_archive_sha256"] = require_sha(kernel_pin["archive_sha256"], 64)
    if susfs:
        for key in ("patch", "try_umount_patch"):
            item = profile[key]
            if key == "patch":
                item = item[kernel_pin["patch_key"]]
            path = (root / item["path"]).resolve()
            if not path.is_relative_to(root.resolve()):
                raise ValueError("Patch escapes repository")
            expected = require_sha(item["sha256"], 64)
            if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                raise ValueError(f"Unreviewed patch contents: {path}")
            result[key] = str(path)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant", required=True)
    parser.add_argument("--kernel", required=True)
    parser.add_argument("--sublevel", required=True)
    parser.add_argument("--susfs", choices=("true", "false"), required=True)
    parser.add_argument("--source", default="")
    parser.add_argument("--susfs-commit", default="")
    parser.add_argument("--hook", default="manual")
    args = parser.parse_args()
    try:
        result = resolve(
            json.loads((ROOT / ".github/config/ksu-stacks.json").read_text()),
            json.loads((ROOT / ".github/config/kernel_versions.json").read_text()),
            args.variant, args.kernel, args.sublevel, args.susfs == "true",
            args.source, args.susfs_commit, args.hook,
        )
    except (KeyError, ValueError, OSError) as error:
        parser.exit(1, f"Stack preflight failed: {error}\n")
    print(json.dumps(result, indent=2))
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as output:
            for key, value in result.items():
                if "\n" in value or "\r" in value:
                    raise ValueError("Multiline workflow output is forbidden")
                output.write(f"{key}={value}\n")


if __name__ == "__main__":
    main()
