"""
Differential tests against the GNU ``patch`` commandline utility: across
randomized scenarios, unipatch must produce byte-identical output, or fail
exactly when ``patch`` fails.
"""

from __future__ import annotations

import difflib
import random
import shutil
import subprocess
from pathlib import Path

import pytest

from unipatch import PatchError, apply_patch

GNU_PATCH = ""
if shutil.which("gpatch") is not None:  # pragma: no cover
    GNU_PATCH = "gpatch"
elif shutil.which("patch") is not None and (
    "GNU patch"
    in subprocess.run(["patch", "--version"], capture_output=True, text=True).stdout
):  # pragma: no cover
    GNU_PATCH = "patch"

pytestmark = pytest.mark.skipif(
    not GNU_PATCH,
    reason="GNU patch not installed",
)


WORDS = ["alpha", "bravo", "charlie", "delta", "echo", "", "  x", "\ty"]


def gnu_patch(tmp_path: Path, source: str, patch: str, forwards: bool) -> str | None:
    """
    Apply the patch with the ``patch`` command, returning None on failure.
    """
    source_path = tmp_path / "source.txt"
    source_path.write_text(source)
    patch_path = tmp_path / "patch.txt"
    patch_path.write_text(patch + "\n")

    command = [GNU_PATCH, "--force"]
    if not forwards:
        command.append("--reverse")
    command.extend([str(source_path), str(patch_path)])
    result = subprocess.run(command, capture_output=True, text=True)
    for reject in tmp_path.glob("*.rej"):
        reject.unlink()
    if result.returncode != 0:
        return None
    return source_path.read_text()


def unipatch_apply(source: str, patch: str, forwards: bool) -> str | None:
    try:
        return apply_patch(source, patch, forwards=forwards)
    except PatchError:
        return None


def mutate(rng: random.Random, lines: list[str], trial: int) -> list[str]:
    result = lines[:]
    # Guarantees the result differs from the input
    result.insert(rng.randrange(len(result) + 1), f"FORCED{trial}")
    for _ in range(rng.randint(0, 3)):
        op = rng.choice(["delete", "insert", "replace"])
        index = rng.randrange(len(result) + 1)
        if op == "insert":
            result.insert(index, rng.choice(WORDS) + "NEW")
        elif op == "delete" and index < len(result):
            result.pop(index)
        elif op == "replace" and index < len(result):
            result[index] = rng.choice(WORDS) + "REP"
    return result


def vary_source(rng: random.Random, lines: list[str], mode: str) -> list[str]:
    result = lines[:]
    if mode == "pad":
        pad = [f"PAD{i}" for i in range(rng.randint(1, 5))]
        result = pad + result if rng.random() < 0.5 else result + pad
    elif mode == "corrupt":
        result[rng.randrange(len(result))] += "_CHANGED"
    return result


def join_lines(lines: list[str], complete: bool) -> str:
    text = "".join(f"{line}\n" for line in lines)
    return text if complete else text[:-1]


def test_differential(tmp_path):
    rng = random.Random(8_675_309)
    for trial in range(250):
        a = [
            rng.choice(WORDS) + str(rng.randint(0, 4))
            for _ in range(rng.randint(1, 12))
        ]
        b = mutate(rng, a, trial)
        context = rng.choice([0, 1, 2, 3])
        patch = "\n".join(difflib.unified_diff(a, b, lineterm="", n=context))

        mode = rng.choice(["exact", "pad", "corrupt"])
        source_a = join_lines(vary_source(rng, a, mode), rng.random() < 0.5)
        source_b = join_lines(vary_source(rng, b, mode), rng.random() < 0.5)

        for source, forwards in [(source_a, True), (source_b, False)]:
            expected = gnu_patch(tmp_path, source, patch, forwards)
            result = unipatch_apply(source, patch, forwards)
            assert result == expected, (
                f"Mismatch with GNU patch on trial {trial}, mode {mode},"
                f" forwards={forwards}:\nsource:\n{source}\npatch:\n{patch}\n"
                f"GNU patch: {expected!r}\nunipatch: {result!r}"
            )
