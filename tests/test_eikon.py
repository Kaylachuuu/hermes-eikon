"""Tests for eikon.  Settings tests need nothing; provider tests need Hermes' source (HERMES_SRC) and fake the image
server.  A real drawing is in scripts/try_live.py."""
import importlib.util
import json
import os
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for cand in (os.environ.get("HERMES_SRC"), ROOT.parent / "hermes-agent"):
    if cand and (Path(cand) / "agent" / "image_gen_provider.py").exists():
        sys.path.insert(0, str(cand))
        break


def _load():
    if "eikon" not in sys.modules:
        spec = importlib.util.spec_from_file_location("eikon", ROOT / "__init__.py", submodule_search_locations=[str(ROOT)])
        module = importlib.util.module_from_spec(spec)
        sys.modules["eikon"] = module
        spec.loader.exec_module(module)
    return sys.modules["eikon"]


def _settings():
    spec = importlib.util.spec_from_file_location("eikon_settings_only", ROOT / "settings.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


try:
    import agent.image_gen_provider  # noqa: F401
    HAVE_HERMES = True
except Exception:
    HAVE_HERMES = False

DREAMS = {"dream_image_api": "comfyui", "dream_image_host": "http://10.1.0.98:8188", "dream_image_width": 1024,
          "dream_image_height": 768, "dream_image_strength": 0.7, "dream_image_model": "z_image_turbo_bf16.safetensors",
          "dream_image_text_encoder_on": "cpu", "dream_image_enlarge": 2.0, "dream_image_people": "anyone"}


def test_blank_settings_follow_the_dreams_and_set_ones_win():
    s = _settings()
    values, sources = s.resolve({}, DREAMS)
    assert values["host"] == "http://10.1.0.98:8188" and sources["host"] == "dreams"
    assert values["model"] == "z_image_turbo_bf16.safetensors" and values["strength"] == 0.7
    assert values["steps"] == 0 and sources["steps"] == "built-in"
    values, sources = s.resolve({"model": "sd_xl_base_1.0.safetensors", "width": 0, "host": "  "}, DREAMS)
    assert values["model"] == "sd_xl_base_1.0.safetensors" and sources["model"] == "eikon"
    assert values["width"] == 1024 and sources["width"] == "dreams"          # 0 is blank
    assert sources["host"] == "dreams"                                       # whitespace is blank
    values, sources = s.resolve({}, {})
    assert values["api"] == "comfyui" and values["host"] == "" and sources["host"] == "built-in"


def test_seeding_copies_only_blank_settings_and_never_touches_the_dreams():
    s = _settings()
    dreams = dict(DREAMS)
    got = s.seed_values({"model": "mine.safetensors"}, dreams)
    assert "model" not in got and got["host"] == "http://10.1.0.98:8188" and got["enlarge"] == 2.0
    assert "people" not in got and "edit_model" not in got                   # only keys eikon has
    assert dreams == DREAMS


def test_the_painter_gets_dream_style_keys_and_a_separate_rework_model_only_when_reworking():
    s = _settings()
    values, _ = s.resolve({"edit_model": "sd_xl_base_1.0.safetensors", "edit_family": "checkpoint"}, DREAMS)
    plain = s.painter_settings(values)
    assert plain["dream_image_model"] == "z_image_turbo_bf16.safetensors" and plain["dream_image_host"].endswith(":8188")
    rework = s.painter_settings(values, editing=True)
    assert rework["dream_image_model"] == "sd_xl_base_1.0.safetensors" and rework["dream_image_family"] == "checkpoint"


def test_sizes_for_each_aspect():
    s = _settings()
    assert s.size_for("landscape", 1024, 768) == (1024, 768)
    assert s.size_for("portrait", 1024, 768) == (768, 1024)
    assert s.size_for("square", 1024, 768) == (896, 896)
    assert s.size_for("landscape", 768, 1024) == (1024, 768)


def test_the_manifest_offers_every_setting_in_the_desktop_form():
    import yaml  # PyYAML or ruamel via Hermes; only to check the manifest
    manifest = yaml.safe_load((ROOT / "plugin.yaml").read_text(encoding="utf-8"))
    s = _settings()
    assert set(manifest["config_schema"]) == set(s.DREAM_KEYS)
    for key, spec in manifest["config_schema"].items():
        assert spec.get("label") and spec.get("description"), key
        assert spec.get("default") in ("", 0), key                            # blank by default: follow the dreams


class _Ctx:
    def __init__(self, settings=None):
        self.settings = dict(settings or {})
        self.registered = []
        self.cli = []

    def get_config(self, key, default=None):
        return self.settings.get(key, default)

    def set_config(self, key, value):
        self.settings[key] = value

    def register_image_gen_provider(self, provider):
        self.registered.append(provider)

    def register_cli_command(self, *args, **kwargs):
        self.cli.append(args[0])


@pytest.fixture
def home(tmp_path, monkeypatch):
    (tmp_path / "holonomic.json").write_text(json.dumps(DREAMS))
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    import hermes_constants
    monkeypatch.setattr(hermes_constants, "get_hermes_home", lambda: tmp_path, raising=False)
    return tmp_path


def test_registers_a_provider_and_a_command(home):
    if not HAVE_HERMES:
        pytest.skip("needs HERMES_SRC")
    eikon = _load()
    ctx = _Ctx()
    eikon.register(ctx)
    provider = ctx.registered[0]
    assert provider.name == "eikon" and ctx.cli == ["eikon"] and provider.is_available()
    caps = provider.capabilities()
    assert caps["modalities"] == ["text", "image"] and caps["supports_upscale"] is True


def test_draws_and_reworks_through_the_painter(home, monkeypatch):
    if not HAVE_HERMES:
        pytest.skip("needs HERMES_SRC")
    eikon = _load()
    calls = []

    def fake_make_painter(sc):
        def paint(prompt, start, size):
            calls.append((sc["dream_image_model"], prompt, start, size))
            return b"\x89PNG\r\n\x1a\nfake"
        return paint

    monkeypatch.setattr(eikon._paint, "make_painter", fake_make_painter)
    import agent.image_gen_provider as igp
    saved = []
    monkeypatch.setattr(igp, "save_b64_image", lambda data, **kw: saved.append(data) or (home / "out.png"))
    ctx = _Ctx({"edit_model": "sd_xl_base_1.0.safetensors"})
    provider = eikon.make_provider(ctx)

    result = provider.generate("a lighthouse at dusk", "portrait")
    assert result["success"] and result["modality"] == "text" and result["size"] == "768x1024"
    assert calls[-1] == ("z_image_turbo_bf16.safetensors", "a lighthouse at dusk", None, (768, 1024))

    source = home / "photo.png"
    source.write_bytes(b"\x89PNG\r\n\x1a\nphoto")
    result = provider.generate("make it a watercolor", "landscape", image_url=str(source))
    assert result["success"] and result["modality"] == "image" and result["strength"] == 0.7
    assert calls[-1][0] == "sd_xl_base_1.0.safetensors" and calls[-1][2] == b"\x89PNG\r\n\x1a\nphoto"

    # a setting changed in Desktop applies to the next picture, and the dreams keep theirs
    ctx.settings["model"] = "other.safetensors"
    provider.generate("again", "square")
    assert calls[-1][0] == "other.safetensors" and calls[-1][3] == (896, 896)
    assert json.loads((home / "holonomic.json").read_text()) == DREAMS


def test_failures_come_back_as_tool_errors(home, monkeypatch):
    if not HAVE_HERMES:
        pytest.skip("needs HERMES_SRC")
    eikon = _load()

    def down(sc):
        def paint(prompt, start, size):
            raise eikon._paint.Unreachable("Could not reach the image server")
        return paint

    monkeypatch.setattr(eikon._paint, "make_painter", down)
    provider = eikon.make_provider(_Ctx())
    result = provider.generate("anything")
    assert result["success"] is False and result["error_type"] == "unreachable"
    assert provider.generate("   ")["error_type"] == "invalid_input"
    missing = provider.generate("rework", image_url=str(home / "nope.png"))
    assert missing["success"] is False and "no picture" in missing["error"].lower()


def test_seed_command_copies_dreams_into_eikon_only(home, capsys):
    if not HAVE_HERMES:
        pytest.skip("needs HERMES_SRC")
    eikon = _load()
    ctx = _Ctx({"model": "keep.safetensors"})
    eikon._seed(ctx, eikon._Settings(ctx), overwrite=False)
    assert ctx.settings["host"] == "http://10.1.0.98:8188" and ctx.settings["model"] == "keep.safetensors"
    eikon._seed(ctx, eikon._Settings(ctx), overwrite=True)
    assert ctx.settings["model"] == "z_image_turbo_bf16.safetensors"
    assert json.loads((home / "holonomic.json").read_text()) == DREAMS
