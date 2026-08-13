# Sequence-aware Next-scene Prompt Assistant

H3 Director keeps two complementary local continuity systems.

- **Visual continuity** uses the selected previous render version and its immutable last/offset frame artifact as the I2V input.
- **Semantic continuity** stores compact, confirmed project-local entries keyed by stable scene and render-version IDs. It provides story context for a short next-scene instruction.

`Develop Next Scene` never renders or silently replaces a prompt. It returns a reviewable draft. `Suggest Next Scene` returns three concise action ideas; choosing one only supplies an instruction for development.

Only immutable adopted render versions add confirmed history. Drafts and abandoned suggestions do not alter continuity memory. Explicit user instructions remain primary and may change prior conditions. Existing projects migrate with empty memory and show **Not recorded** rather than fabricated history.

This is local-only: Ollama is addressed only through its loopback endpoint. MiniMax Prompt Only -> MiniMax I2V and LTX T2V -> LTX I2V retain their existing frame-continuation paths; semantic context supplements, never replaces, the source-frame provenance.
