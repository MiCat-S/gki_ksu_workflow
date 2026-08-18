#!/bin/bash
set -eu

echo "[+] Preparing KernelSU build paths..."

sed -i '/^ccflags-y.*KSU_KERNEL_DIR/c\ccflags-y += -I$(srctree)/$(src) -I$(srctree)/$(src)/include -I$(src) -I$(src)/include' KernelSU/kernel/Kbuild 2>/dev/null || true

echo "[+] KernelSU build paths prepared."
