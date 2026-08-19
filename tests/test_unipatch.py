from __future__ import annotations

from textwrap import dedent

import pytest

from unipatch import (
    HunkApplyError,
    PatchError,
    PatchParseError,
    apply_patch,
)


def test_apply_simple():
    result = apply_patch(
        dedent(
            """\
            def sample():
                return 1
            """
        ),
        dedent(
            """\
            @@ -1,2 +1,2 @@
             def sample():
            -    return 1
            +    return 2
            """
        ),
        forwards=True,
    )
    assert result == dedent(
        """\
        def sample():
            return 2
        """
    )


def test_apply_reverse():
    result = apply_patch(
        dedent(
            """\
            def sample():
                return 2
            """
        ),
        dedent(
            """\
            @@ -1,2 +1,2 @@
             def sample():
            -    return 1
            +    return 2
            """
        ),
        forwards=False,
    )
    assert result == dedent(
        """\
        def sample():
            return 1
        """
    )


def test_apply_multiple_hunks():
    source = "one\ntwo\nthree\nfour\nfive\nsix\nseven\neight\n"
    patch = dedent(
        """\
        @@ -1,2 +1,2 @@
         one
        -two
        +TWO
        @@ -7,2 +7,2 @@
         seven
        -eight
        +EIGHT
        """
    )
    result = apply_patch(source, patch, forwards=True)
    assert result == "one\nTWO\nthree\nfour\nfive\nsix\nseven\nEIGHT\n"


def test_apply_file_headers_skipped():
    result = apply_patch(
        "apples\n",
        dedent(
            """\
            --- sample.py
            +++ sample.py
            @@ -1,1 +1,1 @@
            -apples
            +bananas
            """
        ),
        forwards=True,
    )
    assert result == "bananas\n"


def test_apply_count_defaults_to_one():
    result = apply_patch(
        "apples\n",
        dedent(
            """\
            @@ -1 +1 @@
            -apples
            +bananas
            """
        ),
        forwards=True,
    )
    assert result == "bananas\n"


def test_apply_offset_later():
    # The hunk targets line 1 but only matches at line 3.
    source = "pad1\npad2\napples\nbananas\n"
    patch = dedent(
        """\
        @@ -1,2 +1,2 @@
         apples
        -bananas
        +cherries
        """
    )
    result = apply_patch(source, patch, forwards=True)
    assert result == "pad1\npad2\napples\ncherries\n"


def test_apply_offset_earlier():
    # The hunk targets line 4 but only matches at line 1.
    source = "apples\nbananas\nx\ny\nz\n"
    patch = dedent(
        """\
        @@ -4,2 +4,2 @@
         apples
        -bananas
        +cherries
        """
    )
    result = apply_patch(source, patch, forwards=True)
    assert result == "apples\ncherries\nx\ny\nz\n"


def test_apply_fuzz_trailing_context():
    # The final context line does not match the source, so the hunk applies
    # with fuzz 1, leaving the source’s version of that line in place.
    source = "alpha\nbravo\ncharlie\ndelta\n"
    patch = dedent(
        """\
        @@ -1,4 +1,4 @@
         alpha
        -bravo
        +brian
         charlie
         DIFFERENT
        """
    )
    result = apply_patch(source, patch, forwards=True)
    assert result == "alpha\nbrian\ncharlie\ndelta\n"


def test_apply_fuzz_leading_context():
    source = "alpha\nbravo\ncharlie\ndelta\n"
    patch = dedent(
        """\
        @@ -1,4 +1,4 @@
         DIFFERENT
         bravo
        -charlie
        +carol
         delta
        """
    )
    result = apply_patch(source, patch, forwards=True)
    assert result == "alpha\nbravo\ncarol\ndelta\n"


