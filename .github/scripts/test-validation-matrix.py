#!/usr/bin/env python3
"""Exercise the real workflow matrix for every supported dispatch selection."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = yaml.safe_load((ROOT / ".github/workflows/validate-stack.yml").read_text())
STEP = next(step for step in WORKFLOW["jobs"]["matrix"]["steps"] if step.get("id") == "matrix")
HEADER = "python3 - <<'PY'\n"
assert STEP["run"].count(HEADER) == 1
SCRIPT, terminator, _ = STEP["run"].split(HEADER, 1)[1].rpartition("\nPY")
assert terminator and SCRIPT
HOOKS = {
    "KowSU": ["manual"], "KernelSU-Next": ["manual"],
    "KernelSU-Official": ["manual"], "KernelSU-XX": ["manual", "hookless"],
    "ReSukiSU": ["manual", "tracepoint"],
}
PRIMARY = {("6.1", "177"), ("6.6", "143"), ("6.12", "23")}
ADDITIONAL = {("6.1", "172"), ("6.6", "139"), ("6.12", "38"),
              ("6.12", "69"), ("6.12", "81"), ("6.12", "93")}


def generate(group, state, component):
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        output, summary = root / "output", root / "summary"
        environment = dict(os.environ, GROUP=group, SUSFS=state, COMPONENT=component,
                           GITHUB_OUTPUT=str(output), GITHUB_STEP_SUMMARY=str(summary))
        result = subprocess.run([sys.executable, "-c", SCRIPT], env=environment,
                                capture_output=True, text=True)
        if result.returncode:
            raise ValueError(result.stderr)
        outputs = {key: json.loads(value) for key, value in
                   (line.split("=", 1) for line in output.read_text().splitlines())}
        return outputs, summary.read_text()


class MatrixTests(unittest.TestCase):
    def test_every_supported_selection_has_exact_coverage(self):
        for group in (*HOOKS, "all", "additional-bases"):
            for state in ("on", "off", "both"):
                for component in ("all", "kernels", "companions", "tools"):
                    with self.subTest(group=group, state=state, component=component):
                        outputs, summary = generate(group, state, component)
                        states = {True, False} if state == "both" else {state == "on"}
                        selected = set(HOOKS) if group in ("all", "additional-bases") else {group}
                        expected = set()
                        if group != "additional-bases":
                            expected.update(
                                (variant, hook, kernel, sub, susfs)
                                for variant in selected for hook in HOOKS[variant]
                                for kernel, sub in PRIMARY for susfs in states)
                        if group in ("all", "additional-bases"):
                            expected.update(
                                ("KowSU", "manual", kernel, sub, susfs)
                                for kernel, sub in ADDITIONAL for susfs in states)
                        entries = outputs["kernels"]["include"]
                        actual = {(entry["variant"], entry["hook"], entry["kernel"],
                                   entry["sub"], entry["susfs"]) for entry in entries}
                        self.assertEqual(actual, expected)
                        self.assertEqual(len(entries), len(actual), "duplicate jobs")
                        self.assertEqual(set(outputs["companions"]), selected)
                        count = len(expected) if component in ("all", "kernels") else 0
                        self.assertIn(f"kernel jobs: {count}.", summary)

    def test_unknown_workflow_call_inputs_are_rejected(self):
        for arguments in (("unknown", "on", "all"), ("all", "unknown", "all"),
                          ("all", "on", "unknown")):
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                generate(*arguments)


if __name__ == "__main__":
    unittest.main()
