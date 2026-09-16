#!/usr/bin/env python3
"""Report moving upstream refs; never promote, upload or mutate build inputs."""
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def remote(repo, ref):
    output = subprocess.check_output(
        ["git", "ls-remote", "--exit-code", repo, ref], text=True, timeout=120)
    matches = [line.split()[0] for line in output.splitlines()
               if line.split()[1] == ref]
    if len(matches) != 1:
        raise ValueError(f"Ambiguous or missing ref: {repo} {ref}")
    return matches[0]


def main():
    stacks = json.loads((ROOT / ".github/config/ksu-stacks.json").read_text())
    configs = json.loads((ROOT / ".github/config/kernel_versions.json").read_text())
    selected = os.environ.get("KERNEL_VERSION_TO_CHECK", "all")
    if selected not in ("all", *configs):
        raise ValueError("Invalid kernel version")
    report = []

    def record(name, pinned, repo, ref):
        try:
            latest = remote(repo, ref)
            report.append(dict(name=name, pinned=pinned, candidate=latest,
                               changed=latest != pinned, repository=repo, ref=ref))
        except (ValueError, subprocess.SubprocessError) as error:
            report.append(dict(name=name, pinned=pinned, error=str(error)))

    for name, stack in stacks["variants"].items():
        repo, branch = stack["source_spec"].split(":")
        record(name, stack["base"], f"https://github.com/{repo}.git", f"refs/heads/{branch}")
    for kernel, config in configs.items():
        if selected not in ("all", kernel):
            continue
        kmi = f'{config["android_version"]}-{kernel}'
        record(f"SUSFS {kmi}", stacks["profiles"][kmi]["commit"],
               "https://gitlab.com/simonpunk/susfs4ksu.git", f"refs/heads/gki-{kmi}")
        for sub, rev in config["revisions"].items():
            branch = f'{kmi}-{rev["asb_date"]}'
            record(f"Kernel {kernel}.{sub}", rev["commit"],
                   "https://android.googlesource.com/kernel/common.git", f"refs/heads/{branch}")
    Path("stack-updates.json").write_text(json.dumps(report, indent=2) + "\n")
    summary = ["## Upstream candidates (review required)", ""]
    for item in report:
        state = item.get("error") or ("changed" if item["changed"] else "unchanged")
        summary.append(f'- {item["name"]}: {state}; pinned `{item["pinned"]}`')
    print("\n".join(summary))
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as output:
            output.write("\n".join(summary) + "\n")
    if any("error" in item for item in report):
        raise SystemExit("Some upstream refs could not be checked; see report")


if __name__ == "__main__":
    main()
