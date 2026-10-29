"""Eikon (εἰκών, "image"): Hermes's image_generate tool on a ComfyUI the user runs.

Registers an image-generation provider named ``eikon``.  With ``image_gen.provider: eikon`` every
``image_generate`` call goes to the image server: a new picture from words, or, given a picture, that picture
reworked towards the words.  It draws the way holonomic's dreams do (the same painter), from its own settings,
which start from the dream settings and never change them.  See settings.py and README.md.

The same package loads into Oikos as a faculty (on_oikos.py, oikos-faculty.yaml), drawing with Oikos's one painter.
"""

from __future__ import annotations

import base64
import binascii
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import paint as _paint
from . import settings as _settings

__version__ = "0.3.0"

PLUGIN_ID = "eikon"
MAX_SOURCE_BYTES = 25 * 1024 * 1024


def _hermes_home() -> Path:
    from hermes_constants import get_hermes_home
    return Path(get_hermes_home())


def _read_source(source: str, timeout: float = 60.0) -> bytes:
    """The bytes of the picture to rework: a local path, a file:// or http(s) URL, or a data: URI."""
    source = source.strip()
    if source.startswith("data:"):
        try:
            return base64.b64decode(source.split(",", 1)[1])
        except (IndexError, binascii.Error) as exc:
            raise _paint.PaintError("The picture to rework could not be decoded.") from exc
    if source.startswith(("http://", "https://")):
        with urllib.request.urlopen(source, timeout=timeout) as resp:
            data = resp.read(MAX_SOURCE_BYTES + 1)
    else:
        path = Path(urllib.parse.unquote(urllib.parse.urlparse(source).path) if source.startswith("file://") else source)
        path = path.expanduser()
        if not path.is_file():
            raise _paint.PaintError(f"There is no picture at {source}.")
        data = path.read_bytes()[: MAX_SOURCE_BYTES + 1]
    if len(data) > MAX_SOURCE_BYTES:
        raise _paint.PaintError("The picture to rework is larger than 25 MB.")
    if not data:
        raise _paint.PaintError("The picture to rework is empty.")
    return data


def _load_image_gen_base():
    from agent.image_gen_provider import ImageGenProvider
    return ImageGenProvider


class _Settings:
    """Reads eikon's own settings (through the plugin context) and holonomic's, fresh on every call, so a change
    in Desktop applies from the next picture."""

    def __init__(self, ctx: Any = None) -> None:
        self._ctx = ctx

    def own(self) -> Dict[str, Any]:
        if self._ctx is None:
            return {}
        out = {}
        for key in _settings.DREAM_KEYS:
            try:
                value = self._ctx.get_config(key)
            except Exception:
                value = None
            if value is not None:
                out[key] = value
        return out

    def dream(self) -> Dict[str, Any]:
        return _settings.read_dream_settings(_hermes_home())

    def resolved(self):
        return _settings.resolve(self.own(), self.dream())


def make_provider(ctx: Any = None):
    base = _load_image_gen_base()
    from agent.image_gen_provider import error_response, resolve_aspect_ratio, save_b64_image, success_response

    class EikonImageGenProvider(base):
        def __init__(self) -> None:
            self.settings = _Settings(ctx)

        @property
        def name(self) -> str:
            return "eikon"

        @property
        def display_name(self) -> str:
            return "Eikon (your ComfyUI)"

        def is_available(self) -> bool:
            values, _ = self.settings.resolved()
            return bool(str(values.get("host") or "").strip()) and str(values.get("api") or "") in _paint.APIS

        def list_models(self) -> List[Dict[str, Any]]:
            values, _ = self.settings.resolved()
            model = str(values.get("image_model") or "") or "(the server's first model)"
            return [{"id": model, "display": f"{model} on {values.get('host') or '(no host set)'}",
                     "speed": "your GPU", "strengths": "Private, no per-image cost", "price": "free"}]

        def default_model(self) -> Optional[str]:
            return self.list_models()[0]["id"]

        def get_setup_schema(self) -> Dict[str, Any]:
            return {"name": "Eikon (your ComfyUI)", "badge": "local",
                    "tag": "Draws on your own image server; settings in Desktop under Settings > Plugins > eikon",
                    "env_vars": []}

        def capabilities(self) -> Dict[str, Any]:
            values, _ = self.settings.resolved()
            return {"modalities": ["text", "image"], "max_reference_images": 0,
                    "supports_upscale": float(values.get("enlarge") or 0) > 1}

        def generate(self, prompt: str, aspect_ratio: str = "landscape", *, image_url: Optional[str] = None,
                     reference_image_urls: Optional[List[str]] = None, **kwargs: Any) -> Dict[str, Any]:
            prompt = (prompt or "").strip()
            aspect_ratio = resolve_aspect_ratio(aspect_ratio)
            values, _ = self.settings.resolved()
            source = image_url or next(iter(reference_image_urls or []), None)
            editing = bool(source)
            sc = _settings.painter_settings(values, editing=editing)
            model = str(sc.get("dream_image_model") or "") or "(the server's first model)"
            common = dict(provider=self.name, model=model, prompt=prompt, aspect_ratio=aspect_ratio)
            if not prompt:
                return error_response(error="Prompt is required", error_type="invalid_input", **common)
            try:
                painter = _paint.make_painter(sc)
                size = _settings.size_for(aspect_ratio, values.get("width"), values.get("height"))
                start = _read_source(source) if editing else None
                picture = painter(prompt, start, size)
                upscaled = False
                if kwargs.get("upscale"):
                    enlarger = _paint.make_enlarger(sc)
                    factor = float(values.get("enlarge") or 0)
                    if enlarger is not None and factor > 1:
                        picture = enlarger(picture, (int(size[0] * factor), int(size[1] * factor)))
                        upscaled = True
                path = save_b64_image(base64.b64encode(picture).decode(), prefix="eikon", extension="png")
            except _paint.Unreachable as exc:
                return error_response(error=f"{exc} The image server may be off or restarting; try again shortly.",
                                      error_type="unreachable", **common)
            except _paint.PaintError as exc:
                return error_response(error=str(exc), error_type="provider_error", **common)
            except Exception as exc:                      # never let a backend failure take the tool down
                return error_response(error=f"{type(exc).__name__}: {exc}", error_type=type(exc).__name__, **common)
            extra = {"size": f"{size[0]}x{size[1]}", "host": values.get("host")}
            if editing:
                extra["strength"] = float(values.get("strength") or 0)
            if upscaled:
                extra["upscaled"] = True
            return success_response(image=str(path), modality="image" if editing else "text", extra=extra, **common)

    return EikonImageGenProvider()


