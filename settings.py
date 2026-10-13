"""Eikon's settings, and where each value comes from.

Eikon keeps its own settings under ``plugins.entries.eikon.settings`` in config.yaml (the form in Desktop's
Settings > Plugins > eikon).  A setting left blank (an empty text, or 0 for a number) falls back to the matching
dream setting in holonomic.json, so a fresh install draws the way her dreams do.  Eikon only ever reads
holonomic.json; ``hermes eikon seed`` copies the dream values into eikon's own settings, after which the two are
independent.

Only the standard library is imported: Hermes executes every top-level module in this folder at load.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, Tuple

# eikon key -> holonomic dream key it falls back to (None: eikon's own, no dream counterpart)
DREAM_KEYS: Dict[str, Any] = {
    "api": "dream_image_api",
    "host": "dream_image_host",
    "image_model": "dream_image_model",     # not "model": Hermes reserves that name in plugin settings
    "family": "dream_image_family",
    "text_encoder": "dream_image_text_encoder",
    "vae": "dream_image_vae",
    "text_encoder_on": "dream_image_text_encoder_on",
    "width": "dream_image_width",
    "height": "dream_image_height",
    "steps": "dream_image_steps",
    "strength": "dream_image_strength",
    "negative": "dream_image_negative",
    "timeout": "dream_image_timeout",
    "enlarge": "dream_image_enlarge",
    "enlarge_model": "dream_image_enlarge_model",
    "edit_model": None,
    "edit_family": None,
}

# Used when neither eikon nor holonomic has a value.
BUILT_IN: Dict[str, Any] = {
    "api": "comfyui", "host": "", "image_model": "", "family": "", "text_encoder": "", "vae": "", "text_encoder_on": "",
    "width": 1024, "height": 768, "steps": 0, "strength": 0.6, "negative": "", "timeout": 600,
    "enlarge": 0.0, "enlarge_model": "", "edit_model": "", "edit_family": "",
}


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip()) or (
        isinstance(value, (int, float)) and not isinstance(value, bool) and value == 0)


def read_dream_settings(hermes_home: Path) -> Dict[str, Any]:
    """holonomic's settings, or {} when holonomic is not installed or its file is unreadable."""
    try:
        data = json.loads((Path(hermes_home) / "holonomic.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def resolve(own: Dict[str, Any], dream: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, str]]:
    """The values eikon draws with, and for each key where it came from: 'eikon', 'dreams' or 'built-in'."""
    values, sources = {}, {}
    for key, dream_key in DREAM_KEYS.items():
        mine = (own or {}).get(key)
        theirs = (dream or {}).get(dream_key) if dream_key else None
        if not _blank(mine):
            values[key], sources[key] = mine, "eikon"
        elif not _blank(theirs):
            values[key], sources[key] = theirs, "dreams"
        else:
            values[key], sources[key] = BUILT_IN[key], "built-in"
    return values, sources


def seed_values(own: Dict[str, Any], dream: Dict[str, Any]) -> Dict[str, Any]:
    """The dream values to copy into eikon's settings: only keys eikon leaves blank and the dreams have set."""
    out = {}
    for key, dream_key in DREAM_KEYS.items():
        if dream_key and _blank((own or {}).get(key)) and not _blank((dream or {}).get(dream_key)):
            out[key] = dream[dream_key]
    return out


def painter_settings(values: Dict[str, Any], editing: bool = False) -> Dict[str, Any]:
    """The settings dict holonomic's painter reads (dream_image_* keys).  When editing, a separate edit model and
    family are used if set."""
    sc = {dream_key: values[key] for key, dream_key in DREAM_KEYS.items() if dream_key}
    if editing and values.get("edit_model"):
        sc["dream_image_model"] = values["edit_model"]
        sc["dream_image_family"] = values.get("edit_family") or ""
    return sc


def size_for(aspect_ratio: str, width: int, height: int) -> Tuple[int, int]:
    """Hermes asks for landscape, portrait or square.  Landscape is the configured size, portrait the same turned on
    its side, and square the same area, each side a multiple of 64."""
    width, height = max(int(width or 0), 64), max(int(height or 0), 64)
    long_side, short_side = max(width, height), min(width, height)
    if aspect_ratio == "portrait":
        return short_side, long_side
    if aspect_ratio == "square":
        side = max(64, int(round(math.sqrt(width * height) / 64.0)) * 64)
        return side, side
    return long_side, short_side
