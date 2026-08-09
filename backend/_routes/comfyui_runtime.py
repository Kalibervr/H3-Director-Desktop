"""Read-only local ComfyUI capability route."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api_types import ComfyUIProbeRequest, ComfyUIProbeResponse
from app_handler import AppHandler
from state import get_state_service

router = APIRouter(prefix="/api/comfyui", tags=["comfyui-runtime"])


@router.post("/probe", response_model=ComfyUIProbeResponse)
def route_comfyui_probe(
    request: ComfyUIProbeRequest,
    handler: AppHandler = Depends(get_state_service),
) -> ComfyUIProbeResponse:
    return handler.comfyui_runtime.get_status(request)
