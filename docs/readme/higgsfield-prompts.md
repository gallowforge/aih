# Higgsfield prompt (optional, not generated)

The README images are finished without it. One material would gain from a real photograph: the oak of the drawer fronts and cabinet, which is now a procedural CSS grain (`.oak` in `src/aih.css`). Everything else (cards, type, stamps, output) stays in code, because it is real output or drawn from it.

## 1. Oak drawer-front plate (texture)

**One idea.** The worn quarter-sawn oak of a 1920s library card catalogue, lit like the paper around it, so the cabinet in the hero and the numbers banner feels like furniture, not a gradient.

**Model.** Higgsfield Soul (photoreal still). It renders wood grain, patina and soft daylight convincingly, and it is the house model family for stills. One image, 16:9, highest resolution offered. Estimated cost: one generation.

**Use.** Cropped and tiled as the background image of `.oak`, under the existing bevel, label holder and pull, which stay in code. Grain must run horizontally.

**Prompt.**

> Straight-on macro photograph of a flat panel of antique quarter-sawn white oak from a library card catalogue drawer front, filling the whole frame edge to edge. Honey-brown oak (#9C683B) with fine horizontal grain and gentle medullary ray flecks, a century of hand wear, soft satin shellac finish with faint micro scratches. Even, diffuse daylight from the upper left, no hotspots, no vignette. Shot square to the surface, no perspective, no depth of field falloff, everything sharp. Calm, warm, archival, museum conservation photography.

**Slots.**
- Subject: one flat oak panel, nothing on it.
- Surface: quarter-sawn white oak, horizontal grain, ray flecks, shellac.
- Light: diffuse daylight, upper left, low contrast.
- Camera: orthographic feel, square to the surface, full-frame fill, sharp edge to edge.
- Colour: honey brown around `#9C683B`, no red or orange cast.

**Negative.** No hardware, no brass, no label holder, no handles, no keyholes, no text, no letters, no numbers, no logos, no knots, no cracks, no screws, no joints or seams, no edges of the panel, no shadows of objects, no perspective, no vignette, no bokeh, no people, no hands, no glossy varnish, no orange tint, no 3D render look.

**Acceptance check.** Grain runs horizontally across the full width; the colour samples within about 10% of `#9C683B`; no feature repeats visibly when tiled at 600 px; brass and type stay legible on top of it in the hero and numbers renders.