def test_apply_fuzz_two():
    source = "alpha\nbravo\ncharlie\ndelta\necho\n"
    patch = dedent(
        """\
        @@ -1,5 +1,5 @@
         alpha
        -bravo
        +brian
         DIFFERENT1
         DIFFERENT2
         echo
        """
    )
    with pytest.raises(HunkApplyError):
        # Would require fuzz 3: two mismatching trailing context lines plus
        # a matching one after them.
        apply_patch(source, patch, forwards=True)

    patch = dedent(
        """\
        @@ -1,4 +1,4 @@
         alpha
        -bravo
        +brian
         DIFFERENT1
         DIFFERENT2
        """
    )
    result = apply_patch(source, patch, forwards=True)
    assert result == "alpha\nbrian\ncharlie\ndelta\necho\n"


def test_apply_fuzz_insertion_all_context_mismatching():
    # An insertion hunk whose only context line mismatches falls back to
    # inserting at the stated position, like GNU patch at maximum fuzz.
    result = apply_patch(
        "x\n",
        dedent(
            """\
            @@ -1 +1,2 @@
             WRONG
            +new
            """
        ),
        forwards=True,
    )
    assert result == "x\nnew\n"


def test_apply_fuzz_insertion_beyond_end_clamps():
    # A stated position beyond the end of the source clamps to the end,
    # like GNU patch (which reports a large negative offset).
    result = apply_patch(
        "x\n",
        dedent(
            """\
            @@ -50 +50,2 @@
             WRONG
            +new
            """
        ),
        forwards=True,
    )
    assert result == "x\nnew\n"


def test_apply_fuzz_insertion_fallback_over_previous_trailing_context():
    # The second hunk's context all mismatches; its fallback insertion may
    # land over the first hunk's trailing context line, which GNU patch does
    # not freeze, but not before the first hunk's changed lines.
    result = apply_patch(
        "alpha\nbravo\n",
        dedent(
            """\
            @@ -1,2 +1,3 @@
            -alpha\n            +ALPHA\n            +extra\n             bravo\n            @@ -5 +6,2 @@
             WRONG\n            +new\n            """
        ),
        forwards=True,
    )
    assert result == "ALPHA\nextra\nbravo\nnew\n"


def test_apply_fuzz_insertion_fallback_blocked_by_frozen_lines():
    # The second hunk's fallback insertion cannot fit after the first
    # hunk's changed (frozen) lines, so it fails, like GNU patch.
    with pytest.raises(HunkApplyError):
        apply_patch(
            "alpha\nbravo\n",
            dedent(
                """\
                @@ -1,2 +1,2 @@
                 alpha
                -bravo
                +BRAVO
                @@ -5,2 +5,3 @@
                 WRONG1
                +new
                 WRONG2
                """
            ),
            forwards=True,
        )


def test_apply_insertion_after_incomplete_final_line_continues_it():
    # The trailing context line mismatches (fuzz), so the insertion lands
    # after the source's newline-less final line: like GNU patch, the first
    # inserted line continues that line, since there is no newline to
    # insert after.
    result = apply_patch(
        "alpha\nbravo",
        dedent(
            """\
            @@ -2,2 +2,3 @@
             bravo
            +new
             WRONG
            """
        ),
        forwards=True,
    )
    assert result == "alpha\nbravonew\n"


def test_apply_insertion_after_incomplete_final_line_all_context_wrong():
    # Same merging behavior when every context line mismatches and the
    # fallback inserts at the stated position, at the end of the source.
    result = apply_patch(
        "alpha\nbravo",
        dedent(
            """\
            @@ -5,2 +5,3 @@
             WRONGA
            +new
             WRONGB
            """
        ),
        forwards=True,
    )
    assert result == "alpha\nbravonew\n"


def test_apply_insertion_at_end_without_trailing_context_adds_newline():
    # When the hunk ends with the inserted lines (no trailing context), GNU
    # patch supplies the newline missing from the source's final line before
    # appending, rather than continuing that line.
    result = apply_patch(
        "alpha\nbravo",
        dedent(
            """\
            @@ -2 +2,2 @@
             bravo
            +new
            """
        ),
        forwards=True,
    )
    assert result == "alpha\nbravo\nnew\n"


