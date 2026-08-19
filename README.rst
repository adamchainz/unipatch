========
unipatch
========

.. image:: https://img.shields.io/github/actions/workflow/status/adamchainz/unipatch/main.yml.svg?branch=main&style=for-the-badge
   :target: https://github.com/adamchainz/unipatch/actions?workflow=CI

.. image:: https://img.shields.io/badge/Coverage-100%25-success?style=for-the-badge
   :target: https://github.com/adamchainz/unipatch/actions?workflow=CI

.. image:: https://img.shields.io/pypi/v/unipatch.svg?style=for-the-badge
   :target: https://pypi.org/project/unipatch/

.. image:: https://img.shields.io/badge/code%20style-black-000000.svg?style=for-the-badge
   :target: https://github.com/psf/black

.. image:: https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white&style=for-the-badge
   :target: https://github.com/pre-commit/pre-commit
   :alt: pre-commit

Apply unified diffs in memory, compatible with GNU patch.

A quick example:

.. code-block:: pycon

    >>> import textwrap
    >>> import unipatch
    >>> patch = textwrap.dedent(
    ...     """\
    ...     @@ -1,2 +1,3 @@
    ...      apples
    ...      bananas
    ...     +cherries
    ...     """
    ... )
    >>> print(unipatch.apply_patch("apples\nbananas\n", patch))
    apples
    bananas
    cherries
    <BLANKLINE>

Installation
============

Use **pip**:

.. code-block:: sh

    python -m pip install unipatch

Python 3.10 to 3.15 supported.

API
===

``apply_patch(source: str, patch: str, forwards: bool=True)``
------------------------------------------------------------

Apply the unified diff in the string ``patch`` to the string ``source`` and return the resulting string.
Pass ``forwards=False`` to apply the patch in reverse, undoing it instead.

Raises ``PatchError`` if the patch cannot be parsed or does not apply.

.. code-block:: pycon

    >>> unipatch.apply_patch("a\nb\n", "@@ -1 +1 @@\n-a\n+c\n")
    'c\nb\n'
    >>> unipatch.apply_patch("c\nb\n", "@@ -1 +1 @@\n-a\n+c\n", forwards=False)
    'a\nb\n'

``PatchError``
--------------

The base exception class, a subclass of ``ValueError``.
It has two subclasses:

* ``PatchParseError``: the patch is not valid unified diff format.
* ``HunkApplyError``: the patch parsed, but a hunk’s lines do not match the source.

Exception messages name the failing hunk and what went wrong.

Behaviour
=========

unipatch follows the behaviour of the GNU ``patch`` commandline utility, verified by differentially testing against it with randomized inputs:

* Hunks may apply at an *offset* from the line numbers stated in their ``@@`` headers, matching by content, with a found offset carrying forward to later hunks.

* A *fuzz factor* ignores up to two mismatching context lines at the edges of a hunk. Ignored context lines are left as they are in the source.
  A hunk with less context on one side, as ``diff`` produces at the start or end of a file, only applies at that edge of the source.

* Oddities are tolerated like GNU ``patch``:

  * Hunks cut short at the end of the patch
  * Context lines that have lost their leading space (empty and tab-led lines)
  * ``\ No newline at end of file`` markers

Only unified diff format is supported, not the older context or ``ed`` formats.
Hence the name is ``unipatch``.
