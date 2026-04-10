Contributing
============

This contributing guide is currently a work in progress. For now, please visit
our `GitHub repository <https://github.com/caktus/publish-mdm>`_ for the most
up-to-date information about contributing to this project.

Setup
-----

Pull Request Guardrails
-----------------------

PRs that target ``main`` are validated by the GitHub Actions workflow
``.github/workflows/main-pr-check.yaml``.

The guardrail currently enforces two checks:

1. PR author must be a human account (GitHub ``User`` type).
2. PR title must follow Conventional Commit style using one of these types:
   ``feat``, ``fix``, ``chore``, ``ci``, ``docs``, ``perf``, or ``refactor``.

Examples of accepted PR titles:

* ``feat: add organization policy import``
* ``fix: prevent duplicate form template slugs``
* ``docs: clarify local setup prerequisites``

If the check fails, update the PR title or confirm the PR was opened from a
human account and re-run checks.

Documentation
~~~~~~~~~~~~~

The documentation is built using Sphinx.

To build the documentation, run the following commands (requires ``uv``, see :doc:`local setup docs <local-development/setup>`):

.. code-block:: bash

   cd docs
   uv sync --locked --only-group docs
   sphinx-autobuild --port 8001 . _build/html


Now visit http://127.0.0.1:8001/ in your browser to view the documentation.
