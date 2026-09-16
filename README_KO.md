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

*GKI 커널 빌드 및 배포를 자동화하는 GitHub Actions CI/CD 파이프라인*

</div>

---

## 🚀 개요

본 레포지토리는 단일 워크플로우 실행만으로 여러 커널 버전에 걸쳐 다양한 **KernelSU** 배리언트를 일괄 컴파일할 수 있는 설정 기반의 통합 빌드 오케스트레이션 시스템입니다. 각 배리언트는 독립된 작업(Job)으로 캡슐화되어 있어 유지보수성을 높이고 장애 발생 시 원인 격리를 용이하게 합니다. 또한, 향후 새로운 배리언트나 커널 버전을 추가할 때도 유연하게 대응할 수 있는 수평적 확장성을 제공합니다.

---

## ⚙️ 설정

커널 버전별 설정은 모두 [`.github/config/kernel_versions.json`](.github/config/kernel_versions.json) 파일에서 통합 관리됩니다. 워크플로우 실행 시 `kernel_version`만 지정하면 커널 버전, 서브 레벨, 컴파일러, Rust 사용 여부, AnyKernel3 브랜치 선택 등 빌드 매트릭스 전체가 자동으로 결정됩니다.

이 포크는 [ksu-stacks.json](.github/config/ksu-stacks.json)에 검토된 조합을 고정합니다. 비어 있는 `susfs_commit`은 KMI별 고정 커밋을 선택하며, 검토되지 않은 조합은 거부합니다. 업데이트 절차와 검증 범위는 [Reviewed Stacks](docs/REVIEWED_STACKS.md)를 참고하세요.

---

## 📦 빌드 배리언트

| 배리언트 | SUSFS | Droidspaces | 후크 방식 |
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

> \* **KernelSU-XX 및 ReSukiSU 후크 방식:** 빌드 시 `hook_mode`로 선택하며 SUSFS 설정과 독립적입니다.
> - `hookless` — KernelSU-XX의 기본값; 모든 커널 버전에서 `CONFIG_KSU_HACK_ARM64_BRANCH_LINK` 사용
> - `manual` — XX와 ReSukiSU에서 선택 가능. 기본 XX-only hookless 옵션에서는 ReSukiSU가 `tracepoint` 사용
> - `tracepoint` — ReSukiSU 전용

> [!TIP]
> 일반 빌드는 선택한 배리언트와 서브 레벨별로 커널을 생성합니다. 6.12의 기본 서브 레벨은 `23`입니다. `validate-stack`은 대표 커널 48개, Android 10개와 대응 SUSFS 모듈을 검증하며 Release를 생성하지 않습니다.

---

## 📱 매니저

