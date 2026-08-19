from __future__ import annotations

import difflib

from hypothesis import assume, example, given
from hypothesis import strategies as st

from unipatch import (
    PatchError,
    apply_patch,
)

line_texts = st.text(
    alphabet="abcdefgh -+@\\\t",
    max_size=10,
)


def join_lines(lines: list[str]) -> str:
    return "".join(f"{line}\n" for line in lines)


def make_diff(a: list[str], b: list[str], context: int) -> str:
    return "\n".join(difflib.unified_diff(a, b, lineterm="", n=context))


@given(
    a=st.lists(line_texts, max_size=30),
    b=st.lists(line_texts, max_size=30),
    context=st.integers(min_value=0, max_value=4),
)
def test_property_round_trip(a, b, context):
    """
    A diff between two texts applies forwards to produce the second, and in
    reverse to recover the first.
    """
    assume(a != b)
    patch = make_diff(a, b, context)

    assert apply_patch(join_lines(a), patch, forwards=True) == join_lines(b)
    assert apply_patch(join_lines(b), patch, forwards=False) == join_lines(a)


# Unique lines, so every hunk matches at exactly one place in the source.
unique_lines = st.lists(
    st.text(alphabet="abcdefgh", min_size=1, max_size=8),
    min_size=7,
    max_size=20,
    unique=True,
)
replacement_lines = st.lists(
    st.text(alphabet="mnopqrst", min_size=1, max_size=8),
    max_size=5,
    unique=True,
)
# Distinct alphabet, so padding lines can never match hunk lines.
pad_lines = st.lists(
    st.text(alphabet="XYZ", min_size=1, max_size=8),
    max_size=10,
)


@given(
    a=unique_lines,
    replacement=replacement_lines,
    data=st.data(),
    prefix=pad_lines,
    suffix=pad_lines,
)
def test_property_apply_at_offset(a, replacement, data, prefix, suffix):
    """
    A diff still applies when the source has extra lines before and after the
    patched region, shifting the hunks from their stated line numbers.

    Only interior lines are changed, keeping full context on both sides of
    every hunk: a hunk with clipped context only applies at the edge of the
    source, like GNU patch.
    """
    # Replace some lines in the middle of a, at least 3 lines from each end.
    start = data.draw(st.integers(min_value=3, max_value=len(a) - 3))
    end = data.draw(st.integers(min_value=start, max_value=len(a) - 3))
    b = a[:start] + replacement + a[end:]
    assume(a != b)
    patch = make_diff(a, b, context=3)

    source = join_lines(prefix + a + suffix)
    expected = join_lines(prefix + b + suffix)
    assert apply_patch(source, patch, forwards=True) == expected


garbage_patch_lines = st.one_of(
    st.builds(
        "@@ -{},{} +{},{} @@".format,
        st.integers(0, 5),
        st.integers(0, 5),
        st.integers(0, 5),
        st.integers(0, 5),
    ),
    st.text(alphabet=" -+\\@xy", max_size=6),
)
garbage_patches = st.one_of(
    st.text(max_size=200),
    st.lists(garbage_patch_lines, max_size=15).map("\n".join),
)


@given(source=st.text(max_size=200), patch=garbage_patches)
@example(source="a\n", patch="@@ -1 +1 @@\n-a\n+b")
@example(source="a\n", patch="garbage")
def test_property_garbage_input(source, patch):
    """
    Arbitrary patch input either applies or raises PatchError, never anything
    else.
    """
    for forwards in (True, False):
        try:
            result = apply_patch(source, patch, forwards=forwards)
        except PatchError:
            pass
        else:
            assert isinstance(result, str)
