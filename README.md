<div align="center">

🌐 [English](README.md) &nbsp;|&nbsp; [简体中文](README_CN.md) &nbsp;|&nbsp; [日本語](README_JP.md) &nbsp;|&nbsp; [한국어](README_KO.md)

</div>

<div align="center">

# 🌀 GKI KSU Workflow

![License](https://img.shields.io/github/license/reF1nd/gki_ksu_workflow?style=flat-square&color=blue)
![Last Commit](https://img.shields.io/github/last-commit/reF1nd/gki_ksu_workflow?style=flat-square&color=green)
![Release](https://img.shields.io/github/v/release/reF1nd/gki_ksu_workflow?style=flat-square&color=orange)

![Android](https://img.shields.io/badge/Android-GKI-3DDC84?style=for-the-badge&logo=android&logoColor=white)
![Kernel](https://img.shields.io/badge/Kernel-6.1_~_6.12-2F363D?style=for-the-badge&logo=linux&logoColor=white)
![Architecture](https://img.shields.io/badge/Arch-arm64-blue?style=for-the-badge)
![CI](https://img.shields.io/badge/CI-GitHub_Actions-2088FF?style=for-the-badge&logo=githubactions&logoColor=white)

*Automated GitHub Actions CI/CD pipeline for compiling and distributing GKI kernels.*

</div>

---

## 🚀 Overview

This repository implements a unified, config-driven build orchestration system that compiles multiple **KernelSU** variants across multiple kernel versions from a single workflow trigger. Each variant is encapsulated within its own isolated job, maximizing maintainability, simplifying fault isolation, and enabling seamless horizontal scaling for future variants and kernel versions.

---

## ⚙️ Configuration

All kernel version-specific settings are centralized in [`.github/config/kernel_versions.json`](.github/config/kernel_versions.json). A single `kernel_version` input at workflow dispatch drives the entire build matrix — including Kernel version, Sublevel, Compiler, Rust availability, and AnyKernel3 branch selection.

This fork builds immutable, reviewed source combinations from
[`.github/config/ksu-stacks.json`](.github/config/ksu-stacks.json). A blank
`susfs_commit` selects the pinned KMI-specific commit, not the latest upstream
revision. Unreviewed source/SUSFS combinations are rejected before building.
See [Reviewed Stacks](docs/REVIEWED_STACKS.md) for updates and acceptance coverage.

---

## 📦 Build Variants

| Variant | SUSFS | Droidspaces | Hook Type |
| :--- | :---: | :---: | :--- |
| [KowSU](https://github.com/KOWX712/KernelSU) | ❌ | ❌ | `Kprobes` |
| [KowSU-DS](https://github.com/KOWX712/KernelSU) | ❌ | ✅ | `Kprobes` |
| [KowSU-SUSFS](https://github.com/KOWX712/KernelSU) | ✅ | ❌ | `De-inlined` |
| [KowSU-SUSFS-DS](https://github.com/KOWX712/KernelSU) | ✅ | ✅ | `De-inlined` |
| [KernelSU-Next](https://github.com/KernelSU-Next/KernelSU-Next) | ❌ | ❌ | `Tracepoint` |
| [KernelSU-Next-DS](https://github.com/KernelSU-Next/KernelSU-Next) | ❌ | ✅ | `Tracepoint` |
| [KernelSU-Next-SUSFS](https://github.com/KernelSU-Next/KernelSU-Next) | ✅ | ❌ | `De-inlined` |
| [KernelSU-Next-SUSFS-DS](https://github.com/KernelSU-Next/KernelSU-Next) | ✅ | ✅ | `De-inlined` |
| [KernelSU-Official](https://github.com/tiann/KernelSU) | ❌ | ❌ | `Kprobes` |
| [KernelSU-Official-DS](https://github.com/tiann/KernelSU) | ❌ | ✅ | `Kprobes` |
| [KernelSU-Official-SUSFS](https://github.com/tiann/KernelSU) | ✅ | ❌ | `De-inlined` |
| [KernelSU-Official-SUSFS-DS](https://github.com/tiann/KernelSU) | ✅ | ✅ | `De-inlined` |
| [ReSukiSU](https://github.com/ReSukiSU/ReSukiSU) | ❌ | ❌ | `Manual` / `Tracepoint` |
| [ReSukiSU-DS](https://github.com/ReSukiSU/ReSukiSU) | ❌ | ✅ | `Manual` / `Tracepoint` |
| [ReSukiSU-SUSFS](https://github.com/ReSukiSU/ReSukiSU) | ✅ | ❌ | `De-inlined` |
| [ReSukiSU-SUSFS-DS](https://github.com/ReSukiSU/ReSukiSU) | ✅ | ✅ | `De-inlined` |
| [KernelSU-XX](https://github.com/backslashxx/KernelSU) | ❌ | ❌ | `Hookless` |
| [KernelSU-XX-DS](https://github.com/backslashxx/KernelSU) | ❌ | ✅ | `Hookless` |
| [KernelSU-XX-SUSFS](https://github.com/backslashxx/KernelSU) | ✅ | ❌ | `De-inlined` |
| [KernelSU-XX-SUSFS-DS](https://github.com/backslashxx/KernelSU) | ✅ | ✅ | `De-inlined` |

> \* **KernelSU-XX & ReSukiSU Hook Type:** Selected at build time via `hook_mode`, independently of SUSFS.
> - `hookless` — default for KernelSU-XX; uses `CONFIG_KSU_HACK_ARM64_BRANCH_LINK` on all kernel versions
> - `manual` — available for KernelSU-XX and ReSukiSU; the default XX-only hookless selection maps ReSukiSU to `tracepoint`
> - `tracepoint` — ReSukiSU only

> [!TIP]
> **Matrix Build Orchestration:** Normal builds produce one kernel artifact per selected variant and sublevel. Kernel 6.12 uses the selected `kernel_sublevel` (default `23`). The separate `validate-stack` mode runs 48 representative kernel builds, 10 Android companion builds and one paired SUSFS module build without publishing a release.

---

## 📱 Managers

Use the manager distributed by the selected upstream: [KowSU](https://github.com/KOWX712/KernelSU), [KernelSU-Next](https://github.com/KernelSU-Next/KernelSU-Next), [KernelSU Official](https://github.com/tiann/KernelSU), [ReSukiSU](https://github.com/ReSukiSU/ReSukiSU), or [KernelSU-XX](https://github.com/backslashxx/KernelSU). The workflow preserves each upstream's manager verification and does not bundle a universal manager APK.

---

## 🔧 Hook Type Reference

| Type | Mechanism & Characteristics |
| :--- | :--- |
| `Kprobes` | Dynamically instruments kernel functions at runtime via kprobe breakpoints. Minimal kernel footprint, broad compatibility. **Default for KowSU and KernelSU Official** (non-SUSFS). |
| `Tracepoint` | Hooks into the kernel's static syscall tracepoint infrastructure (`sys_enter`/`sys_exit`) without modifying kernel source. **Default for KernelSU-Next** (non-SUSFS). |
| `Inline` | Legacy integration with KernelSU call sites embedded in the SUSFS kernel patch. Not used by the reviewed stacks in this fork. |
| `De-inlined` | Removes legacy inline KernelSU call sites from the reviewed SUSFS patch while retaining SUSFS filesystem changes. KernelSU uses its own hook mechanism and supplies the paired SUSFS callbacks. **Used for SUSFS integration by all five variants.** |
| `Manual` | Explicit KernelSU hooks applied as kernel source patches. Selectable for ReSukiSU and KernelSU-XX with SUSFS either on or off. |
| `Hookless` | Pure KernelSU built-in mechanisms. Always enables `CONFIG_KSU_HACK_ARM64_BRANCH_LINK` regardless of kernel version. Zero kernel source modification. Relies entirely on KernelSU's internal hooking infrastructure. **Default for KernelSU-XX** (non-SUSFS). |

---

## 🧩 Additional Features

| Feature | Description |
| :--- | :--- |
| **Kernel Version** | Select `6.1`, `6.6`, `6.12`, or `all` to compile one or all kernel versions. Sublevel, revision, compiler, and Rust settings are auto-resolved from the centralized config. |
| **Source Mirror** | Choose between Google's official AOSP mirror or a self-hosted mirror for kernel source and toolchain downloads. |
| **SUSFS Module** | Builds the paired ARM64 tool from pinned source, checks its ABI against the three SUSFS profiles, and packages it with the pinned module. Installation and the binary update action use the same hash-verified bundled tool, not a mutable latest binary. |
| **KSU Toolkit** | Automatically fetches the latest [ksu_toolkit](https://github.com/backslashxx/ksu_toolkit) module from nightly.link and attaches it to the release. |
| **Droidspaces** | Container support via [Droidspaces-OSS](https://github.com/ravindu644/Droidspaces-OSS) — SYSVIPC, IPC_NS, PID_NS, DEVTMPFS, NTSync, and networking. Enabled per-variant through the `use_droidspaces` toggle. |
| **Re:Kernel(-X)** | Integrated [Re:Kernel](https://github.com/Sakion-Team/Re-Kernel) and [Re:Kernel-X](https://github.com/myflavor/ReKernel-X) modules compiled directly into the kernel. Provides tombstone freeze recovery, network-triggered unfreeze, and binder async cleanup. Toggled via `use_rekernel` switch. |
| **Unicode Bypass Fix** | Always enabled. Patches kernel unicode normalization to prevent filesystem bypass attacks via non-standard unicode encodings. |
| **ADIOS I/O Scheduler** | Optionally integrates [ADIOS](https://github.com/firelzrd/adios) as the built-in default multi-queue I/O scheduler for kernel 6.6 and 6.12 builds. Enabled through the `use_adios` toggle; kernel 6.1 remains unchanged. |
| **LZ4/Zstd zram backends** | Optionally updates the kernel's LZ4 and Zstd implementations from the official LZ4 1.10.0 and Zstandard 1.5.7 releases, with zram backend support enabled for kernel 6.12. Disabled for 6.12.81 due to a confirmed boot failure; 6.1 and 6.6 builds remain unchanged. |
| **Ccache** | Compiler cache integration with a 60-second wait guard for dependency installation, ensuring robust accelerated incremental rebuilds across workflow runs. |
| **Spoofed Build Metadata** | Customizable `kernel name`, `build timestamp`, `user`, and `host` strings for the compiled image. |

---

## ✅ Tested Devices

The following list records earlier device reports. It does not establish hardware compatibility for the reviewed SUSFS migration; this migration has no new device-testing claim.

| Brand | Model |
| :--- | :--- |
| Google | Pixel 7/8/9/10 series (Tensor) |
| Xiaomi | Xiaomi 17 series (Snapdragon) |
| Xiaomi | REDMI K90 Pro Max (Snapdragon) |
| Tecno | Tecno Camon 40 Pro 4G (Helio) |

> [!NOTE]
> **Compatibility Notes:**
> - All listed devices run Android 16+ with GKI kernels (6.1/6.6/6.12)
> - CI compilation and artifact verification do not replace device testing
> - Users on stock ROMs are advised to flash the kernel via the manager provided by their selected KernelSU variant or Kernel Flasher

> [!TIP]
> **Have a device not listed?**
> If you've successfully tested a kernel on your device, feel free to open an issue or pull request to have it added to this list!

---
