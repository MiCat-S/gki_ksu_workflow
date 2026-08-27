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

*GKIカーネルのビルドと配布を自動化する GitHub Actions CI/CD パイプライン*

</div>

---

## 🚀 概要

本リポジトリは、単一のワークフローから複数のカーネルバージョン向けに、多様な **KernelSU** バリアントを一括コンパイルできる設定駆動型の統合ビルドシステムです。各バリアントは独立したジョブとしてカプセル化されており、保守性を高め、障害の切り分けを容易にするとともに、将来的なバリアントやカーネルバージョンの追加にもシームレスに対応できる柔軟なスケーリングを実現します。

---

## ⚙️ 設定

カーネルバージョン固有の設定は、すべて [`.github/config/kernel_versions.json`](.github/config/kernel_versions.json) に集約されています。ワークフロー実行時に `kernel_version` を指定するだけで、カーネルバージョン、サブレベル、コンパイラ、Rust の要否、AnyKernel3 のブランチ選択など、ビルドマトリクス全体が自動的に決定されます。

---

## 📦 ビルドバリアント

| バリアント | SUSFS | Droidspaces | フック方式 |
| :--- | :---: | :---: | :--- |
| [KowSU](https://github.com/KOWX712/KernelSU) | ❌ | ❌ | `Kprobes` |
| [KowSU-DS](https://github.com/KOWX712/KernelSU) | ❌ | ✅ | `Kprobes` |
| [KowSU-SUSFS](https://github.com/KOWX712/KernelSU) | ✅ | ❌ | `Inline` |
| [KowSU-SUSFS-DS](https://github.com/KOWX712/KernelSU) | ✅ | ✅ | `Inline` |
| [KernelSU-Next](https://github.com/KernelSU-Next/KernelSU-Next) | ❌ | ❌ | `Tracepoint` |
| [KernelSU-Next-DS](https://github.com/KernelSU-Next/KernelSU-Next) | ❌ | ✅ | `Tracepoint` |
| [KernelSU-Next-SUSFS](https://github.com/KernelSU-Next/KernelSU-Next) | ✅ | ❌ | `Inline` |
| [KernelSU-Next-SUSFS-DS](https://github.com/KernelSU-Next/KernelSU-Next) | ✅ | ✅ | `Inline` |
| [KernelSU-Official](https://github.com/tiann/KernelSU) | ❌ | ❌ | `Kprobes` |
| [KernelSU-Official-DS](https://github.com/tiann/KernelSU) | ❌ | ✅ | `Kprobes` |
| [KernelSU-Official-SUSFS](https://github.com/tiann/KernelSU) | ✅ | ❌ | `Inline` |
| [KernelSU-Official-SUSFS-DS](https://github.com/tiann/KernelSU) | ✅ | ✅ | `Inline` |
| [ReSukiSU](https://github.com/ReSukiSU/ReSukiSU) | ❌ | ❌ | `Manual` |
| [ReSukiSU-DS](https://github.com/ReSukiSU/ReSukiSU) | ❌ | ✅ | `Manual` |
| [ReSukiSU-SUSFS](https://github.com/ReSukiSU/ReSukiSU) | ✅ | ❌ | `Inline` |
| [ReSukiSU-SUSFS-DS](https://github.com/ReSukiSU/ReSukiSU) | ✅ | ✅ | `Inline` |
| [KernelSU-XX](https://github.com/backslashxx/KernelSU) | ❌ | ❌ | `Hookless` |
| [KernelSU-XX-DS](https://github.com/backslashxx/KernelSU) | ❌ | ✅ | `Hookless` |
| [KernelSU-XX-SUSFS](https://github.com/backslashxx/KernelSU) | ✅ | ❌ | `De-inlined` |
| [KernelSU-XX-SUSFS-DS](https://github.com/backslashxx/KernelSU) | ✅ | ✅ | `De-inlined` |

> \* **KernelSU-XX および ReSukiSU のフック方式:** 実行時に `hook_mode` で切り替え可能です。
> - `hookless` — KernelSU-XX のデフォルト；すべてのカーネルバージョンで `CONFIG_KSU_HACK_ARM64_BRANCH_LINK` を使用
> - `manual` — ReSukiSU のデフォルト
> - `tracepoint` — ReSukiSU のみ対応

> [!TIP]
> **マトリクスビルドの仕組み:** マトリクスは常にバリアントごとに **1 つの成果物** のみを生成します。有効化した機能（Droidspaces / SUSFS）は、その単一の成果物に適用されます。5 つのバリアントすべてを選択した場合、カーネルバージョンの **各サブレベルごとに 5 つのビルド** が実行されます。`kernel_version` で `all` を選択すると、6.1 / 6.6 / 6.12 の全サブレベルが並列コンパイルされ、デフォルト設定では合計 **25 のジョブ** が同時に実行されます。

---

## 📱 マネージャー

選択したアップストリームが提供するマネージャーを使用してください：[KowSU](https://github.com/KOWX712/KernelSU)、[KernelSU-Next](https://github.com/KernelSU-Next/KernelSU-Next)、[KernelSU Official](https://github.com/tiann/KernelSU)、[ReSukiSU](https://github.com/ReSukiSU/ReSukiSU)、または [KernelSU-XX](https://github.com/backslashxx/KernelSU)。ワークフローは各アップストリーム本来のマネージャー検証を維持し、共通マネージャー APK は同梱しません。

---

## 🔧 フック方式リファレンス

| 方式 | メカニズムと特徴 |
| :--- | :--- |
| `Kprobes` | 実行時に kprobe ブレークポイントを用いてカーネル関数を動的にフックします。カーネルへの影響が最小限で、幅広い互換性を持ちます。**KowSU および KernelSU Official（非 SUSFS）のデフォルト。** |
| `Tracepoint` | カーネルの静的な syscall tracepoint 基盤（`sys_enter`/`sys_exit`）にフックするため、カーネルソースの改変を行いません。**KernelSU-Next（非 SUSFS）のデフォルト。** |
| `Inline` | `#ifdef CONFIG_KSU_SUSFS` ブロックをカーネルサブシステムのソースに直接埋め込む、コンパイル時注入方式です。`static_key` 分岐により実行時の切り替えが可能です。kprobe や LSM フックには依存しません。VFS（`exec`、`open`、`stat`、`readdir`、`statfs`）、SELinux（`avc`、`hooks`、`services`）、input、mounts、procfs に組み込まれます。**KowSU、KernelSU-Next、ReSukiSU、KernelSU Official の SUSFS ビルドで使用。** |
| `De-inlined` | `#ifdef CONFIG_KSU_SUSFS` によるインラインブロックを使用せず、カーネルソースへのパッチ適用により SUSFS フックを組み込みます。SUSFS ロジックがコアカーネルサブシステムからより明確に分離されます。**KernelSU-XX-SUSFS で使用。** |
| `Manual` | カーネルソースへの静的なパッチ適用方式です。コンパイル時に独自のフックをコアカーネルサブシステムへ注入します。**ReSukiSU（非 SUSFS）のデフォルト。** |
| `Hookless` | KernelSU 組み込みの機構のみを使用します。すべてのカーネルバージョンで `CONFIG_KSU_HACK_ARM64_BRANCH_LINK` を有効化し、カーネルソースの改変は一切行いません。KernelSU 内部のフック基盤に完全に依存します。**KernelSU-XX（非 SUSFS）のデフォルト。** |

---

## 🧩 その他の機能

| 機能 | 説明 |
| :--- | :--- |
| **カーネルバージョン** | `6.1`、`6.6`、`6.12`、または `all` から、単一または全バージョンを選択できます。サブレベル、リビジョン、コンパイラ、Rust の各設定は、一元化された config から自動解決されます。 |
| **ソースミラー** | カーネルソースおよびツールチェーンの取得先として、Google 公式の AOSP ミラー、またはセルフホストミラーを選択可能です。 |
| **SUSFS モジュール** | SUSFS 有効時に、最新の [susfs4ksu-module](https://github.com/sidex15/susfs4ksu-module) を自動取得してリリースに同梱します。全バリアントの SUSFS バージョンは単一の `susfs_commit` 入力で一元管理されます。 |
| **KSU ツールキット** | 最新の [ksu_toolkit](https://github.com/backslashxx/ksu_toolkit) モジュールを nightly.link から自動取得し、リリースに同梱します。 |
| **Droidspaces** | [Droidspaces-OSS](https://github.com/ravindu644/Droidspaces-OSS) を利用したコンテナ対応。SYSVIPC、IPC_NS、PID_NS、DEVTMPFS、NTSync、ネットワーク機能を提供します。`use_droidspaces` トグルでバリアントごとに有効化できます。 |
| **Re:Kernel(-X)** | [Re:Kernel](https://github.com/Sakion-Team/Re-Kernel) および [Re:Kernel-X](https://github.com/myflavor/ReKernel-X) モジュールをカーネルに直接組み込みます。tombstone によるフリーズ復旧、ネットワークトリガーによる解除、binder 非同期クリーンアップを提供します。`use_rekernel` スイッチで制御します。 |
| **Unicode バイパス修正** | 常に有効です。非標準の Unicode エンコーディングを用いたファイルシステムバイパス攻撃を防ぐため、カーネルの Unicode 正規化処理にパッチを適用します。 |
| **ADIOS I/O スケジューラ** | オプションで [ADIOS](https://github.com/firelzrd/adios) を kernel 6.6 および 6.12 ビルドの組み込みデフォルト・マルチキュー I/O スケジューラとして統合します。`use_adios` トグルで有効化し、kernel 6.1 は変更されません。 |
| **LZ4/Zstd zram バックエンド** | オプションでカーネルの LZ4 と Zstd 実装を公式 LZ4 1.10.0 および Zstandard 1.5.7 に更新し、kernel 6.12 の zram バックエンドを有効化します。`use_lz4_zstd` トグルで制御し、6.1 および 6.6 ビルドは変更されません。 |
| **Ccache** | 依存関係のインストール完了後に 60 秒間の待機プロセスを設けることでコンパイラキャッシュを安全に統合。ワークフロー実行をまたいだ、安定かつ堅牢な増分ビルドの高速化を実現します。 |
| **ビルドメタデータのカスタマイズ** | コンパイル済みイメージに埋め込む `カーネル名`、`ビルド日時`、`ユーザー名`、`ホスト名` を任意に設定できます。 |

---

## ✅ 動作確認済み端末

本ワークフローでビルドしたカーネルにて、下記端末での動作を確認済みです。

| ブランド | モデル |
| :--- | :--- |
| Google | Pixel 7/8/9/10 シリーズ (Tensor) |
| Xiaomi | Xiaomi 17 シリーズ (Snapdragon) |
| Xiaomi | REDMI K90 Pro Max (Snapdragon) |
| Tecno | Tecno Camon 40 Pro 4G (Helio) |

> [!NOTE]
> **互換性について**
> - 記載の端末はいずれも Android 16 以降・GKI カーネル（6.1/6.6/6.12）環境で動作しています
> - SUSFS / Droidspaces は全シリーズで検証済みです
> - 純正 ROM をご利用の場合は、選択した KernelSU バリアントのマネージャー、または Kernel Flasher からの書き込みを推奨します

> [!TIP]
> **お使いの端末がリストにない場合**
> カーネルの動作確認ができましたら、Issue または Pull Request でお知らせください。リストに追記します。

---
