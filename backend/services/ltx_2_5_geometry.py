"""Geometry resolver and non-rendering preset matrix for LTX 2.5 workflows.

The captured I2V and T2V graphs halve ``ResolutionSelector`` output before
creating the latent, then use the native x2 latent upscaler.  The latent node
uses whole 32-pixel cells, so the final result is a 64-pixel grid and can be
smaller than the selector's nominal output.  Keeping this derivation here
prevents the Director from displaying a selector size as though it were the
actual encoded video size.
"""
from __future__ import annotations
import math
from dataclasses import dataclass

RATIOS = {
    "1:1 (Square)": (1, 1),
    "3:4 (Portrait Standard)": (3, 4),
    "4:3 (Standard)": (4, 3),
    "9:16 (Portrait Widescreen)": (9, 16),
    "16:9 (Widescreen)": (16, 9),
}

# These are discovered from the live ResolutionSelector's 0.1 MP step.  They
# are contract candidates only; a caller must not interpret them as runtime
# verified merely because geometry can be calculated.
LTX_CANDIDATE_MEGAPIXELS = (0.4, 0.6, 0.8, 0.9, 1.0)

# Narrow, deliberate product-validation candidates.  These are not ordinary UI
# presets and stay contract-only until a real H3 Director render is adopted and
# ffprobe-verified.  They use the already proven 0.9 MP tier on the same local
# runtime, avoiding an uncontrolled sweep of ResolutionSelector's 0.1–16 MP.
LTX_PRODUCT_VALIDATION_PRESETS = frozenset({
    ("16:9 (Widescreen)", 0.9, 1280, 704),
    ("9:16 (Portrait Widescreen)", 0.9, 704, 1280),
    ("1:1 (Square)", 0.9, 960, 960),
})


def is_ltx_product_validation_preset(aspect_ratio: str, megapixels: float, width: int, height: int) -> bool:
    """True only for the bounded presets approved for one supervised render."""
    return (aspect_ratio, megapixels, width, height) in LTX_PRODUCT_VALIDATION_PRESETS
@dataclass(frozen=True)
class LtxGeometry:
    aspect_ratio: str
    megapixels: float
    selector_width: int
    selector_height: int
    generation_width: int
    generation_height: int
    final_width: int
    final_height: int

    @property
    def latent_grid(self) -> tuple[int, int]:
        return self.generation_width // 32, self.generation_height // 32

    @property
    def post_x2_latent_grid(self) -> tuple[int, int]:
        width, height = self.latent_grid
        return width * 2, height * 2


def resolve_ltx_geometry(aspect_ratio: str, megapixels: float) -> LtxGeometry:
    if aspect_ratio not in RATIOS or not 0.1 <= megapixels <= 16 or round(megapixels * 10) != megapixels * 10:
        raise ValueError("Unsupported LTX ResolutionSelector value.")
    rw, rh = RATIOS[aspect_ratio]
    scale = math.sqrt(megapixels * 1024 * 1024 / (rw * rh))
    sw = round(rw * scale / 32) * 32
    sh = round(rh * scale / 32) * 32
    gw, gh = int(sw / 2), int(sh / 2)
    # Contracts halve selector values; EmptyLTXVLatentVideo uses //32 cells,
    # then LTXV latent x2 plus VAE yields a 64-pixel final output grid.
    return LtxGeometry(aspect_ratio, megapixels, sw, sh, gw, gh, (gw // 32) * 64, (gh // 32) * 64)


def ltx_geometry_matrix() -> list[LtxGeometry]:
    """Return all currently inspected candidate geometries, without enablement."""
    return [
        resolve_ltx_geometry(aspect_ratio, megapixels)
        for aspect_ratio in RATIOS
        for megapixels in LTX_CANDIDATE_MEGAPIXELS
    ]
