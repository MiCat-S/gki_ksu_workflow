#!/usr/bin/env python3
"""Verify the resolved .config, not just the requested defconfig fragment."""
from pathlib import Path
import sys


def check(path, variant, susfs, hook):
    values = dict(line.split("=", 1) for line in path.read_text().splitlines()
                  if line.startswith("CONFIG_") and "=" in line)

    def expect(name, enabled):
        actual = values.get(f"CONFIG_{name}", "n")
        if actual != ("y" if enabled else "n"):
            raise ValueError(f"{name} resolved to {actual}, expected {'y' if enabled else 'n'}")

    expect("KSU", True)
    expect("KSU_SUSFS", susfs)
    if susfs:
        for feature in ("SUS_PATH", "SUS_MOUNT", "SUS_KSTAT", "OPEN_REDIRECT", "SUS_MAP"):
            expect(f"KSU_SUSFS_{feature}", True)
    if variant == "KernelSU-XX":
        expect("KSU_HACK_ARM64_BRANCH_LINK", hook == "hookless")
        expect("KSU_KPROBES_KSUD", False)
        expect("KSU_TAMPER_SYSCALL_TABLE", False)
    if variant == "ReSukiSU":
        expect("KSU_MANUAL_HOOK", hook == "manual")
        expect("KSU_TRACEPOINT_HOOK", hook == "tracepoint")


if __name__ == "__main__":
    try:
        check(Path(sys.argv[1]), sys.argv[2], sys.argv[3] == "true", sys.argv[4])
    except ValueError as error:
        sys.exit(f"Resolved Kconfig mismatch: {error}")
    print("Resolved Kconfig matches the requested reviewed stack")
