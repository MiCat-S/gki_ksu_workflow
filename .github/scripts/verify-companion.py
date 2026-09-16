#!/usr/bin/env python3
"""Compare standalone and APK-embedded ARM64 ksud after Gradle stripping."""
import io
import json
from pathlib import Path
import sys
from zipfile import ZipFile
from elftools.elf.elffile import ELFFile


def allocated(elf):
    fields = ("sh_type", "sh_flags", "sh_addr", "sh_offset", "sh_size", "sh_addralign", "sh_entsize")
    return {s.name: (tuple(s[f] for f in fields), s.data())
            for s in elf.iter_sections() if s["sh_flags"] & 2}


def verify(root):
    standalone = (root / "ksud").read_bytes()
    original = ELFFile(io.BytesIO(standalone))
    assert original["e_machine"] == "EM_AARCH64"
    verified = []
    for apk in sorted(root.glob("*.apk")):
        with ZipFile(apk) as archive:
            assert archive.testzip() is None, apk
            name = "lib/arm64-v8a/libksud.so"
            if name not in archive.namelist():
                continue
            embedded = archive.read(name)
        packaged = ELFFile(io.BytesIO(embedded))
        for key in original.header:
            if key not in {"e_shoff", "e_shnum", "e_shstrndx"}:
                assert original[key] == packaged[key], (apk, key)
        segments, other = list(original.iter_segments()), list(packaged.iter_segments())
        assert len(segments) == len(other)
        for first, second in zip(segments, other):
            assert first.header == second.header, apk
            if first["p_type"] == "PT_LOAD":
                start = max(first["p_offset"], original["e_ehsize"])
                end = first["p_offset"] + first["p_filesz"]
                assert standalone[start:end] == embedded[start:end], apk
        assert allocated(original) == allocated(packaged), apk
        verified.append(apk.name)
    assert verified, "No APK contains the ARM64 companion"
    result = dict(json.loads((root / "source.json").read_text()),
                  apk_runtime_verified=verified, allocated_sections=len(allocated(original)))
    (root / "verification.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    verify(Path(sys.argv[1]))