def test_apply_insertion_only_hunk_after_incomplete_final_line():
    # An insertion-only hunk (no context at all) also gets a supplied
    # newline after the source's incomplete final line, like GNU patch.
    result = apply_patch(
        "alpha\nbravo",
        dedent(
            """\
            @@ -2,0 +3 @@
            +new
            """
        ),
        forwards=True,
    )
    assert result == "alpha\nbravo\nnew\n"


def test_apply_fuzzed_insertion_after_incomplete_line_multiple_lines():
    # Only the first inserted line continues the incomplete final line;
    # later inserted lines follow normally, keeping the last one's
    # trailing-newline state.
    result = apply_patch(
        "alpha\nbravo",
        dedent(
            """\
            @@ -2,2 +2,4 @@
             bravo
            +one
            +two
             WRONG
            """
        ),
        forwards=True,
    )
    assert result == "alpha\nbravoone\ntwo\n"


def test_error_no_op_hunk():
    # GNU patch also rejects hunks without any changed lines as malformed.
    with pytest.raises(PatchParseError) as excinfo:
        apply_patch(
            "apples\nbananas\n",
            dedent(
                """\
                @@ -1,1 +1,1 @@
                 apples
                """
            ),
            forwards=True,
        )
    assert str(excinfo.value) == "Hunk #1 contains no changed lines."


def test_apply_delete_incomplete_last_line_requires_marker():
    # A deletion of the source's final, newline-less line only matches when
    # the patch marks the line as incomplete too, like GNU patch.
    unmarked = dedent(
        """\
        @@ -1,2 +1,2 @@
         apples
        -bananas
        +BANANAS
        """
    )
    with pytest.raises(HunkApplyError):
        apply_patch("apples\nbananas", unmarked, forwards=True)

    marked = dedent(
        """\
        @@ -1,2 +1,2 @@
         apples
        -bananas
        \\ No newline at end of file
        +BANANAS
        """
    )
    assert apply_patch("apples\nbananas", marked, forwards=True) == "apples\nBANANAS\n"
    with pytest.raises(HunkApplyError):
        # ...and a marked deletion does not match a complete line.
        apply_patch("apples\nbananas\n", marked, forwards=True)


def test_apply_trailing_context_keeps_source_newline_state():
    # Context lines are copied from the source, so the source's trailing
    # newline state is kept, whatever the patch context says, like GNU patch.
    result = apply_patch(
        "1\n0\ndelta",
        dedent(
            """\
            @@ -1,3 +1,2 @@
             1
            -0
             delta
            """
        ),
    )
    assert result == "1\ndelta"

    marked = dedent(
        """\
        @@ -1,2 +1,2 @@
        -apples
        +APPLES
         bananas
        \\ No newline at end of file
        """
    )
    assert (
        apply_patch("apples\nbananas\n", marked, forwards=True) == "APPLES\nbananas\n"
    )


def test_apply_hunk_larger_than_source():
    with pytest.raises(HunkApplyError):
        apply_patch(
            "apples\n",
            dedent(
                """\
                @@ -1,3 +1,0 @@
                -apples
                -bananas
                -cherries
                """
            ),
            forwards=True,
        )


def test_apply_start_anchored_hunk_far_line_number():
    # A hunk with less leading than trailing context could only anchor to the
    # start of the source, but its stated line number is far from the start,
    # so it only applies once fuzz trims the trailing context.
    source = "x\napples\nbananas\ncherries\n"
    patch = dedent(
        """\
        @@ -5,3 +5,3 @@
        -apples
        +APPLES
         bananas
         cherries
        """
    )
    result = apply_patch(source, patch, forwards=True)
    assert result == "x\nAPPLES\nbananas\ncherries\n"


def test_apply_fuzz_not_applied_to_changes():
    # Fuzz only ignores context lines, never '-' lines.
    source = "alpha\nbravo\n"
    patch = dedent(
        """\
        @@ -1,2 +1,2 @@
         alpha
        -DIFFERENT
        +charlie
        """
    )
    with pytest.raises(HunkApplyError):
        apply_patch(source, patch, forwards=True)


