import importlib
import subprocess
import sys


def test_package_imports() -> None:
    assert importlib.import_module("rn_forge.data").__doc__


def test_core_import_loads_no_pandas() -> None:
    code = "import sys, rn_forge.data; assert 'pandas' not in sys.modules"
    subprocess.run([sys.executable, "-c", code], check=True)
