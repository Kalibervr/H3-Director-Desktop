"""Tests for /api/runtime-policy endpoint."""

from __future__ import annotations

from state.app_settings import (
    AppSettings,
    should_image_generate_with_fal_api,
    should_video_generate_with_ltx_api,
)


def test_runtime_policy_true(client, test_state):
    test_state.config.local_generations_mode = "unsupported"

    response = client.get("/api/runtime-policy")
    assert response.status_code == 200
    assert response.json() == {"force_api_generations": True}


def test_local_only_mode_never_forces_cloud_api(client, test_state):
    test_state.config.local_generations_mode = "unsupported"
    test_state.config.cloud_api_enabled = False

    response = client.get("/api/runtime-policy")
    assert response.status_code == 200
    assert response.json() == {"force_api_generations": False}


def test_local_only_mode_ignores_cloud_keys_and_preferences():
    settings = AppSettings(
        ltx_api_key="ltx-key",
        fal_api_key="fal-key",
        user_prefers_ltx_api_video_generations=True,
        user_prefers_fal_api_image_generations=True,
    )

    assert not should_video_generate_with_ltx_api(
        cloud_api_enabled=False,
        force_api_generations=True,
        settings=settings,
    )
    assert not should_image_generate_with_fal_api(
        cloud_api_enabled=False,
        force_api_generations=True,
        settings=settings,
    )


def test_runtime_policy_false(client, test_state):
    test_state.config.local_generations_mode = "full_models_loading"

    response = client.get("/api/runtime-policy")
    assert response.status_code == 200
    assert response.json() == {"force_api_generations": False}
