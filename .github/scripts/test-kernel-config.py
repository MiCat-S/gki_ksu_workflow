#!/usr/bin/env python3
"""Execute the real composite action's config script for all supported modes."""
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import yaml

ROOT = Path(__file__).resolve().parents[2]
action = yaml.safe_load((ROOT / ".github/actions/kernel-config/action.yml").read_text())
script = action["runs"]["steps"][0]["run"]
hooks = {
    "KowSU": ["manual"], "KernelSU-Next": ["manual"], "KernelSU-Official": ["manual"],
    "KernelSU-XX": ["manual", "hookless"], "ReSukiSU": ["manual", "tracepoint"],
}
with tempfile.TemporaryDirectory() as temp:
    temp = Path(temp)
    environment = os.environ.copy()
    if shutil.which("gsed"):
        (temp / "sed").symlink_to(shutil.which("gsed"))
        environment["PATH"] = str(temp) + os.pathsep + environment["PATH"]
    elif sys.platform == "darwin":
        wrapper = temp / "sed"
        wrapper.write_text('#!/bin/sh\nif [ "$1" = "-i" ]; then shift; exec /usr/bin/sed -i "" "$@"; fi\nexec /usr/bin/sed "$@"\n')
        wrapper.chmod(0o755)
        environment["PATH"] = str(temp) + os.pathsep + environment["PATH"]
    for variant, modes in hooks.items():
        for mode in modes:
            for enabled in ("true", "false"):
                config = temp / "defconfig"
                config.write_text("CONFIG_KSU_SUSFS=y\nCONFIG_KSU_HACK_ARM64_BRANCH_LINK=y\n"
                                  "CONFIG_KSU_KPROBES_KSUD=y\nCONFIG_KSU_TAMPER_SYSCALL_TABLE=y\n"
                                  "CONFIG_KSU_MANUAL_HOOK=y\nCONFIG_KSU_TRACEPOINT_HOOK=y\n")
                build = temp / "build.config.gki"
                build.write_text("check_defconfig\n")
                inputs = {key: str(value.get("default", "")) for key, value in action["inputs"].items()}
                inputs.update(defconfig_path=str(config), build_config_path=str(build),
                              variant=variant, hook_mode=mode, enable_susfs=enabled,
                              localversion="-test")
                run = re.sub(r"\$\{\{ inputs\.(\w+) \}\}", lambda m: inputs[m[1]], script)
                assert "${{" not in run
                subprocess.run(["bash", "-euo", "pipefail", "-c", run], env=environment, check=True)
                resolved = {}
                for line in config.read_text().splitlines():
                    if line.startswith("CONFIG_"):
                        key, value = line.split("=", 1)
                        resolved[key] = value
                    elif line.startswith("# CONFIG_") and line.endswith(" is not set"):
                        resolved[line[2:].split()[0]] = "n"
                assert resolved["CONFIG_KSU_SUSFS"] == ("y" if enabled == "true" else "n")
                if variant == "KernelSU-XX":
                    assert resolved["CONFIG_KSU_HACK_ARM64_BRANCH_LINK"] == ("y" if mode == "hookless" else "n")
                    assert resolved["CONFIG_KSU_TAMPER_SYSCALL_TABLE"] == "n"
                    assert resolved["CONFIG_KSU_KPROBES_KSUD"] == "n"
                if variant == "ReSukiSU":
                    assert resolved["CONFIG_KSU_MANUAL_HOOK"] == ("y" if mode == "manual" else "n")
                    assert resolved["CONFIG_KSU_TRACEPOINT_HOOK"] == ("y" if mode == "tracepoint" else "n")
                print(f"PASS {variant} {mode} SUSFS={enabled}")
