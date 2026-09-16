#!/usr/bin/env python3
"""Package the pinned module with a source-built, offline-paired ARM64 tool."""
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError("Pinned module layout changed; replacement requires review")
    return text.replace(old, new, 1)


def package(module, binary, output):
    manifest = json.loads((ROOT / ".github/config/ksu-stacks.json").read_text())
    actual = subprocess.check_output(["git", "-C", str(module), "rev-parse", "HEAD"],
                                     text=True).strip()
    if actual != manifest["userspace"]["module_commit"]:
        raise ValueError("Wrong module source commit")
    elf = binary.read_bytes()
    if elf[:6] != b"\x7fELF\x02\x01" or struct.unpack_from("<H", elf, 18)[0] != 183:
        raise ValueError("SUSFS tool is not an AArch64 ELF64 binary")
    digest = hashlib.sha256(elf).hexdigest()
    dest = output / "module"
    if dest.exists():
        raise ValueError("Refusing to reuse an existing module output directory")
    shutil.copytree(module, dest, ignore=shutil.ignore_patterns(".git", ".github"))
    shutil.copyfile(binary, dest / "tools/ksu_susfs_arm64")
    (dest / "tools/ksu_susfs_arm64").chmod(0o755)
    check = f'echo "{digest}  ${{TMPDIR}}/susfs/tools/ksu_susfs_arm64" | sha256sum -c - || abort "SUSFS tool hash mismatch"\n'
    customize = (dest / "customize.sh").read_text()
    customize = replace_once(customize, 'chmod +x "${TMPDIR}/susfs/tools/ksu_susfs_arm64"',
                             check + 'chmod +x "${TMPDIR}/susfs/tools/ksu_susfs_arm64"')
    begin, end = "# Check connectivity first\n", "# copy sus_su over\n"
    if customize.count(begin) != 1 or customize.count(end) != 1:
        raise ValueError("Module installer network block changed")
    before, tail = customize.split(begin)
    _, after = tail.split(end)
    customize = before + (
        'ui_print "[-] Installing the reviewed offline SUSFS tool"\n'
        'cp "${TMPDIR}/susfs/tools/ksu_susfs_arm64" "${DEST_BIN_DIR}/.ksu_susfs.locked" || abort "SUSFS copy failed"\n'
        'chmod 755 "${DEST_BIN_DIR}/.ksu_susfs.locked" || abort "SUSFS chmod failed"\n'
        'mv -f "${DEST_BIN_DIR}/.ksu_susfs.locked" "${DEST_BIN_DIR}/ksu_susfs" || abort "SUSFS install failed"\n\n'
    ) + end + after
    # No unused cloud helpers remain in the packaged installer.
    start = customize.index("download() {")
    stop = customize.index("# Checking KernelSU Version", start)
    customize = customize[:start] + customize[stop:]
    (dest / "customize.sh").write_text(customize)
    restore = f"""#!/bin/sh
set -eu
MODDIR=${{0%/*}}
TOOL="$MODDIR/tools/ksu_susfs_arm64"
echo "{digest}  $TOOL" | sha256sum -c -
cp "$TOOL" /data/adb/ksu/bin/.ksu_susfs.locked
chmod 755 /data/adb/ksu/bin/.ksu_susfs.locked
mv -f /data/adb/ksu/bin/.ksu_susfs.locked /data/adb/ksu/bin/ksu_susfs
echo "Restored the tool paired with this reviewed kernel stack."
"""
    for name in ("action.sh", "susfs-bin-update.sh"):
        (dest / name).write_text(restore)
    (dest / "susfs-bin-check.sh").write_text(f"""#!/bin/sh
actual=$(sha256sum /data/adb/ksu/bin/ksu_susfs 2>/dev/null)
if [ "${{actual%% *}}" = "{digest}" ]; then echo match; else echo mismatch; fi
""")
    prop = dest / "module.prop"
    prop.write_text("\n".join(line for line in prop.read_text().splitlines()
                              if not line.startswith("updateJson=")) + "\n")
    provenance = dict(manifest["userspace"], binary_sha256=digest,
                      tool_patch_sha256=hashlib.sha256(
                          (ROOT / ".github/patches/susfs-userspace-kstat.patch").read_bytes()).hexdigest(),
                      susfs_commits={k: v["commit"] for k, v in manifest["profiles"].items()})
    (dest / "stack-provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    for name in ("customize.sh", "action.sh", "susfs-bin-check.sh", "susfs-bin-update.sh"):
        text = (dest / name).read_text()
        if "http://" in text or "https://" in text or "universal-binary" in text:
            raise ValueError(f"Mutable tool download remains in {name}")
        subprocess.run(["sh", "-n", str(dest / name)], check=True)
    output.mkdir(parents=True, exist_ok=True)
    archive = output / "susfs-reviewed-stack.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zipped:
        for file in sorted(dest.rglob("*")):
            if file.is_file():
                zipped.write(file, file.relative_to(dest))
    shutil.copyfile(dest / "stack-provenance.json", output / "stack-provenance.json")
    print(json.dumps(provenance, indent=2))


if __name__ == "__main__":
    package(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve(),
            Path(sys.argv[3]).resolve())
