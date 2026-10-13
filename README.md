# Eikon

*εἰκών, "image, likeness"*

Image generation for Hermes on your own ComfyUI: new pictures from words, or a picture you send reworked. It
starts from holonomic's dream settings and keeps its own, which never change her dreams.

Eikon is an image-generation provider. With `image_gen.provider: eikon`, every `image_generate` call goes to
your image server instead of a paid service: "draw me a lighthouse at dusk" makes a new picture, and a picture
sent with "make this a watercolor" is reworked towards the words. It draws the way her dreams do, with a copy
of holonomic's painter (`paint.py`), so ComfyUI (including Z-Image), the Stable Diffusion WebUI API and
OpenAI-style image servers all work.

## Install

```
sync-plugin eikon --restart            # or copy this folder to ~/.hermes/plugins/eikon
hermes plugins enable eikon
hermes config set image_gen.provider eikon
hermes eikon status
```

Then tick **Image Generation** for each platform in `hermes tools`, and restart Hermes.

## Settings

Eikon's settings are on its own page in Hermes Desktop (**Settings → Plugins → eikon**), stored under
`plugins.entries.eikon.settings` in config.yaml. Every setting left blank (empty, or 0) uses her matching
dream setting from `holonomic.json`, so a fresh install draws exactly the way her dreams do.

| Setting | Dream setting it follows when blank |
|---|---|
| `host`, `api` | `dream_image_host`, `dream_image_api` |
| `image_model`, `family` | `dream_image_model`, `dream_image_family` |
| `text_encoder`, `vae`, `text_encoder_on` | the Z-Image parts, likewise |
| `width`, `height` | the landscape size; portrait swaps them, square keeps the area |
| `steps`, `negative`, `timeout` | likewise |
| `strength` | how far a reworked picture may move from yours (0.1 barely, 1.0 almost new) |
| `enlarge`, `enlarge_model` | used when she asks for a larger picture |
| `edit_model`, `edit_family` | eikon's own: a different model for reworking, e.g. an instruction-editing model |

- **`hermes eikon status`** shows each value and where it came from: eikon, dreams or built-in.
- **`hermes eikon seed`** copies the dream values into eikon's own settings (only the blank ones; `--overwrite`
  replaces them all). After that the two are independent: change eikon's, and her dreams keep theirs.
- **`hermes eikon try "words" [--picture PATH]`** draws one picture now and prints where it was saved.

Eikon only ever reads `holonomic.json`; nothing here writes to it. Settings are read for every picture, so a
change in Desktop applies to the next one without a restart.

## Reworking a picture

With a picture, the image server starts from it instead of from noise, with `strength` deciding how much may
change. With an ordinary model that is a re-imagining: "make it a watercolor", "the same place in winter".
It keeps the composition and changes the look. Precise instructions ("remove the hat", "make the car red")
need an instruction-editing model in ComfyUI (e.g. Qwen-Image-Edit or FLUX Kontext). Set it as `edit_model`
and it is used only for reworking.

## Testing

```
HERMES_SRC=/path/to/hermes-agent python3 -m pytest tests            # settings and provider, image server faked
HERMES_SRC=/path/to/hermes-agent python3 scripts/try_live.py ~/.hermes   # a real drawing and a rework
```

`try_live.py` works on a copy of `holonomic.json` in a temporary folder and never writes the real one.

## Licence

MIT
