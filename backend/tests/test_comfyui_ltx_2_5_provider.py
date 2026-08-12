from pathlib import Path

import pytest

from services.comfyui_ltx_2_5_provider import LtxI2VRequest, ProviderError, build_ltx_i2v_prompt_payload


def _template() -> dict:
    return {
        "395": {"inputs": {"image": "old.png"}},
        "398:376": {"inputs": {"value": "old prompt"}},
        "398:383": {"inputs": {"value": False}},
        "403": {"inputs": {"aspect_ratio": "1:1 (Square)", "megapixels": 0.4, "multiple": 32}},
        "398:362": {"inputs": {"value": 1}}, "398:361": {"inputs": {"value": 1}},
        "398:338": {"inputs": {"noise_seed": 1}}, "75": {"inputs": {"filename_prefix": "old"}},
    }


def _request(**changes: object) -> LtxI2VRequest:
    values = dict(prompt="A cinematic test.", input_image=Path("reference.jpg"), seed=42, prompt_enhance=True,
                  aspect_ratio="16:9 (Widescreen)", resolution_megapixels=0.9, width=1280, height=704,
                  duration_seconds=5.0, fps=24, frame_count=121, output_filename_prefix="ltx_scene_001")
    values.update(changes)
    return LtxI2VRequest(**values)


def test_captured_ltx_i2v_fields_map_without_mutating_template() -> None:
    template = _template()
    payload = build_ltx_i2v_prompt_payload(template, _request(), "staged/reference.png", "abcdef012345")
    prompt = payload["prompt"]
    assert template["395"]["inputs"]["image"] == "old.png"
    assert prompt["395"]["inputs"]["image"] == "staged/reference.png"
    assert prompt["398:376"]["inputs"]["value"] == "A cinematic test."
    assert prompt["398:383"]["inputs"]["value"] is True
    assert prompt["403"]["inputs"] == {"aspect_ratio": "16:9 (Widescreen)", "megapixels": 0.9, "multiple": 32}
    assert prompt["398:362"]["inputs"]["value"] == 5.0
    assert prompt["398:361"]["inputs"]["value"] == 24
    assert prompt["398:338"]["inputs"]["noise_seed"] == 42
    assert prompt["75"]["inputs"]["filename_prefix"] == "h3-director/ltx_scene_001_abcdef01"


@pytest.mark.parametrize("changes", [
    {"aspect_ratio": "1:1 (Square)"}, {"resolution_megapixels": 0.4}, {"width": 864},
    {"fps": 30}, {"duration_seconds": 10.0}, {"frame_count": 124},
])
def test_unverified_ltx_i2v_configuration_is_rejected(changes: dict[str, object]) -> None:
    with pytest.raises(ProviderError, match="verified LTX 2.5 I2V configuration"):
        build_ltx_i2v_prompt_payload(_template(), _request(**changes), "staged.png", "abc")
