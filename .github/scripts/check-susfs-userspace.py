#!/usr/bin/env python3
"""Compile ABI assertions using actual kernel and userspace declarations."""
from pathlib import Path
import re
import subprocess
import sys


def struct_body(text, name):
    match = re.search(rf"struct {name} \{{([^{{}}]+)\}};", text)
    if not match:
        raise ValueError(f"Missing plain struct: {name}")
    return match.group(0), match.group(1)


def verify(kernel, userspace, cc):
    ktext = (kernel / "kernel_patches/include/linux/susfs.h").read_text()
    ktext += (kernel / "kernel_patches/include/linux/susfs_def.h").read_text()
    utext = (userspace / "include/susfs.h").read_text()
    ks, kb = struct_body(ktext, "st_susfs_sus_kstat")
    us, ub = struct_body(utext, "sus_kstat_v2100")
    code = "#include <stddef.h>\n#include <stdbool.h>\n"
    code += "#define SUSFS_MAX_LEN_PATHNAME 256\n"
    code += ks + "\n" + us + "\n"
    fields = re.findall(r"\b(\w+)(?:\[[^\]]+\])?;", kb)
    if fields != re.findall(r"\b(\w+)(?:\[[^\]]+\])?;", ub):
        raise ValueError("KSTAT field lists differ")
    code += '_Static_assert(sizeof(struct st_susfs_sus_kstat) == sizeof(struct sus_kstat_v2100), "size");\n'
    for field in fields:
        code += f'_Static_assert(offsetof(struct st_susfs_sus_kstat, {field}) == offsetof(struct sus_kstat_v2100, {field}), "{field} offset");\n'
        code += f'_Static_assert(sizeof(((struct st_susfs_sus_kstat *)0)->{field}) == sizeof(((struct sus_kstat_v2100 *)0)->{field}), "{field} size");\n'
    for name in re.findall(r"^#define (KSTAT_SPOOF_\w+)\b", ktext, re.M):
        values = []
        for text in (ktext, utext):
            match = re.search(rf"^#define {name}\s+(\(1\s*<<\s*\d+\))", text, re.M)
            if not match:
                raise ValueError(f"Missing shifted flag: {name}")
            values.append(match.group(1))
        code += f'_Static_assert({values[0]} == {values[1]}, "{name}");\n'
    for text in (ktext, utext):
        if not re.search(r"^#define SUSFS_MAX_LEN_PATHNAME\s+256\b", text, re.M):
            raise ValueError("Path buffer size changed")
    subprocess.run([cc, "-std=c11", "-Werror", "-fsyntax-only", "-x", "c", "-"],
                   input=code, text=True, check=True)
    print(f"PASS KSTAT ABI: {len(fields)} field offsets/sizes and 12 flags")


if __name__ == "__main__":
    verify(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3])