def test_apply_insertion_only_at_start():
    result = apply_patch(
        "apples\nbananas\n",
        dedent(
            """\
            @@ -0,0 +1,1 @@
            +new
            """
        ),
        forwards=True,
    )
    assert result == "new\napples\nbananas\n"


def test_apply_insertion_only_in_middle():
    result = apply_patch(
        "apples\nbananas\n",
        dedent(
            """\
            @@ -1,0 +2,1 @@
            +new
            """
        ),
        forwards=True,
    )
    assert result == "apples\nnew\nbananas\n"


def test_apply_insertion_only_at_end():
    result = apply_patch(
        "apples\nbananas\n",
        dedent(
            """\
            @@ -2,0 +3,1 @@
            +new
            """
        ),
        forwards=True,
    )
    assert result == "apples\nbananas\nnew\n"


def test_apply_insertion_into_empty_source():
    result = apply_patch(
        "",
        dedent(
            """\
            @@ -0,0 +1,2 @@
            +apples
            +bananas
            """
        ),
        forwards=True,
    )
    assert result == "apples\nbananas\n"


def test_apply_delete_all_lines():
    result = apply_patch(
        "apples\nbananas\n",
        dedent(
            """\
            @@ -1,2 +0,0 @@
            -apples
            -bananas
            """
        ),
        forwards=True,
    )
    assert result == ""


def test_apply_source_no_trailing_newline_untouched():
    result = apply_patch(
        "apples\nbananas",
        dedent(
            """\
            @@ -1,1 +1,1 @@
            -apples
            +cherries
            """
        ),
        forwards=True,
    )
    assert result == "cherries\nbananas"


def test_apply_remove_trailing_newline():
    patch = dedent(
        """\
        @@ -1,2 +1,2 @@
         alpha
        -bravo
        +bravo
        \\ No newline at end of file
        """
    )
    result = apply_patch("alpha\nbravo\n", patch, forwards=True)
    assert result == "alpha\nbravo"

    result = apply_patch("alpha\nbravo", patch, forwards=False)
    assert result == "alpha\nbravo\n"


def test_apply_add_trailing_newline():
    patch = dedent(
        """\
        @@ -1,2 +1,2 @@
         alpha
        -bravo
        \\ No newline at end of file
        +bravo
        """
    )
    result = apply_patch("alpha\nbravo", patch, forwards=True)
    assert result == "alpha\nbravo\n"

    result = apply_patch("alpha\nbravo\n", patch, forwards=False)
    assert result == "alpha\nbravo"


def test_apply_blank_line_treated_as_context():
    # Editors often strip the single space from blank context lines.
    source = "apples\n\nbananas\n"
    patch = dedent(
        """\
        @@ -1,3 +1,3 @@
        -apples
        +APPLES

         bananas
        """
    )
    result = apply_patch(source, patch, forwards=True)
    assert result == "APPLES\n\nbananas\n"


def test_apply_stripped_leading_space_treated_as_context():
    # GNU patch tolerates context lines that have lost their leading space.
    source = "apples\n\tbananas\n"
    patch = dedent(
        """\
        @@ -1,2 +1,2 @@
        -apples
        +APPLES
        \tbananas
        """
    )
    result = apply_patch(source, patch, forwards=True)
    assert result == "APPLES\n\tbananas\n"


def test_error_is_value_error():
    assert issubclass(PatchError, ValueError)


def test_error_no_hunks():
    with pytest.raises(PatchParseError) as excinfo:
        apply_patch("apples\n", "garbage\n", forwards=True)
    assert str(excinfo.value) == (
        "The patch does not contain any hunks; it does not appear to be valid"
        " unified diff format."
    )


def test_error_invalid_header():
    with pytest.raises(PatchParseError) as excinfo:
        apply_patch(
            "apples\n",
            dedent(
                """\
                @@ garbage @@
                -apples
                +bananas
                """
            ),
            forwards=True,
        )
    assert str(excinfo.value) == (
        "Hunk #1 has an invalid header line: '@@ garbage @@'."
    )