선택한 업스트림에서 제공하는 매니저를 사용하세요: [KowSU](https://github.com/KOWX712/KernelSU), [KernelSU-Next](https://github.com/KernelSU-Next/KernelSU-Next), [KernelSU Official](https://github.com/tiann/KernelSU), [ReSukiSU](https://github.com/ReSukiSU/ReSukiSU), 또는 [KernelSU-XX](https://github.com/backslashxx/KernelSU). 워크플로는 각 업스트림의 기존 매니저 검증을 유지하며 공용 매니저 APK를 포함하지 않습니다.

---

## 🔧 후크 방식 레퍼런스

| 방식 | 메커니즘 및 특징 |
| :--- | :--- |
| `Kprobes` | 실행 시 kprobe 브레이크포인트를 사용하여 커널 함수를 동적으로 후킹합니다. 커널에 미치는 영향을 최소화하며 광범위한 호환성을 제공합니다. **KowSU 및 KernelSU Official(비 SUSFS 환경)의 기본 방식입니다.** |
| `Tracepoint` | 커널의 정적인 syscall tracepoint 인프라(`sys_enter`/`sys_exit`)에 후킹하므로 커널 소스를 수정하지 않습니다. **KernelSU-Next(비 SUSFS 환경)의 기본 방식입니다.** |
| `Inline` | SUSFS 패치에 KernelSU 호출을 삽입하던 이전 방식입니다. 이 포크의 검토된 조합에서는 사용하지 않습니다. |
| `De-inlined` | 이전 KernelSU 호출을 제거하고 SUSFS 파일 시스템 변경을 유지합니다. KernelSU는 자체 후크와 대응 콜백을 제공합니다. **5개 배리언트 모두의 SUSFS 통합 방식입니다.** |
| `Manual` | 커널 소스 패치로 명시적인 KernelSU 후크를 추가합니다. XX와 ReSukiSU에서 SUSFS 설정과 독립적으로 선택할 수 있습니다. |
| `Hookless` | KernelSU 내장 메커니즘만을 사용합니다. 모든 커널 버전에서 `CONFIG_KSU_HACK_ARM64_BRANCH_LINK`를 활성화하며 커널 소스를 전혀 수정하지 않고 KernelSU 내부의 후크 인프라에 완전히 의존합니다. **KernelSU-XX(비 SUSFS 환경)의 기본 방식입니다.** |

---

## 🧩 기타 기능

| 기능 | 설명 |
| :--- | :--- |
| **커널 버전** | `6.1`, `6.6`, `6.12` 중 단일 버전을 선택하거나 `all`을 통해 전체 버전을 선택할 수 있습니다. 서브 레벨, 리비전, 컴파일러, Rust 설정 등은 중앙 집중식 config에서 자동으로 적용됩니다. |
| **소스 미러** | 커널 소스 및 툴체인 다운로드 시 Google 공식 AOSP 미러 또는 자체 호스팅 미러 중에서 선택할 수 있습니다. |
| **SUSFS 모듈** | 고정 소스에서 ARM64 도구를 빌드하고 3개 SUSFS ABI를 확인한 뒤 고정 모듈과 함께 패키징합니다. 설치와 업데이트는 해시가 검증된 동일한 내장 도구를 사용합니다. |
| **KSU 툴킷** | 최신 [ksu_toolkit](https://github.com/backslashxx/ksu_toolkit) 모듈을 nightly.link에서 자동으로 가져와 릴리스에 포함합니다. |
| **Droidspaces** | [Droidspaces-OSS](https://github.com/ravindu644/Droidspaces-OSS)를 활용한 컨테이너 지원 기능으로 SYSVIPC, IPC_NS, PID_NS, DEVTMPFS, NTSync, 네트워킹 기능을 제공합니다. `use_droidspaces` 옵션을 통해 배리언트마다 활성화할 수 있습니다. |
| **Re:Kernel(-X)** | [Re:Kernel](https://github.com/Sakion-Team/Re-Kernel) 및 [Re:Kernel-X](https://github.com/myflavor/ReKernel-X) 모듈을 커널에 직접 내장합니다. 툼스톤(tombstone) 기반 프리즈 복구, 네트워크 트리거 해제, 바인더(binder) 비동기 정리를 제공합니다. `use_rekernel` 옵션으로 제어합니다. |
| **유니코드 바이패스 수정** | 항상 활성화됩니다. 비표준 유니코드 인코딩을 이용한 파일시스템 우회 공격을 방지하기 위해 커널의 유니코드 정규화 로직을 패치합니다. |
| **ADIOS I/O 스케줄러** | 선택적으로 [ADIOS](https://github.com/firelzrd/adios)를 kernel 6.6 및 6.12 빌드의 내장 기본 멀티큐 I/O 스케줄러로 통합합니다. `use_adios` 옵션으로 활성화하며, kernel 6.1은 변경되지 않습니다. |
| **LZ4/Zstd zram 백엔드** | 선택적으로 커널의 LZ4 및 Zstd 구현을 공식 LZ4 1.10.0 및 Zstandard 1.5.7 릴리스로 업데이트하고 kernel 6.12의 zram 백엔드를 활성화합니다. 부팅 실패가 확인되어 6.12.81에서는 강제로 비활성화됩니다. |
| **Ccache** | 의존성 설치 완료 후 60초 대기 시간을 두어 컴파일러 캐시를 안전하게 통합합니다. 여러 워크플로우 실행에 걸쳐 안정적이고 강력한 증분 빌드 속도 향상을 제공합니다. |
| **빌드 메타데이터 커스터마이징** | 컴파일된 이미지에 포함되는 `커널 이름`, `빌드 타임스탬프`, `사용자 이름`, `호스트 이름` 문자열을 자유롭게 설정할 수 있습니다. |

---

## ✅ 테스트 완료 기기

아래 목록은 이전 버전의 기기 보고이며 이번 SUSFS 마이그레이션의 실기기 검증을 의미하지 않습니다.

| 브랜드 | 모델 |
| :--- | :--- |
| Google | Pixel 7/8/9/10 시리즈 (Tensor) |
| Xiaomi | Xiaomi 17 시리즈 (Snapdragon) |
| Xiaomi | REDMI K90 Pro Max (Snapdragon) |
| Tecno | Tecno Camon 40 Pro 4G (Helio) |

> [!NOTE]
> **호환성 안내**
> - 나열된 모든 기기는 Android 16 이상, GKI 커널(6.1/6.6/6.12) 환경에서 동작합니다
> - 기기 목록은 과거 보고이며 이번 SUSFS 마이그레이션의 실기기 검증을 의미하지 않습니다. CI는 기기 테스트를 대체하지 않습니다
> - 순정 ROM 이용 시 선택한 KernelSU 배리언트에서 제공하는 매니저 또는 Kernel Flasher로 플래시하는 것을 권장합니다

> [!TIP]
> **목록에 없는 기기를 사용 중이라면?**
> 커널이 정상 동작하는 것을 확인하셨다면 Issue 또는 Pull Request로 알려주세요. 목록에 추가하겠습니다.

---