# -- hermes eikon ------------------------------------------------------------------------------------------------

def _status(settings: _Settings) -> None:
    values, sources = settings.resolved()
    print("Eikon settings (Desktop: Settings > Plugins > eikon; blank = her dream setting)")
    for key in _settings.DREAM_KEYS:
        value = values[key]
        shown = "(blank)" if value in ("", None) else value
        print(f"  {key:16} {str(shown):40} from {sources[key]}")
    try:
        from hermes_cli.config import load_config
        provider = ((load_config() or {}).get("image_gen") or {}).get("provider")
    except Exception:
        provider = None
    print(f"\nimage_gen.provider is {provider or '(not set)'}" + ("" if provider == "eikon" else
          "; eikon draws for image_generate only when it is 'eikon' (hermes tools, or: hermes config set image_gen.provider eikon)"))


def _seed(ctx: Any, settings: _Settings, overwrite: bool) -> None:
    own, dream = settings.own(), settings.dream()
    if not dream:
        print("No holonomic.json with dream settings was found; nothing to copy.")
        return
    values = _settings.seed_values({} if overwrite else own, dream)
    if not values:
        print("Nothing to copy: every setting eikon leaves blank is blank in the dreams too, or eikon has its own.")
        return
    copied = 0
    for key, value in values.items():
        try:
            ctx.set_config(key, value)
        except Exception as exc:                  # one refused key must not stop the rest
            print(f"  {key:16}   not copied: {exc}")
            continue
        copied += 1
        print(f"  {key:16} = {value}")
    print(f"Copied {copied} dream setting(s) into eikon's own settings. Changing them changes only eikon; "
          "her dreams keep theirs.")


def _seed_once(ctx: Any, settings: _Settings) -> None:
    """The first time eikon loads where her dream settings exist, copy them into eikon's own blank settings, so the
    Desktop form shows real values to adjust.  Only once: later changes to her dreams stay out of eikon."""
    try:
        if ctx.state.get("seeded_from_dreams", default=False):
            return
        dream = settings.dream()
        if not dream:
            return                                    # no dream settings yet; try again on the next start
        for key, value in _settings.seed_values(settings.own(), dream).items():
            try:
                ctx.set_config(key, value)
            except Exception:                         # one refused key must not stop the rest
                pass
        ctx.state.set("seeded_from_dreams", True)
    except Exception:                                 # never stop the plugin loading over this
        pass


def _try(settings: _Settings, words: str, picture: Optional[str]) -> None:
    provider = make_provider(settings._ctx)
    result = provider.generate(words, "landscape", image_url=picture)
    if result.get("success"):
        print(f"Drawn: {result['image']}  ({result.get('size')}, {result['model']})")
    else:
        print(f"Not drawn: {result.get('error')}")


def _is_oikos(ctx) -> bool:
    """Oikos's registrar (its oikos/faculties.py) rather than Hermes' plugin context."""
    return all(hasattr(ctx, a) for a in ("manifest", "moment", "identity", "data_dir"))


def register(ctx) -> None:
    if _is_oikos(ctx):
        from .on_oikos import register as on_oikos
        on_oikos(ctx)
        return
    ctx.register_image_gen_provider(make_provider(ctx))
    settings = _Settings(ctx)
    _seed_once(ctx, settings)

    def setup(parser) -> None:
        subs = parser.add_subparsers(dest="eikon_command")
        subs.add_parser("status", help="Show the settings eikon draws with, and where each comes from")
        sd = subs.add_parser("seed", help="Copy her dream settings into eikon's own (only blank ones, unless --overwrite)")
        sd.add_argument("--overwrite", action="store_true", help="Replace eikon's own values too")
        tr = subs.add_parser("try", help="Draw one picture now and print where it was saved")
        tr.add_argument("words", help="What to draw")
        tr.add_argument("--picture", help="A picture to rework instead of starting from nothing (path or URL)")

    def handle(args) -> None:
        command = getattr(args, "eikon_command", None) or "status"
        if command == "seed":
            _seed(ctx, settings, bool(getattr(args, "overwrite", False)))
        elif command == "try":
            _try(settings, args.words, getattr(args, "picture", None))
        else:
            _status(settings)

    ctx.register_cli_command("eikon", "Eikon: pictures on your own image server", setup, handle,
                             description="Status, seeding from her dream settings, and a test drawing.")
