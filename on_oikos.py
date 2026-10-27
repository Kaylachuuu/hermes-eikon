"""Eikon as an Oikos faculty (Oikos: code/oikos/faculties.py, code/kernel/paint.py; design/eikon-on-oikos.md).

The same tool as under Hermes, `image_generate`: a new picture from words, or a picture reworked towards them.
`register(ctx)` in __init__.py sends Oikos's registrar here; oikos-faculty.yaml says what it may register.

    Hermes                                  Oikos
    an image_gen provider for Hermes'       her tool image_generate, registered by Eikon itself, with the schema
    image_generate                          Hermes gives it for Eikon
    paint.py, asking the host in its        oikos.paint: Oikos's one painter, which says where pictures are made
    settings                                (painter: in oikos.yaml); Eikon never names a host
    its settings, blank ones from her       its settings in faculty_settings, blank ones from the painter's own
    dream settings in holonomic.json        choices (her dream settings, in painter: how)
    Hermes' gateway sending the picture     oikos.show: kept beside the conversation, and sent to the client
    to the chat
    melete's looker.py, painting with       the board eikon.how: Eikon's own choices, which Melete paints with
    eikon's settings                        through oikos.paint
    hermes eikon status / try               console commands eikon.status, eikon.try
    hermes eikon seed                       not needed: the painter's choices are the fallback

Where her pictures are made moves in one place, Oikos's `painter:`, so it can go back onto her own card without
Eikon changing (Kayla, 2026-10-27; Athena, thread/2026-10-27-25-athena.md).

A picture to rework is one sent to her in a conversation (the path she was given), one Eikon made, or a URL; other
files on the machine Oikos runs on are not read.

Only stdlib imports at the top: Hermes executes every .py file in the plugin's folder when it loads it.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import settings as _settings

ASPECTS = ("landscape", "square", "portrait")
HOW_BOARD = "eikon.how"

# Eikon's setting -> the painter's name for it (Oikos's kernel/paint.py HOW). host, api and timeout are the painter's.
TO_PAINTER = {"image_model": "model", "family": "family", "text_encoder": "text_encoder", "vae": "vae",
              "text_encoder_on": "text_encoder_on", "width": "width", "height": "height", "steps": "steps",
              "strength": "strength", "negative": "negative", "enlarge": "enlarge", "enlarge_model": "enlarge_model"}
WHERE_KEYS = ("host", "api", "timeout")       # under Hermes Eikon's; on Oikos only the painter says where

DESCRIPTION = ("Generate high-quality images from text prompts{edit}. The picture is shown to the person you are "
               "talking with; the result's `image` field is where it is kept.")
PROMPT = {"type": "string", "description": "The text prompt describing the desired image (text-to-image) or the edit "
          "to apply (image-to-image). Be detailed and descriptive."}
ASPECT = {"type": "string", "enum": list(ASPECTS), "default": "landscape", "description": "The aspect ratio of the "
          "generated image. 'landscape' is 16:9 wide, 'portrait' is 16:9 tall, 'square' is 1:1."}
IMAGE_URL = {"type": "string", "description": "Source image to edit/transform (image-to-image). A public URL or an "
             "absolute local file path from the conversation. Omit for text-to-image."}
UPSCALE = {"type": "boolean", "description": "Post-generation high-resolution pass (~2x, extra cost/latency), off by "
           "default. A creative enhancer that can alter fine detail (rendered text, faces) — use only when "
           "resolution matters more than fidelity."}


def own(settings: Dict[str, Any]) -> Dict[str, Any]:
    """Eikon's own settings from Oikos's faculty_settings, the ones it knows."""
    return {k: v for k, v in (settings or {}).items() if k in _settings.DREAM_KEYS}


def resolve(mine: Dict[str, Any], painter: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, str]]:
    """The values Eikon draws with, by Eikon's names, and where each came from: 'eikon', 'the painter' or 'built-in'.
    `painter` is the painter's own choices, by its names."""
    values, sources = {}, {}
    for key in _settings.DREAM_KEYS:
        if key in WHERE_KEYS:
            continue
        theirs = painter.get(TO_PAINTER[key]) if key in TO_PAINTER else None
        if not _settings._blank(mine.get(key)):
            values[key], sources[key] = mine[key], "eikon"
        elif not _settings._blank(theirs):
            values[key], sources[key] = theirs, "the painter"
        else:
            values[key], sources[key] = _settings.BUILT_IN[key], "built-in"
    return values, sources


def how(values: Dict[str, Any], editing: bool = False) -> Dict[str, Any]:
    """Eikon's values as the painter's `how`. When reworking, a separate rework model and family, if set."""
    out = {TO_PAINTER[k]: v for k, v in values.items() if k in TO_PAINTER and not _settings._blank(v)}
    if editing and values.get("edit_model"):
        out["model"] = values["edit_model"]
        out.pop("family", None)
        if values.get("edit_family"):
            out["family"] = values["edit_family"]
    return out


def schema(can_enlarge: bool) -> Dict[str, Any]:
    props = {"prompt": PROMPT, "aspect_ratio": ASPECT, "image_url": IMAGE_URL}
    if can_enlarge:
        props["upscale"] = UPSCALE
    return {"name": "image_generate",
            "description": DESCRIPTION.format(edit=", or edit / transform an existing image by passing image_url"),
            "parameters": {"type": "object", "properties": props, "required": ["prompt"]}}


