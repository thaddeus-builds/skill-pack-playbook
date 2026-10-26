---
name: feedback-skip-full-suite-locally
description: The owner prefers speed over a local full run_all when the risk is small and correctable; run the affected suite locally and let CI run the full suite on the PR
metadata:
  node_type: memory
  type: feedback
  originSessionId: d994ec77-cfab-4c70-a65c-b182cbce8499
  modified: 2026-10-26T15:44:18.481Z
---

On 2026-10-26 the owner said: if the risk is small and can be corrected afterwards, skip unimportant tests to move faster ("如果没有很大风险，而且随后可以纠正的话。可以尝试跳过一些不重要的测试。我希望加快进度").

**Why:** `python3 run_all.py` takes 4 to 7 minutes per branch and the owner was waiting on it repeatedly for docs-only and test-only changes; CI runs the same command on every pull request anyway.

**How to apply:** for a change that touches only docs, tests or playbook tooling, run the one affected suite (`python3 tests/run.py`, `kit/tests/run.py <filter>`, the templates selftest) and open the PR; say in the PR that CI runs the full suite. Keep the full local run for a kit byte change (VERSION, manifest) and for anything on the risky list (the gate, the write path, human tables). Never skip a failing test to get green.
