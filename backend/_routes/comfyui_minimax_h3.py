"""Local-only H3 Director single-scene generation routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from api_types import ComfyUIProbeResponse, MiniMaxH3RenderRequest, MiniMaxH3RenderResponse
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
