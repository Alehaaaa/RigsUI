import sys

try:
    import importlib
except ImportError:
    importlib = None

import os
import io

TOOL_TITLE = "Rigs Library"
MOD_NAME = "RigsUI"

# Expose version
try:
    _v_path = os.path.join(os.path.dirname(__file__), "VERSION")
    with io.open(_v_path, "rb") as _f:
        _content = _f.read()
        try:
            VERSION = _content.decode("utf-8").strip()
        except UnicodeDecodeError:
            VERSION = _content.decode("utf-16").strip()
except Exception:
    VERSION = "0.0.0"


def show(mod_name=MOD_NAME):
    for name in list(sys.modules.keys()):
        if name == mod_name or name.startswith(mod_name + "."):
            sys.modules.pop(name, None)

    if importlib and hasattr(importlib, "invalidate_caches"):
        importlib.invalidate_caches()
        rigsui = importlib.import_module(mod_name)
        main_mod = importlib.import_module(mod_name + ".main")
    else:
        rigsui = __import__(mod_name)
        main_mod = __import__(mod_name + ".main", fromlist=["main"])

    main_mod.LibraryUI.showUI()

    return rigsui


if __name__ == "__main__":
    show()
