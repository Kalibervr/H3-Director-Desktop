"""Local-only H3 Director single-scene generation routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from api_types import (
    ComfyUIProbeResponse,
    H3Project,
    H3ContinuityPrepareResponse,
    H3ProjectCreateRequest,
    H3ProjectOpenRequest,
    H3ProjectRenderRequest,
    H3ProjectUpdateRequest,
    H3SceneUpdateRequest,
    H3SceneReorderRequest,
    H3RenderRun,
    H3SequenceStartRequest,
    MiniMaxH3RenderRequest,
    MiniMaxH3RenderResponse,
)
from app_handler import AppHandler
from state import get_state_service

router = APIRouter(prefix="/api/comfyui/minimax-h3", tags=["minimax-h3"])


@router.get("/status", response_model=ComfyUIProbeResponse)
def route_minimax_h3_status(
    base_url: str = Query(default="http://127.0.0.1:8188"),
    handler: AppHandler = Depends(get_state_service),
) -> ComfyUIProbeResponse:
    return handler.comfyui_minimax_h3.get_status(base_url)


@router.post("/render", response_model=MiniMaxH3RenderResponse)
def route_minimax_h3_render(
    request: MiniMaxH3RenderRequest,
    handler: AppHandler = Depends(get_state_service),
) -> MiniMaxH3RenderResponse:
    return handler.comfyui_minimax_h3.render_scene(request)


@router.get("/projects", response_model=list[H3Project])
def route_h3_projects(handler: AppHandler = Depends(get_state_service)) -> list[H3Project]:
    return handler.comfyui_minimax_h3.list_projects()


@router.post("/projects", response_model=H3Project)
def route_h3_project_create(
    request: H3ProjectCreateRequest,
    handler: AppHandler = Depends(get_state_service),
) -> H3Project:
    return handler.comfyui_minimax_h3.create_project(request)


@router.post("/projects/open", response_model=H3Project)
def route_h3_project_open(
    request: H3ProjectOpenRequest,
    handler: AppHandler = Depends(get_state_service),
) -> H3Project:
    return handler.comfyui_minimax_h3.reopen_project(request.project_root)


@router.get("/projects/{project_id}", response_model=H3Project)
def route_h3_project_get(
    project_id: str,
    handler: AppHandler = Depends(get_state_service),
) -> H3Project:
    return handler.comfyui_minimax_h3.get_project(project_id)


@router.patch("/projects/{project_id}", response_model=H3Project)
def route_h3_project_update(
    project_id: str,
    request: H3ProjectUpdateRequest,
    handler: AppHandler = Depends(get_state_service),
) -> H3Project:
    return handler.comfyui_minimax_h3.update_project(project_id, request)


@router.patch("/projects/{project_id}/scenes/{scene_id}", response_model=H3Project)
def route_h3_scene_update(
    project_id: str,
    scene_id: str,
    request: H3SceneUpdateRequest,
    handler: AppHandler = Depends(get_state_service),
) -> H3Project:
    return handler.comfyui_minimax_h3.update_scene(project_id, scene_id, request)


@router.post("/projects/{project_id}/scenes", response_model=H3Project)
def route_h3_scene_add(
    project_id: str,
    handler: AppHandler = Depends(get_state_service),
) -> H3Project:
    return handler.comfyui_minimax_h3.add_scene(project_id)


@router.post("/projects/{project_id}/scenes/reorder", response_model=H3Project)
def route_h3_scenes_reorder(
    project_id: str,
    request: H3SceneReorderRequest,
    handler: AppHandler = Depends(get_state_service),
) -> H3Project:
    return handler.comfyui_minimax_h3.reorder_scenes(project_id, request)


@router.post("/projects/{project_id}/scenes/{scene_id}/select", response_model=H3Project)
def route_h3_scene_select(
    project_id: str,
    scene_id: str,
    handler: AppHandler = Depends(get_state_service),
) -> H3Project:
    return handler.comfyui_minimax_h3.select_scene(project_id, scene_id)


@router.post("/projects/{project_id}/scenes/{scene_id}/duplicate", response_model=H3Project)
def route_h3_scene_duplicate(
    project_id: str,
    scene_id: str,
    handler: AppHandler = Depends(get_state_service),
) -> H3Project:
    return handler.comfyui_minimax_h3.duplicate_scene(project_id, scene_id)


@router.delete("/projects/{project_id}/scenes/{scene_id}", response_model=H3Project)
def route_h3_scene_delete(
    project_id: str,
    scene_id: str,
    handler: AppHandler = Depends(get_state_service),
) -> H3Project:
    return handler.comfyui_minimax_h3.delete_scene(project_id, scene_id)


@router.post("/projects/{project_id}/scenes/{scene_id}/render", response_model=H3Project)
def route_h3_scene_render(
    project_id: str,
    scene_id: str,
    request: H3ProjectRenderRequest,
    handler: AppHandler = Depends(get_state_service),
) -> H3Project:
    return handler.comfyui_minimax_h3.render_project_scene(project_id, scene_id, request)


@router.post(
    "/projects/{project_id}/scenes/{scene_id}/continuity",
    response_model=H3ContinuityPrepareResponse,
)
def route_h3_scene_continuity(
    project_id: str,
    scene_id: str,
    handler: AppHandler = Depends(get_state_service),
) -> H3ContinuityPrepareResponse:
    return handler.comfyui_minimax_h3.prepare_continuity(project_id, scene_id)


@router.post("/projects/{project_id}/sequences", response_model=H3RenderRun)
def route_h3_sequence_start(
    project_id: str,
    request: H3SequenceStartRequest,
    handler: AppHandler = Depends(get_state_service),
) -> H3RenderRun:
    return handler.comfyui_minimax_h3.start_sequence(project_id, request)


@router.post("/projects/{project_id}/sequences/{run_id}/stop", response_model=H3RenderRun)
def route_h3_sequence_stop(
    project_id: str,
    run_id: str,
    handler: AppHandler = Depends(get_state_service),
) -> H3RenderRun:
    return handler.comfyui_minimax_h3.stop_sequence(project_id, run_id)
