from services.ltx_2_5_geometry import ltx_geometry_matrix, resolve_ltx_geometry
def test_verified_ltx_geometry_explains_output_crop():
    value=resolve_ltx_geometry('16:9 (Widescreen)',0.9)
    assert (value.selector_width,value.selector_height,value.final_width,value.final_height)==(1280,736,1280,704)
def test_ltx_geometry_uses_final_64_pixel_grid():
    for ratio in ('9:16 (Portrait Widescreen)','1:1 (Square)','4:3 (Standard)','3:4 (Portrait Standard)'):
        value=resolve_ltx_geometry(ratio,0.9); assert value.selector_width%32==0 and value.selector_height%32==0 and value.final_width%64==0 and value.final_height%64==0


def test_ltx_geometry_matrix_keeps_candidate_status_separate_from_math() -> None:
    matrix = ltx_geometry_matrix()
    assert len(matrix) == 25
    portrait = next(item for item in matrix if item.aspect_ratio == "9:16 (Portrait Widescreen)" and item.megapixels == 0.9)
    assert (portrait.selector_width, portrait.selector_height) == (736, 1280)
    assert portrait.latent_grid == (11, 20)
    assert portrait.post_x2_latent_grid == (22, 40)
    assert (portrait.final_width, portrait.final_height) == (704, 1280)
