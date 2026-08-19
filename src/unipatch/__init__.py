"""
An in-memory implementation of unified diff patching, following the behaviour
of GNU patch: hunks may apply at an offset from their stated line numbers, and
with a “fuzz factor” that ignores up to 2 mismatching leading/trailing context
lines.
"""

from __future__ import annotations

import re
from typing import Literal, cast

__all__ = (
    "apply_patch",
    "PatchError",
    "PatchParseError",
    "HunkApplyError",
)

MAX_FUZZ = 2


class PatchError(ValueError):
    pass


class PatchParseError(PatchError):
    pass


class HunkApplyError(PatchError):
    pass


Tag = Literal[" ", "-", "+"]


class Line:
    __slots__ = ("tag", "text", "newline", "phantom")

    def __init__(
        self,
        tag: Tag,
        text: str,
        newline: bool = True,
        # True for stand-ins for context lines missing from a hunk cut short
        # at the end of the patch. They never match source lines, so can
        # only be ignored by fuzz, mirroring GNU patch.
        phantom: bool = False,
    ) -> None:
        self.tag = tag
        self.text = text
        self.newline = newline
        self.phantom = phantom


class Hunk:
    __slots__ = ("number", "old_start", "old_count", "new_start", "new_count", "lines")

    def __init__(
        self,
        number: int,
        old_start: int,
        old_count: int,
        new_start: int,
        new_count: int,
        lines: list[Line],
    ) -> None:
        self.number = number
        self.old_start = old_start
        self.old_count = old_count
        self.new_start = new_start
        self.new_count = new_count
        self.lines = lines


def apply_patch(source: str, patch: str, forwards: bool = True) -> str:
    hunks = _parse_patch(patch)
    if not forwards:
        hunks = [_invert_hunk(hunk) for hunk in hunks]
    return _apply_hunks(source, hunks)


_HUNK_HEADER_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def _parse_patch(patch: str) -> list[Hunk]:
    lines = patch.split("\n")
    if lines[-1] == "":
        # split() artifact from a trailing newline, not a line of the patch
        lines.pop()
    hunks: list[Hunk] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("@@"):
            match = _HUNK_HEADER_RE.match(line)
            if match is None:
                raise PatchParseError(
                    f"Hunk #{len(hunks) + 1} has an invalid header line: {line!r}."
                )
            number = len(hunks) + 1
            old_count = int(match[2]) if match[2] is not None else 1
            new_count = int(match[4]) if match[4] is not None else 1
            i, hunk_lines = _parse_hunk_body(lines, i + 1, number, old_count, new_count)
            hunks.append(
                Hunk(
                    number=number,
                    old_start=int(match[1]),
                    old_count=old_count,
                    new_start=int(match[3]),
                    new_count=new_count,
                    lines=hunk_lines,
                )
            )
        else:
            # Skip file headers (`---`/`+++` lines) and any other content
            # outside hunks, like GNU patch does.
            i += 1
    if not hunks:
        raise PatchParseError(
            "The patch does not contain any hunks; it does not appear to be"
            + " valid unified diff format."
        )
    return hunks


def _parse_hunk_body(
    lines: list[str], i: int, number: int, old_count: int, new_count: int
) -> tuple[int, list[Line]]:
    hunk_lines: list[Line] = []
    old_remaining = old_count
    new_remaining = new_count
    last: Line | None = None
    while old_remaining > 0 or new_remaining > 0:
        if i >= len(lines):
            if old_remaining == new_remaining and hunk_lines:
                # Like GNU patch, tolerate a hunk cut short at the end of the
                # patch when only shared trailing context lines are missing.
                for _ in range(old_remaining):
                    hunk_lines.append(Line(tag=" ", text="", phantom=True))
                break
            raise PatchParseError(
                f"Hunk #{number} ends before all of the lines declared in"
                + " its header."
            )
        if lines[i].startswith("@@"):
            raise PatchParseError(
                f"Hunk #{number} ends before all of the lines declared in"
                + " its header."
            )
        raw = lines[i]
        if raw.startswith("\\"):
            # “\ No newline at end of file” marker, referring to the previous
            # line.
            if last is None:
                raise PatchParseError(
                    f"Hunk #{number} has a '\\ No newline' marker line"
                    + " with no line before it."
                )
            last.newline = False
            i += 1
            continue
        if raw.startswith((" ", "-", "+")):
            line = Line(tag=cast(Tag, raw[0]), text=raw[1:])
        elif raw == "" or raw.startswith("\t"):
            # Like GNU patch, treat empty and tab-led lines as context lines
            # that have lost their leading space, e.g. through editors
            # stripping trailing whitespace.
            line = Line(tag=" ", text=raw)
        else:
            raise PatchParseError(f"Hunk #{number} has an invalid line: {raw!r}.")
        if line.tag in (" ", "-"):
            old_remaining -= 1
        if line.tag in (" ", "+"):
            new_remaining -= 1
        if old_remaining < 0 or new_remaining < 0:
            raise PatchParseError(
                f"Hunk #{number} contains more lines than declared in its" + " header."
            )
        hunk_lines.append(line)
        last = line
        i += 1
    if i < len(lines) and lines[i].startswith("\\") and last is not None:
        last.newline = False
        i += 1
    if all(line.tag == " " for line in hunk_lines):
        # GNU patch also rejects hunks without any changed lines.
        raise PatchParseError(f"Hunk #{number} contains no changed lines.")
    return i, hunk_lines


