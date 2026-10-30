import importlib


def test_package_imports() -> None:
    assert importlib.import_module("rn_forge.auth").__doc__
