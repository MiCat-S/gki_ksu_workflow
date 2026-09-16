# Reviewed KernelSU / SUSFS Stacks

`.github/config/ksu-stacks.json` is the build's compatibility contract.
An empty SUSFS commit selects the reviewed KMI-specific commit, not upstream
HEAD. The familiar source branch inputs are aliases for the recorded upstream
base. An unreviewed source or SUSFS override fails before toolchain downloads.

## Source Assembly

- SUSFS off: the variant's `extra` commit and tree.
- SUSFS on: its complete `integration` commit and tree.
- Both snapshots retain upstream Manager package/signature validation.
- Original upstream, snapshot, tree, workflow, kernel and SUSFS identities are
  saved in the commit-info artifact, along with the resolved kernel configuration.
- Kernel archive hashes prevent mutable release assets from changing a build.
  The Google source option downloads the exact recorded commit.

The integration branch remains three commits above its upstream base: inherited
CI removal, common extra features/fixes, and a complete SUSFS integration patch.
The final commit must remain independently replayable on its parent. Do not append
  a small fix as a fourth commit and make it the branch's HEAD.patch.

## Updating

1. The scheduled update workflow reports upstream candidates without writing
   branches or replacing release archives.
2. Review a complete source/header/kernel-patch/userspace combination.
3. Update and test each source snapshot, retaining common fixes in `extra` so
   SUSFS-off does not silently lose them.
4. Import an exact kernel patch, review de-inlining, and regenerate the checked-in
   `51_*` outputs. The converter rejects inputs outside its reviewed hash set.
5. Update the manifest's commits, trees, exact kernel mappings and patch hashes.
   Never silently select a nearby sublevel's patch.
6. Run `.github/scripts/test-stacks.py`, source regression tests, exact patch
   replay, and the `validate-stack` release-type mode in Build and Release.
   That mode creates artifacts only and never publishes or cleans releases.
7. Review all failed jobs and artifacts before promoting formal branches.

## Validation Coverage

The all-variants CI mode runs 48 kernel jobs:

- 6.1.177, 6.6.143 and 6.12.23: all five variants, XX manual/hookless and
  ReSukiSU manual/tracepoint, each with SUSFS on and off (42 jobs).
- 6.1.172, 6.6.139, 6.12.38, 6.12.69, 6.12.81 and 6.12.93:
  KowSU with SUSFS on (6 jobs).

Companion jobs build both source snapshots for each variant with locked Cargo
dependencies and temporary validation signing. APK-embedded ARM64 ksud must match
the standalone ELF's runtime sections and load segments.
ReSukiSU uses pinned `nightly-2026-09-15` for its upstream `decl_macro` feature;
the other variants use Rust `1.98.1`. The `validate-companions` release type runs
only the Android checks for diagnosis. It does not replace full stack acceptance.

This is representative compilation plus all-base patch coverage, not every
126-way Cartesian combination and not a substitute for hardware testing.

## Paired Userspace Module

The module and universal userspace tool are fetched by full commit SHA. The tool
is built from source with the reviewed KSTAT field-width correction, and its
layout/flag ABI is checked against all three SUSFS kernel headers.

The packaged module installs its hash-verified bundled tool without downloading
another binary. Its binary update action restores that same reviewed tool. A new
tool/module version requires a stack review; automatic module updates are not
advertised by this paired package. The original WebUI and settings are retained.

ReKernel 11.6 and ReKernel-X 1.4 remain pinned to the previously built versions.
ReKernel-X 1.5's asynchronous binder lifetime changes are outside this SUSFS
migration and require a separate review.