_INVERT_TAGS: dict[Tag, Tag] = {
    "-": "+",
    "+": "-",
    " ": " ",
}


def _invert_hunk(hunk: Hunk) -> Hunk:
    return Hunk(
        number=hunk.number,
        old_start=hunk.new_start,
        old_count=hunk.new_count,
        new_start=hunk.old_start,
        new_count=hunk.old_count,
        lines=[
            Line(
                _INVERT_TAGS[line.tag],
                line.text,
                line.newline,
                line.phantom,
            )
            for line in hunk.lines
        ],
    )


def _apply_hunks(source: str, hunks: list[Hunk]) -> str:
    if source == "":
        lines: list[str] = []
        ends_with_newline = True
    else:
        ends_with_newline = source.endswith("\n")
        lines = source.split("\n")
        if ends_with_newline:
            lines.pop()

    # Total lines added minus lines removed by hunks applied so far, mapping
    # line numbers in the unpatched source to positions in `lines`.
    shift = 0
    # How far the previous hunk applied from its stated position, carried
    # forward as an adjustment to later hunks’ positions, like GNU patch.
    offset = 0
    # Hunks must apply in order, each after the previous one’s replacement.
    min_pos = 0
    # Position just past the lines “frozen” by previous hunks, mirroring GNU
    # patch’s last_frozen_line: unlike min_pos, a hunk’s trailing context is
    # not frozen, so a later hunk may apply over it.
    frozen = 0
    for hunk in hunks:
        old_lines = [line for line in hunk.lines if line.tag != "+"]
        new_lines = [line for line in hunk.lines if line.tag != "-"]

        # Position of the source’s final, newline-less line, if any: deletion
        # lines only match it when the patch marks them as incomplete too.
        incomplete_pos = len(lines) - 1 if not ends_with_newline else None

        if not old_lines:
            # An insertion-only hunk with no context: old_start is the line
            # number to insert after.
            pos = hunk.old_start + shift + offset
            pos = max(min_pos, min(pos, len(lines)))
            matched_old: list[Line] = []
            matched_new = new_lines
        else:
            pos, matched_old, matched_new, offset = _find_hunk(
                lines,
                hunk,
                old_lines,
                new_lines,
                shift,
                offset,
                min_pos,
                frozen,
                incomplete_pos,
            )

        at_end = pos + len(matched_old) == len(lines)
        if (
            at_end
            and not matched_old
            and matched_new
            and not ends_with_newline
            and lines
            and hunk.lines[-1].tag == " "
        ):
            # Inserting after the source's incomplete final line, from a hunk
            # whose insertions are followed by (fuzz-ignored) context: like
            # GNU patch, the first inserted line continues that line, since
            # there is no newline to insert after. When the insertions end
            # the hunk instead, GNU patch supplies the missing newline, which
            # the ordinary insertion below reproduces.
            lines[-1] += matched_new[0].text
            lines.extend(line.text for line in matched_new[1:])
            ends_with_newline = matched_new[-1].newline
            min_pos = len(lines)
            frozen = len(lines)
            shift += len(new_lines) - len(old_lines)
            continue
        lines[pos : pos + len(matched_old)] = [line.text for line in matched_new]
        if at_end:
            if matched_new:
                # Correct even for a final context line: matching enforced
                # that its trailing-newline state agrees with the source’s.
                ends_with_newline = matched_new[-1].newline
            else:
                # The lines up to the end were deleted, so the new final line
                # is an untouched source line, which has a newline.
                ends_with_newline = True

        min_pos = pos + len(matched_new)
        trailing_context = 0
        while (
            trailing_context < len(matched_new)
            and matched_new[-1 - trailing_context].tag == " "
        ):
            trailing_context += 1
        frozen = pos + len(matched_new) - trailing_context
        shift += len(new_lines) - len(old_lines)

    if not lines:
        return ""
    return "\n".join(lines) + ("\n" if ends_with_newline else "")


