# aih: the README's look

**Family.** aih's README is drawn in Glass, the language of the gallowforge profile: real output as frosted-glass windows floating in a dark, softly lit space, with the one line that matters lifted out of its window toward you. aih, agent-guardrails and bwtidy share the renderer, the type and the composition grammar; each has its own accent light.

**The idea.** Every chat you have had, found in milliseconds. The hero is a real search: the best match is lifted out of the terminal, with the archive's stats and a filed chat floating behind it.

**Accent.** Violet, the colour aih's search hits take: light `#bcaaff` on dark windows, ink `#5b3fc4` on light pages, and a pool of `#5a43c8` light behind the glass. It is spent only on what aih found or proved: matching words, the lifted result, SAFE.

**Type.** Geist for headings and copy, Geist Mono for every line of output.

**Themes.** Each image has a dark version (on GitHub's `#0d1117`) and a light one (on `#ffffff`), with phone crops; the edges dissolve into the page. Terminals stay dark in both themes; the chat document is a dark page in the dark version and a light page in the light one.

**Truth.** Every window shows real output of aih on the synthetic "alex" setup (`scripts/readme-capture.sh`), copied word for word into the pages in `docs/readme/src/tex/`. Every number in the copy is read from that capture or from the smoke test.

**Rebuild.** `scripts/readme-visuals.sh` (or `--render` to reuse the last capture). The renderer is `docs/readme/src/glass/`: `scene.js` (three.js compositor), `grammar.js` (light, glass, type and compositions), `layouts.js` (this README's scenes) and `glass.cjs` (textures, scenes and WebP).
