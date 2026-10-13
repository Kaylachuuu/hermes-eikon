"""Draw for real: one new picture, then that picture reworked, on the image server in HOME's holonomic.json (or
eikon settings given as KEY=VALUE).  Writes nothing to holonomic.json.

    HERMES_SRC=/path/to/hermes-agent python3 scripts/try_live.py HOME [KEY=VALUE ...]
"""
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, os.environ["HERMES_SRC"])
home = Path(sys.argv[1]).expanduser()
own = {}
for pair in sys.argv[2:]:
    key, _, value = pair.partition("=")
    own[key] = json.loads(value) if value[:1] in "0123456789." else value

scratch = Path(tempfile.mkdtemp(prefix="eikon-live-"))
if (home / "holonomic.json").exists():
    shutil.copy(home / "holonomic.json", scratch / "holonomic.json")     # a copy: the real file is never opened for writing
os.environ["HERMES_HOME"] = str(scratch)
import hermes_constants
hermes_constants.get_hermes_home = lambda: scratch

spec = importlib.util.spec_from_file_location("eikon", ROOT / "__init__.py", submodule_search_locations=[str(ROOT)])
eikon = importlib.util.module_from_spec(spec)
sys.modules["eikon"] = eikon
spec.loader.exec_module(eikon)


class Ctx:
    def get_config(self, key, default=None):
        return own.get(key, default)


provider = eikon.make_provider(Ctx())
values, sources = eikon._Settings(Ctx()).resolved()
print("drawing with", {k: v for k, v in values.items() if v not in ("", 0, 0.0)})
t = time.time()
first = provider.generate("a small stone lighthouse on a cliff at dusk, warm light in the window, watercolor", "landscape")
print(round(time.time() - t, 1), "s", json.dumps(first, indent=1))
if first.get("success"):
    t = time.time()
    second = provider.generate("the same lighthouse in deep winter at night, snow falling, moonlight", "landscape",
                               image_url=first["image"])
    print(round(time.time() - t, 1), "s", json.dumps(second, indent=1))