def _find_hunk(
    lines: list[str],
    hunk: Hunk,
    old_lines: list[Line],
    new_lines: list[Line],
    shift: int,
    offset: int,
    min_pos: int,
    frozen: int,
    incomplete_pos: int | None,
) -> tuple[int, list[Line], list[Line], int]:
    """
    Find where the hunk applies, mirroring GNU patch’s locate_hunk().

    Fuzz may ignore mismatching context lines before the first change and
    after the last one. The per-side allowance is fuzz + side’s context −
    max(both sides’ context), so a hunk with less context on one side —
    produced by diff only at the start or end of a file — anchors to that end
    of the source while negative. Only the lines actually matched get
    replaced, so ignored context lines are left as they are in the source.
    """
    prefix_context = 0
    while hunk.lines[prefix_context].tag == " ":
        prefix_context += 1
    suffix_context = 0
    while hunk.lines[-1 - suffix_context].tag == " ":
        suffix_context += 1
    # Both loops are bounded because parsing rejects hunks without any
    # changed lines.
    context = max(prefix_context, suffix_context)

    guess = hunk.old_start - 1 + shift + offset
    for fuzz in range(min(MAX_FUZZ, context) + 1):
        prefix_fuzz = fuzz + prefix_context - context
        suffix_fuzz = fuzz + suffix_context - context

        # context = max(prefix_context, suffix_context), so at most one of
        # prefix_fuzz and suffix_fuzz is negative.
        if prefix_fuzz < 0:
            # Can only match the start of the source.
            if (
                hunk.old_start <= 1
                and min_pos == 0
                and len(old_lines) - suffix_fuzz <= len(lines)
                and _lines_match(
                    lines,
                    0,
                    old_lines[: len(old_lines) - suffix_fuzz],
                    incomplete_pos,
                )
            ):
                matched_old = old_lines[: len(old_lines) - suffix_fuzz]
                matched_new = new_lines[: len(new_lines) - suffix_fuzz]
                return 0, matched_old, matched_new, offset
        elif suffix_fuzz < 0:
            # Can only match the end of the source.
            matched_old = old_lines[prefix_fuzz:]
            pos = len(lines) - len(matched_old)
            if pos >= max(min_pos, prefix_fuzz) and _lines_match(
                lines, pos, matched_old, incomplete_pos
            ):
                matched_new = new_lines[prefix_fuzz:]
                return pos, matched_old, matched_new, offset
        else:
            matched_old = old_lines[prefix_fuzz : len(old_lines) - suffix_fuzz]
            matched_new = new_lines[prefix_fuzz : len(new_lines) - suffix_fuzz]
            if not matched_old:
                # All of the hunk’s old lines were mismatching context: fall
                # back to inserting the remaining lines at the stated
                # position, as GNU patch does at maximum fuzz. Like GNU
                # patch, the constraints are in the unpatched source’s
                # coordinates: the hunk’s start — including its fuzz-ignored
                # leading context — is clamped so that it comes after the
                # frozen lines (which exclude the previous hunk’s trailing
                # context) and its old lines, less the fuzzed trailing
                # context, fit within the original source; the insertion then
                # lands after the fuzzed leading context.
                src_len = len(lines) - shift
                guess_src = guess - shift
                max_start = src_len - (len(old_lines) - suffix_fuzz)
                min_start = max(frozen - shift, 0)
                if min_start <= max_start:
                    start = max(min_start, min(guess_src, max_start))
                    return (
                        start + prefix_fuzz + shift,
                        matched_old,
                        matched_new,
                        offset + start - guess_src,
                    )
                continue
            # The matched region may start before min_pos by the number of
            # untrimmed leading context lines, like GNU patch — the changed
            # lines still land after min_pos.
            low = max(min_pos - prefix_context + 2 * prefix_fuzz, prefix_fuzz)
            found = _search(
                lines,
                matched_old,
                guess + prefix_fuzz,
                low,
                incomplete_pos,
            )
            if found is not None:
                return (
                    found,
                    matched_old,
                    matched_new,
                    offset + found - prefix_fuzz - guess,
                )
    raise HunkApplyError(
        f"Hunk #{hunk.number} failed to apply — its lines do not match the"
        + f" source (expected around line {hunk.old_start})."
    )


def _lines_match(
    lines: list[str], pos: int, target: list[Line], incomplete_pos: int | None
) -> bool:
    """
    Check the target hunk lines against the source lines at pos (in bounds
    per the callers).

    Phantom lines never match. Other lines require agreement on whether the
    line is the source’s final, newline-less line, like GNU patch — although
    a mismatch on a context line may still be ignored by fuzz.
    """
    for i, target_line in enumerate(target):
        if target_line.phantom or lines[pos + i] != target_line.text:
            return False
        if target_line.newline == (pos + i == incomplete_pos):
            return False
    return True


def _search(
    lines: list[str],
    target: list[Line],
    expected: int,
    min_pos: int,
    incomplete_pos: int | None,
) -> int | None:
    """
    Find target within lines[min_pos:], at the position closest to expected.
    """
    last_pos = len(lines) - len(target)
    if last_pos < min_pos:
        return None
    expected = max(min_pos, min(expected, last_pos))
    max_delta = max(expected - min_pos, last_pos - expected)
    for delta in range(max_delta + 1):
        for pos in (expected + delta, expected - delta):
            if min_pos <= pos <= last_pos and _lines_match(
                lines, pos, target, incomplete_pos
            ):
                return pos
    return None
