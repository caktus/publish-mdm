"""
Security regression tests for the publish_mdm app.
"""


# ---------------------------------------------------------------------------
# VULN-004: Hardcoded SECRET_KEY committed to VCS
# ---------------------------------------------------------------------------


class TestHardcodedSecretKey:
    """VULN-004: base.py must not contain the original compromised SECRET_KEY.

    The key 'django-insecure-t1586xqgp3f7k%0@k-gfxpewx)9!cl$*z!a!sckvu0gcoy3afj'
    was committed to version control and must be treated as permanently compromised.
    base.py must use os.environ.get() for the key, not a hardcoded string.
    """

    COMPROMISED_KEY = "django-insecure-t1586xqgp3f7k%0@k-gfxpewx)9!cl$*z!a!sckvu0gcoy3afj"

    def test_compromised_key_not_in_base_settings(self):
        """The original hardcoded key must not appear anywhere in base.py."""
        from pathlib import Path

        base_path = Path("config/settings/base.py")
        content = base_path.read_text()
        assert self.COMPROMISED_KEY not in content, (
            "The compromised SECRET_KEY is still hardcoded in config/settings/base.py. "
            "Remove it and use os.environ.get('DJANGO_SECRET_KEY', ...) with a placeholder."
        )

    def test_base_settings_uses_env_var_for_secret_key(self):
        """base.py must read SECRET_KEY from the environment, not hardcode it."""
        import ast
        from pathlib import Path

        base_path = Path("config/settings/base.py")
        source = base_path.read_text()
        tree = ast.parse(source)

        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "SECRET_KEY" for t in node.targets)
            ):
                continue
            # The RHS must involve os.environ.get or os.getenv, not a bare string
            is_env_lookup = False
            for subnode in ast.walk(node.value):
                if isinstance(subnode, ast.Call):
                    func = subnode.func
                    if isinstance(func, ast.Attribute) and func.attr in ("get", "getenv"):
                        is_env_lookup = True
                        break
            assert is_env_lookup, (
                "SECRET_KEY in config/settings/base.py must be read from the environment "
                "via os.environ.get() or os.getenv(), not hardcoded."
            )
            return
        raise AssertionError("Could not find SECRET_KEY assignment in config/settings/base.py")
