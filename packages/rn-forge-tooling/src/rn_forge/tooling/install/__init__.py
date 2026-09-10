"""Workstation install mechanics.

The *mechanics* of installing a release safely — extracting a bundle
(:func:`~rn_forge.tooling.install.archive.extract_archive`) — are identical
between the rn-forge tools and are owned here. The product coordinates (which
``$RNF_HOME``, which repository, which retention policy) stay in each product,
because their layouts differ.

The cross-process lock and the atomic symlink these were first written beside
carry no installer policy in their signatures and live in
:mod:`rn_forge.commons.fs.locks`.
"""

from rn_forge.tooling.install.archive import extract_archive

__all__ = ["extract_archive"]