def test_apply_missing_trailing_context_tolerated():
    # Like GNU patch, a hunk may be cut short at the end of the patch when
    # only shared trailing context lines are missing.
    result = apply_patch(
        "apples\nbananas\n",
        dedent(
            """\
            @@ -1,2 +1,2 @@
            -apples
            +cherries
            """
        ),
        forwards=True,
    )
    assert result == "cherries\nbananas\n"


def test_error_truncated_hunk():
    with pytest.raises(PatchParseError) as excinfo:
        apply_patch(
            "apples\nbananas\ncherries\n",
            dedent(
                """\
                @@ -1,3 +1,2 @@
                -apples
                +dates
                """
            ),
            forwards=True,
        )
    assert str(excinfo.value) == (
        "Hunk #1 ends before all of the lines declared in its header."
    )


def test_error_empty_hunk():
    with pytest.raises(PatchParseError) as excinfo:
        apply_patch(
            "apples\nbananas\n",
            dedent(
                """\
                @@ -1,2 +1,2 @@
                """
            ),
            forwards=True,
        )
    assert str(excinfo.value) == (
        "Hunk #1 ends before all of the lines declared in its header."
    )


def test_error_invalid_line():
    with pytest.raises(PatchParseError) as excinfo:
        apply_patch(
            "apples\nbananas\n",
            dedent(
                """\
                @@ -1,2 +1,2 @@
                -apples
                +cherries
                junk
                """
            ),
            forwards=True,
        )
    assert str(excinfo.value) == "Hunk #1 has an invalid line: 'junk'."


def test_error_truncated_hunk_followed_by_next_hunk():
    patch = dedent(
        """\
        @@ -1,2 +1,2 @@
        -apples
        +cherries
        @@ -4,1 +4,1 @@
        -dates
        +elderberries
        """
    )
    with pytest.raises(PatchParseError) as excinfo:
        apply_patch("apples\nbananas\ncherries\ndates\n", patch, forwards=True)
    assert str(excinfo.value) == (
        "Hunk #1 ends before all of the lines declared in its header."
    )


def test_error_too_many_lines():
    with pytest.raises(PatchParseError) as excinfo:
        apply_patch(
            "apples\nbananas\n",
            dedent(
                """\
                @@ -1,1 +1,2 @@
                 apples
                -bananas
                +cherries
                """
            ),
            forwards=True,
        )
    assert str(excinfo.value) == (
        "Hunk #1 contains more lines than declared in its header."
    )


def test_error_no_newline_marker_first():
    with pytest.raises(PatchParseError) as excinfo:
        apply_patch(
            "apples\n",
            dedent(
                """\
                @@ -1,1 +1,1 @@
                \\ No newline at end of file
                -apples
                +bananas
                """
            ),
            forwards=True,
        )
    assert str(excinfo.value) == (
        "Hunk #1 has a '\\ No newline' marker line with no line before it."
    )


def test_error_hunk_does_not_apply():
    with pytest.raises(HunkApplyError) as excinfo:
        apply_patch(
            "apples\nbananas\n",
            dedent(
                """\
                @@ -1,2 +1,2 @@
                 apples
                -x
                +y
                """
            ),
            forwards=True,
        )
    assert str(excinfo.value) == (
        "Hunk #1 failed to apply — its lines do not match the source (expected"
        " around line 1)."
    )


def test_error_hunks_out_of_order():
    source = "apples\nbananas\ncherries\ndates\nelderberries\n"
    patch = dedent(
        """\
        @@ -4,1 +4,1 @@
        -dates
        +DATES
        @@ -1,1 +1,1 @@
        -apples
        +APPLES
        """
    )
    with pytest.raises(HunkApplyError) as excinfo:
        apply_patch(source, patch, forwards=True)
    assert "Hunk #2 failed to apply" in str(excinfo.value)