def read_source(source: str, allowed: List[Path], read_url) -> bytes:
    """The picture to rework: a path under one of `allowed` (a file:// URL too), an http(s) URL, or a data: URI."""
    from urllib.parse import unquote, urlparse
    source = (source or "").strip()
    if source.startswith(("data:", "http://", "https://")):
        return read_url(source)
    path = Path(unquote(urlparse(source).path) if source.startswith("file://") else source).expanduser()
    try:
        path = path.resolve(strict=True)
    except (OSError, RuntimeError):
        path = None
    if path is None or not path.is_file():
        raise ValueError(f"There is no picture at {source}.")
    if not any(path.is_relative_to(a.resolve()) for a in allowed if a.exists()):
        raise ValueError("Only a picture from the conversation, one made here, or a URL can be reworked.")
    return read_url(path.as_uri())


def register(oikos: Any) -> None:
    from . import _read_source, MAX_SOURCE_BYTES  # noqa: F401  (the same reading as under Hermes)

    mine = own(oikos.settings)
    painter = oikos.painter or {}
    values, sources = resolve(mine, painter.get("how") or {})
    home = Path(oikos.data_dir).parents[1]                 # Oikos's home: <home>/faculties/eikon
    allowed = [home / "conversations" / "images", Path(oikos.data_dir)]
    oikos.post(HOW_BOARD, {"how": how(values)})            # for Melete's workshop: drawn as Eikon draws

    def ready() -> bool:
        p = oikos.painter or {}
        return p.get("where") == "server" and bool(p.get("host")) and bool(p.get("api"))

    def can_enlarge() -> bool:
        return float(values.get("enlarge") or 0) > 1

    def draw(words: str, aspect: str, source: Optional[str], upscale: bool) -> Tuple[bytes, Dict[str, Any]]:
        editing = bool(source)
        chosen = how(values, editing=editing)
        size = _settings.size_for(aspect, values.get("width"), values.get("height"))
        start = read_source(source, allowed, _read_source) if editing else None
        picture = oikos.paint(words, size, start, chosen)
        extra: Dict[str, Any] = {"size": f"{size[0]}x{size[1]}", "model": chosen.get("model") or
                                 "(the server's first model)"}
        if editing:
            extra["strength"] = float(values.get("strength") or 0)
        factor = float(values.get("enlarge") or 0)
        if upscale and factor > 1:
            larger = oikos.enlarge(picture, (int(size[0] * factor), int(size[1] * factor)), chosen)
            if larger is not None:
                picture, extra["upscaled"] = larger, True
        return picture, extra

    def tool(args: Dict[str, Any], info: Any = None, **_: Any) -> str:
        words = str(args.get("prompt") or "").strip()
        aspect = str(args.get("aspect_ratio") or "landscape").lower()
        aspect = aspect if aspect in ASPECTS else "landscape"
        source = args.get("image_url") or next(iter(args.get("reference_image_urls") or []), None)
        common = {"provider": "eikon", "prompt": words, "aspect_ratio": aspect}
        if not words:
            return json.dumps({"success": False, "image": None, "error": "Prompt is required",
                               "error_type": "invalid_input", **common})
        try:
            picture, extra = draw(words, aspect, source, bool(args.get("upscale")))
            kept = oikos.show(info, picture)
        except oikos.Unreachable as e:
            return json.dumps({"success": False, "image": None, "error": f"{e} The image server may be off or "
                               "restarting; try again shortly.", "error_type": "unreachable", **common})
        except (oikos.PaintError, ValueError) as e:
            return json.dumps({"success": False, "image": None, "error": str(e), "error_type": "provider_error",
                               **common})
        return json.dumps({"success": True, "image": kept, "modality": "image" if source else "text",
                           "shown": True, **common, **extra}, ensure_ascii=False)

    oikos.tool("image_generate", schema(can_enlarge()), tool, available=ready)

    def status(args: List[str]) -> str:
        p = oikos.painter or {}
        where = (f"an image server ({p.get('api') or 'no api set'} at {p.get('host') or 'no host set'})"
                 if p.get("where") == "server" else "her own card" if p.get("where") == "card" else "nowhere: Oikos "
                 "has no painter")
        lines = [f"Eikon {oikos.manifest.version}: pictures are made on {where} (Oikos's painter: in oikos.yaml)",
                 "Settings (faculty_settings: eikon; blank = the painter's choice)"]
        for key in values:
            shown = "(blank)" if values[key] in ("", None) else values[key]
            lines.append(f"  {key:16} {str(shown):40} from {sources[key]}")
        ignored = [k for k in WHERE_KEYS if not _settings._blank(mine.get(k))]
        if ignored:
            lines.append(f"  {', '.join(ignored)}: set, but on Oikos only the painter says where pictures are made")
        if not ready():
            lines.append("image_generate is unavailable: the painter can't make pictures yet.")
        return "\n".join(lines)

    def try_(args: List[str]) -> str:
        words = " ".join(args).strip()
        if not words:
            return "Usage: eikon.try words..."
        try:
            picture, extra = draw(words, "landscape", None, False)
        except oikos.PaintError as e:
            return f"Not drawn: {e}"
        to = Path(oikos.data_dir) / "tries" / f"eikon_{time.strftime('%Y%m%d-%H%M%S')}.png"
        to.parent.mkdir(parents=True, exist_ok=True)
        to.write_bytes(picture)
        return f"Drawn: {to}  ({extra['size']}, {extra['model']})"

    oikos.command("eikon.status", status, help="Where pictures are made, and the settings Eikon draws with")
    oikos.command("eikon.try", try_, help="eikon.try words...: draw one picture now and say where it was saved",
                  changing=False)
