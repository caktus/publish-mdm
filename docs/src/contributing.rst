Contributing
============

This contributing guide is currently a work in progress. For now, please visit
our `GitHub repository <https://github.com/caktus/publish-mdm>`_ for the most
up-to-date information about contributing to this project.

Setup
-----

Documentation
~~~~~~~~~~~~~

The documentation is built using Sphinx.

To build the documentation, run the following commands (requires ``uv``, see :doc:`local setup docs <local-development/setup>`):

.. code-block:: bash

   cd docs
   uv sync --locked --only-group docs
   sphinx-autobuild --port 8001 . _build/html


Now visit http://127.0.0.1:8001/ in your browser to view the documentation.
