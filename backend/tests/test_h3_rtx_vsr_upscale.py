from services.h3_rtx_vsr_upscale import build_rtx_vsr_workflow


def test_rtx_vsr_workflow_uses_verified_nodes_and_audio() -> None:
    workflow = build_rtx_vsr_workflow(
        staged_video="h3-director-upscale/source.mp4", source_fps=24.0,
        target_width=1280, target_height=960, filename_prefix="h3-director/upscale_test",
    )
    assert workflow["1"]["class_type"] == "VHS_LoadVideo"
    assert workflow["2"]["class_type"] == "ImageResizeKJv2"
    assert workflow["2"]["inputs"]["upscale_method"] == "nvidia_rtx_vsr"
    assert workflow["2"]["inputs"]["device"] == "gpu"
    assert workflow["3"]["class_type"] == "VHS_VideoCombine"
    assert workflow["3"]["inputs"]["audio"] == ["1", 2]
    assert workflow["3"]["inputs"]["frame_rate"] == 24.0


def test_rtx_vsr_workflow_uses_exact_target_dimensions() -> None:
    workflow = build_rtx_vsr_workflow(
        staged_video="h3-director-upscale/source.mp4", source_fps=24.0,
        target_width=1728, target_height=960, filename_prefix="h3-director/upscale_test",
    )
    assert workflow["2"]["inputs"]["width"] == 1728
    assert workflow["2"]["inputs"]["height"] == 960
    assert workflow["2"]["inputs"]["divisible_by"] == 8
