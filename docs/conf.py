# SPDX-FileCopyrightText: 2026 Faithful Oversight, LLC
# SPDX-License-Identifier: Apache-2.0
"""Sphinx configuration for the pakad documentation site.

The pages in this folder are plain Markdown that also read well on GitHub. The
site navigation is added here at build time, so no Sphinx-only markup appears in
the pages themselves.
"""

from __future__ import annotations

from importlib.metadata import version as _version
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sphinx.application import Sphinx

project = "pakad"
author = "Faithful Oversight, LLC"
copyright = "2026, Faithful Oversight, LLC"  # noqa: A001 - Sphinx setting name
release = _version("faithful-pakad")

extensions = ["myst_parser"]
source_suffix = {".md": "markdown"}
root_doc = "index"
exclude_patterns = ["_build"]
myst_heading_anchors = 3
nitpicky = True

html_theme = "furo"
html_title = f"pakad {release}"
html_show_sphinx = False
html_theme_options = {
    "source_repository": "https://github.com/faithful-oversight/faithful-pakad/",
    "source_branch": "main",
    "source_directory": "docs/",
}

NAVIGATION = {
    "index": [
        "quickstart",
        "usage",
        "profile",
        "output",
        "assessors",
        "limitations",
        "architecture",
        "threat-model",
        "releasing",
        "adr/index",
    ],
    "adr/index": [
        "0001-record-architecture-decisions",
        "0002-python-core",
        "0003-matching-semantics",
        "0004-documentation-site",
    ],
}
"""Page order for the site navigation, keyed by the page that lists them."""


def _add_navigation(_: Sphinx, docname: str, source: list[str]) -> None:
    pages = NAVIGATION.get(docname)
    if pages:
        source[0] += "\n\n```{toctree}\n:hidden:\n\n" + "\n".join(pages) + "\n```\n"


def setup(app: Sphinx) -> None:
    """Register the build-time navigation hook."""
    app.connect("source-read", _add_navigation)
