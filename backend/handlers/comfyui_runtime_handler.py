"""Sanitized read-only ComfyUI runtime status handler."""

from __future__ import annotations

from api_types import ComfyUIProbeRequest, ComfyUIProbeResponse
from services.comfyui_runtime_probe import ComfyUIRuntimeProbe


class ComfyUIRuntimeHandler:
    def __init__(self, probe: ComfyUIRuntimeProbe | None = None) -> None:
        self._probe = probe or ComfyUIRuntimeProbe()

    def get_status(self, request: ComfyUIProbeRequest) -> ComfyUIProbeResponse:
        result = self._probe.probe(
            base_url=request.base_url,
            workflow=request.workflow,
            production_runtime=request.production_runtime,
        )
        return ComfyUIProbeResponse(
            status=result.status,
            comfyui_version=result.comfyui_version,
            required_nodes_present=list(result.required_nodes_present),
            required_nodes_missing=list(result.required_nodes_missing),
            required_models_present=list(result.required_models_present),
            required_models_missing=list(result.required_models_missing),
            workflow_contract_valid=result.workflow_contract_valid,
            errors=list(result.errors),
        )
