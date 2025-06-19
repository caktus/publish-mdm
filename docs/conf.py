# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = "Publish MDM Documentation"
copyright = "2025, Caktus Group"
author = "Caktus Group"
release = "2025"

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    "sphinxcontrib.mermaid",
    "sphinxcontrib.googleanalytics",
    "sphinx_copybutton",
    "sphinx_contributors",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]


# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = "shibuya"
html_static_path = ["_static"]

html_theme_options = {
    "accent_color": "grass",
    "github_url": "https://github.com/caktus/publish-mdm",
    "nav_links": [
        {"title": "Home", "url": "https://publishmdm.com/", "external": True},
    ],
}

# -- Google Analytics --------------------------------------------------------
googleanalytics_id = "G-14L02MHWV2"
