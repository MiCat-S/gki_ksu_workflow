#!/usr/bin/env python3
"""Reject known SUSFS interface mismatches before expensive compilation."""
from pathlib import Path
import re
import sys


def check(root):
    header = (root / "include/linux/susfs.h").read_text()
    implementation = (root / "fs/susfs.c").read_text()
    for name, bit in (("KSTAT_SPOOF_CTIME_TV_SEC", 8), ("KSTAT_SPOOF_CTIME_TV_NSEC", 9)):
        if not re.search(rf"^#define\s+{name}\s+\(1\s*<<\s*{bit}\)", header, re.M):
            raise ValueError(f"Incompatible userspace ABI: {name}")
    removed = ("susfs_open_redirect_spoof_seq_show", "susfs_open_redirect_spoof_vfs_statfs")
    for file in ("fs/proc/fd.c", "fs/statfs.c", "fs/susfs.c", "include/linux/susfs.h"):
        text = (root / file).read_text()
        if any(name in text for name in removed):
            raise ValueError(f"Removed OPEN_REDIRECT interface remains in {file}")
    for name in ("susfs_add_sus_path", "susfs_add_sus_kstat", "susfs_add_open_redirect",
                 "susfs_add_sus_map", "susfs_add_try_umount"):
        if not re.search(rf"\bvoid\s+{name}\s*\(", implementation):
            raise ValueError(f"Missing SUSFS implementation: {name}")
    if not re.search(r"obj-\$\(CONFIG_KSU_SUSFS\)\s*\+=\s*susfs.o", (root / "fs/Makefile").read_text()):
        raise ValueError("SUSFS object is not wired into the build")


if __name__ == "__main__":
    try:
        check(Path(sys.argv[1]))
    except (ValueError, OSError) as error:
        sys.exit(f"SUSFS interface preflight failed: {error}")
    print("SUSFS interface preflight passed (compile/link verification still required)")
