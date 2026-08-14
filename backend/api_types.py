"""Pydantic request/response models and typed aliases for ltx2_server."""

from __future__ import annotations

import re
from typing import Annotated
from typing import Any, Literal, NamedTuple, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StringConstraints, model_validator

NonEmptyPrompt = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
H3AspectRatio = Literal[
    "1:1 (Square)",
    "16:9 (Widescreen)",
    "9:16 (Portrait Widescreen)",
]
H3ResolutionMegapixels = Literal[0.4, 0.6, 0.8, 0.9, 1.0]
H3WorkflowProfileId = Literal[
    "minimax_h3_image_to_video",
    "minimax_h3_no_reference",
    "ltx_2_5_text_to_video",
    "ltx_2_5_image_to_video",
]
H3WorkflowMode = Literal["image_to_video", "text_to_video"]
H3_RESOLUTION_PRESETS: dict[H3AspectRatio, dict[H3ResolutionMegapixels, tuple[int, int]]] = {
    "1:1 (Square)": {0.4: (640, 640), 0.6: (800, 800), 0.8: (928, 928), 0.9: (960, 960), 1.0: (1024, 1024)},
    "16:9 (Widescreen)": {0.4: (864, 480), 0.6: (1056, 608), 0.8: (1216, 672), 0.9: (1280, 704), 1.0: (1376, 768)},
    "9:16 (Portrait Widescreen)": {0.4: (480, 864), 0.6: (608, 1056), 0.8: (672, 1216), 0.9: (736, 1280), 1.0: (768, 1376)},
}
ModelCheckpointID = Literal[
    "ltx-2.3-22b-distilled",
    "ltx-2.3-22b-distilled-1.1",
    "ltx-2.3-spatial-upscaler-x2-1.0",
    "ltx-2.3-spatial-upscaler-x2-1.1",
    "ltx-2.3-22b-ic-lora-union-control-ref0.5",
    "dpt-hybrid-midas",
    "yolox-l-torchscript",
    "dw-ll-ucoco-384-bs5",
    "gemma-3-12b-it-qat-q4_0-unquantized",
    "z-image-turbo",
]
LTXLocalModelId = Literal["ltx-2.3-22b-distilled-1.1", "ltx-2.3-22b-distilled"]


class ImageConditioningInput(NamedTuple):
    """Image conditioning triplet used by all video pipelines."""

    path: str
    frame_idx: int
    strength: float


JsonObject: TypeAlias = dict[str, object]
VideoCameraMotion = Literal[
    "none",
    "dolly_in",
    "dolly_out",
    "dolly_left",
    "dolly_right",
    "jib_up",
    "jib_down",
    "static",
    "focus_shift",
]


# ============================================================
# Response Models
# ============================================================


class ModelStatusItem(BaseModel):
    id: str
    name: str
    loaded: bool
    downloaded: bool


class GpuTelemetry(BaseModel):
    name: str
    vram: int
    vramUsed: int


class HealthResponse(BaseModel):
    status: Literal["ok"]
    models_loaded: bool
    active_model: str | None
    gpu_info: GpuTelemetry
    sage_attention: bool
    models_status: list[ModelStatusItem]


class GpuInfoResponse(BaseModel):
    cuda_available: bool
    mps_available: bool = False
    gpu_available: bool = False
    gpu_name: str | None
    vram_gb: int | None
    gpu_info: GpuTelemetry


class MpsMemoryResponse(BaseModel):
    """Read-only Apple Silicon MPS memory snapshot, MiB. Fields are None off MPS."""
    available: bool
    allocated_mib: int | None = None
    driver_mib: int | None = None
    recommended_max_mib: int | None = None


class RuntimePolicyResponse(BaseModel):
    force_api_generations: bool


class ComfyUIProbeRequest(BaseModel):
    model_config = ConfigDict(strict=True)
    base_url: str
    workflow: dict[str, JsonValue]
    production_runtime: bool = False


class ComfyUIProbeResponse(BaseModel):
    model_config = ConfigDict(strict=True)
    status: Literal["connected", "unavailable", "incompatible"]
    comfyui_version: str | None = None
    required_nodes_present: list[str]
    required_nodes_missing: list[str]
    required_models_present: list[str]
    required_models_missing: list[str]
    workflow_contract_valid: bool
    errors: list[str]


class MiniMaxH3RenderRequest(BaseModel):
    model_config = ConfigDict(strict=True)
    base_url: str = "http://127.0.0.1:8188"
    prompt: NonEmptyPrompt
    input_image: str
    reference_fit: Literal["fill_crop", "fit", "stretch"] = "fill_crop"
    aspect_ratio: H3AspectRatio = "1:1 (Square)"
    resolution_megapixels: H3ResolutionMegapixels = 0.4
    seed: int = Field(ge=0, le=0xFFFFFFFFFFFFFFFF)
    width: int = Field(default=640, ge=1)
    height: int = Field(default=640, ge=1)
    duration_seconds: float = Field(default=5.0, gt=0)
    fps: int = Field(default=24, ge=1)
    output_filename_prefix: str = Field(default="MiniMax_H3", min_length=1, max_length=64)


class MiniMaxH3VideoProbeResponse(BaseModel):
    model_config = ConfigDict(strict=True)
    codec: str
    width: int
    height: int
    fps: str
    duration_seconds: float
    frame_count: int | None
    audio_present: bool


class MiniMaxH3RenderResponse(BaseModel):
    model_config = ConfigDict(strict=True)
    status: Literal["complete"] = "complete"
    prompt_id: str
    output_file: str
    metadata_file: str
    video: MiniMaxH3VideoProbeResponse


H3SceneStatus = Literal[
    "idle", "queued", "preparing", "submitted", "rendering", "encoding",
    "verifying", "complete", "failed", "cancelled",
]
H3SceneMode = Literal["new_shot", "continue_previous", "same_character_new_shot"]
H3ContinuityStrategy = Literal["last_valid_frame", "offset_from_end"]
H3SequenceKind = Literal["scene", "from_here", "all"]
H3QueueState = Literal[
    "waiting", "preparing", "rendering", "verifying", "complete", "failed",
    "skipped", "cancelled",
]
H3SequenceStatus = Literal["running", "complete", "failed", "cancelled"]


class H3ProjectSettings(BaseModel):
    model_config = ConfigDict(strict=True)
    width: int = Field(ge=1)
    height: int = Field(ge=1)
    fps: int = Field(ge=1)
    duration_seconds: float = Field(gt=0)
    frame_count: int = Field(ge=1)


class H3RenderVersion(BaseModel):
    model_config = ConfigDict(strict=True)
    id: str
    number: int = Field(ge=1)
    created_at: str
    # Coordinator-owned execution interval: provider invocation through a
    # verified/adopted usable MP4.  It intentionally excludes UI idle time.
    render_started_at: str | None = None
    render_completed_at: str | None = None
    render_elapsed_seconds: float | None = Field(default=None, ge=0)
    root: str
    video_file: str
    metadata_file: str
    prompt: str
    final_prompt: str | None = None
    raw_user_prompt: str | None = None
    improved_prompt: str | None = None
    native_enhanced_prompt: str | None = None
    final_submitted_prompt: str | None = None
    native_prompt_enhance: bool | None = None
    audio_mode: Literal["natural_ambience", "dialogue", "silent"] = "natural_ambience"
    no_speech: bool = False
    no_music: bool = False
    custom_audio_instruction: str = ""
    input_image_reference: str
    seed: int = Field(ge=0)
    width: int = Field(ge=1)
    height: int = Field(ge=1)
    fps: int = Field(ge=1)
    duration_seconds: float = Field(gt=0)
    frame_count: int | None
    prompt_id: str
    input_image_sha256: str
    workflow_sha256: str
    output_sha256: str
    ffprobe: MiniMaxH3VideoProbeResponse
    upscale_variants: list["H3UpscaleVariant"] = Field(default_factory=list)


class H3UpscaleVariant(BaseModel):
    """Immutable locally-derived post-process asset; never replaces its source render."""
    model_config = ConfigDict(strict=True)
    id: str
    number: int = Field(ge=1)
    created_at: str
    processing_elapsed_seconds: float | None = Field(default=None, ge=0)
    root: str
    video_file: str
    metadata_file: str
    backend: Literal["nvidia_rtx_vsr"]
    source_render_version_id: str
    source_width: int = Field(ge=1)
    source_height: int = Field(ge=1)
    width: int = Field(ge=1)
    height: int = Field(ge=1)
    scale: Literal[2]
    fps: int = Field(ge=1)
    duration_seconds: float = Field(gt=0)
    audio_preserved: bool
    prompt_id: str
    source_video_sha256: str
    output_sha256: str
    ffprobe: MiniMaxH3VideoProbeResponse


class H3ContinuityArtifact(BaseModel):
    model_config = ConfigDict(strict=True)
    id: str
    number: int = Field(ge=1)
    created_at: str
    root: str
    image_file: str
    metadata_file: str
    image_sha256: str
    source_scene_id: str
    source_render_version_id: str
    source_video_reference: str
    source_video_sha256: str
    frame_index: int = Field(ge=0)
    timestamp_seconds: float = Field(ge=0)
    strategy: H3ContinuityStrategy
    offset_from_end_frames: int = Field(ge=0)
    source_frame_count: int = Field(ge=1)
    source_fps: str


class H3Scene(BaseModel):
    model_config = ConfigDict(strict=True)
    id: str
    storage_name: str = Field(pattern=r"^scene_[0-9]{3}$")
    order: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=120)
    prompt: str
    # User-confirmed outcome is deliberately separate from the planned prompt: a
    # generated clip may end somewhere different than its prompt described.
    confirmed_outcome: str = Field(default="", max_length=600)
    # The accepted immutable render that this user-confirmed outcome describes.
    # A scene may have several materially different versions, so this must not
    # silently carry forward when the user selects another version.
    confirmed_outcome_render_version_id: str | None = None
    audio_mode: Literal["natural_ambience", "dialogue", "silent"] = "natural_ambience"
    no_speech: bool = False
    no_music: bool = False
    custom_audio_instruction: str = ""
    reference_image: str | None
    reference_fit: Literal["fill_crop", "fit", "stretch"] = "fill_crop"
    ltx_prompt_enhance: bool = False
    # A scene retains its own generation contract so visual-frame continuation can
    # transition the *next* scene from a prompt-only/T2V source to its matching
    # I2V profile without rewriting the completed source scene.
    workflow_profile_id: H3WorkflowProfileId = "minimax_h3_image_to_video"
    workflow_mode: H3WorkflowMode = "image_to_video"
    aspect_ratio: H3AspectRatio = "1:1 (Square)"
    resolution_megapixels: H3ResolutionMegapixels = 0.4
    width: int = Field(ge=1)
    height: int = Field(ge=1)
    fps: int = Field(ge=1)
    duration_seconds: float = Field(gt=0)
    frame_count: int = Field(ge=1)
    seed: int = Field(ge=0, le=0xFFFFFFFFFFFFFFFF)
    mode: H3SceneMode
    continuity_strategy: H3ContinuityStrategy
    continuity_offset_frames: int = Field(ge=0)
    selected_continuity_artifact_id: str | None
    continuity_artifacts: list[H3ContinuityArtifact]
    status: H3SceneStatus
    selected_render_version_id: str | None
    render_versions: list[H3RenderVersion]
    last_error: str | None
    active_prompt_id: str | None
    current_phase: str | None
    progress_value: int | None = Field(default=None, ge=0)
    progress_max: int | None = Field(default=None, ge=1)
    diagnostics: str | None


class H3SequenceItem(BaseModel):
    model_config = ConfigDict(strict=True)
    scene_id: str
    scene_order: int = Field(ge=1)
    state: H3QueueState
    started_at: str | None = None
    completed_at: str | None = None
    render_version_id: str | None = None
    prompt_id: str | None = None
    continuity_artifact_id: str | None = None
    error: str | None = None
    current_phase: str | None = None
    progress_value: int | None = Field(default=None, ge=0)
    progress_max: int | None = Field(default=None, ge=1)
    diagnostics: str | None = None


class H3RenderRun(BaseModel):
    model_config = ConfigDict(strict=True)
    id: str
    kind: H3SequenceKind
    status: H3SequenceStatus
    started_at: str
    completed_at: str | None = None
    ordered_scene_ids: list[str]
    current_scene_id: str | None = None
    stop_after_current_requested: bool = False
    failure_or_cancel_reason: str | None = None
    items: list[H3SequenceItem]


class H3ContinuityMemoryEntry(BaseModel):
    """Compact confirmed history; never records an unrendered prompt draft as fact."""
    model_config = ConfigDict(strict=True)
    scene_id: str
    render_version_id: str
    summary: str = Field(min_length=1, max_length=1200)
    current_state: str = Field(min_length=1, max_length=600)
    audio_summary: str = Field(default="", max_length=600)


class H3ContinuityMemory(BaseModel):
    model_config = ConfigDict(strict=True)
    entries: list[H3ContinuityMemoryEntry] = Field(default_factory=list)


class H3Project(BaseModel):
    model_config = ConfigDict(strict=True)
    schema_version: Literal[18]
    id: str
    name: str = Field(min_length=1, max_length=120)
    created_at: str
    updated_at: str
    project_root: str
    settings: H3ProjectSettings
    sequence_mode: Literal["independent_shots", "continuous_sequence"] = "independent_shots"
    workflow_profile_id: H3WorkflowProfileId = "minimax_h3_image_to_video"
    workflow_mode: H3WorkflowMode = "image_to_video"
    scenes: list[H3Scene]
    selected_scene_id: str
    render_runs: list[H3RenderRun]
    continuity_memory: H3ContinuityMemory = Field(default_factory=H3ContinuityMemory)


class H3ProjectCreateRequest(BaseModel):
    model_config = ConfigDict(strict=True)
    name: str = Field(min_length=1, max_length=120)
    scene_count: int = Field(default=1, ge=1, le=999)
    sequence_mode: Literal["independent_shots", "continuous_sequence"] = "independent_shots"
    workflow_profile_id: H3WorkflowProfileId = "minimax_h3_image_to_video"
    workflow_mode: H3WorkflowMode = "image_to_video"


class H3ProjectUpdateRequest(BaseModel):
    model_config = ConfigDict(strict=True)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    sequence_mode: Literal["independent_shots", "continuous_sequence"] | None = None
    workflow_profile_id: H3WorkflowProfileId | None = None
    workflow_mode: H3WorkflowMode | None = None


class H3ProjectOpenRequest(BaseModel):
    model_config = ConfigDict(strict=True)
    project_root: str


class H3SceneUpdateRequest(BaseModel):
    model_config = ConfigDict(strict=True)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    prompt: str | None = None
    confirmed_outcome: str | None = Field(default=None, max_length=600)
    audio_mode: Literal["natural_ambience", "dialogue", "silent"] | None = None
    no_speech: bool | None = None
    no_music: bool | None = None
    custom_audio_instruction: str | None = Field(default=None, max_length=500)
    reference_image: str | None = None
    reference_fit: Literal["fill_crop", "fit", "stretch"] | None = None
    ltx_prompt_enhance: bool | None = None
    workflow_profile_id: H3WorkflowProfileId | None = None
    workflow_mode: H3WorkflowMode | None = None
    aspect_ratio: H3AspectRatio | None = None
    resolution_megapixels: H3ResolutionMegapixels | None = None
    width: int | None = Field(default=None, ge=1)
    height: int | None = Field(default=None, ge=1)
    fps: int | None = Field(default=None, ge=1)
    duration_seconds: float | None = Field(default=None, gt=0)
    frame_count: int | None = Field(default=None, ge=1)
    seed: int | None = Field(default=None, ge=0, le=0xFFFFFFFFFFFFFFFF)
    selected_render_version_id: str | None = None
    mode: H3SceneMode | None = None
    continuity_strategy: H3ContinuityStrategy | None = None
    continuity_offset_frames: int | None = Field(default=None, ge=0)


class H3ProjectRenderRequest(BaseModel):
    model_config = ConfigDict(strict=True)
    base_url: str = "http://127.0.0.1:8188"


class H3UpscaleRequest(BaseModel):
    model_config = ConfigDict(strict=True)
    base_url: str
    input_directory: str
    output_directory: str
    scale: Literal[2] = 2


class H3UpscaleAvailabilityResponse(BaseModel):
    model_config = ConfigDict(strict=True)
    available: bool
    backend: Literal["nvidia_rtx_vsr"] = "nvidia_rtx_vsr"
    reason: str


class H3OllamaModel(BaseModel):
    model_config = ConfigDict(strict=True)
    name: str
    vision_capable: bool = False


class H3PromptAssistantStatusResponse(BaseModel):
    model_config = ConfigDict(strict=True)
    status: Literal["ready", "not_running", "model_not_installed", "unavailable"]
    endpoint: str
    models: list[H3OllamaModel] = Field(default_factory=list)
    selected_model: str | None = None
    selected_model_available: bool = False
    vision_capable: bool = False
    model_state: Literal["cold", "warming", "warm", "unknown"] = "unknown"
    model_vram_bytes: int | None = Field(default=None, ge=0)
    message: str


class H3PromptAssistantRequest(BaseModel):
    """Local Ollama prompt-improvement request. Never accepts remote URLs."""
    model_config = ConfigDict(strict=True)
    endpoint: str = "http://127.0.0.1:11434"
    model: str = Field(min_length=1, max_length=300)
    raw_prompt: str = Field(min_length=1, max_length=12000)
    scene_number: int = Field(ge=1)
    scene_name: str = Field(min_length=1, max_length=120)
    scene_mode: H3SceneMode
    duration_seconds: float = Field(gt=0)
    aspect_ratio: H3AspectRatio
    width: int = Field(ge=1)
    height: int = Field(ge=1)
    fps: int = Field(ge=1)
    project_name: str = Field(min_length=1, max_length=120)
    sequence_mode: Literal["independent_shots", "continuous_sequence"]
    previous_scene_number: int | None = Field(default=None, ge=1)
    previous_scene_name: str | None = Field(default=None, max_length=120)
    previous_scene_prompt: str | None = Field(default=None, max_length=12000)
    previous_final_prompt: str | None = Field(default=None, max_length=12000)
    continuity_source_version_id: str | None = Field(default=None, max_length=120)
    current_location: str | None = Field(default=None, max_length=600)
    current_state: str | None = Field(default=None, max_length=1200)
    next_action: str | None = Field(default=None, max_length=12000)
    persistent_visual_style: str | None = Field(default=None, max_length=600)
    audio_state: str | None = Field(default=None, max_length=600)
    continuity_frame_path: str | None = Field(default=None, max_length=4096)
    reference_image_path: str | None = Field(default=None, max_length=4096)
    audio_mode: Literal["natural_ambience", "dialogue", "silent"]
    no_speech: bool = False
    no_music: bool = False
    custom_audio_instruction: str = Field(default="", max_length=500)
    request_id: str | None = Field(default=None, min_length=1, max_length=120)


class H3PromptAssistantResponse(BaseModel):
    model_config = ConfigDict(strict=True)
    provider: Literal["ollama"] = "ollama"
    suggestion: str
    model: str
    vision_context: Literal["used", "not_available"]
    message: str
    request_id: str | None = None
    elapsed_seconds: float = Field(ge=0)


class H3NextScenePromptRequest(BaseModel):
    model_config = ConfigDict(strict=True)
    endpoint: str = "http://127.0.0.1:11434"
    model: str = Field(min_length=1, max_length=300)
    current_user_instruction: str = Field(default="", max_length=12000)
    request_id: str | None = Field(default=None, min_length=1, max_length=120)


class H3NextScenePromptResponse(BaseModel):
    model_config = ConfigDict(strict=True)
    provider: Literal["ollama", "deterministic_local"]
    developed_prompt: str
    updated_continuity_summary: str
    next_scene_summary: str
    source_scene_id: str
    source_render_version_id: str
    continuity_artifact_id: str | None = None
    message: str
    request_id: str | None = None
    elapsed_seconds: float = Field(ge=0)


class H3NextSceneSuggestionsResponse(BaseModel):
    model_config = ConfigDict(strict=True)
    options: list[str] = Field(min_length=3, max_length=3)
    source_scene_id: str
    source_render_version_id: str
    provider: Literal["ollama", "deterministic_local"]
    mode: Literal["original_ideas", "user_directed_variations"]
    message: str
    request_id: str | None = None
    elapsed_seconds: float = Field(ge=0)


class H3WorkflowProfileInstallRequest(BaseModel):
    model_config = ConfigDict(strict=True)
    folder: str = Field(min_length=1, max_length=4096)


class H3WorkflowProfileInstallResponse(BaseModel):
    model_config = ConfigDict(strict=True)
    profile_id: str
    version: str
    installed_path: str


class H3Ltx25ModelAssetStatus(BaseModel):
    """Filename/layout state only; no checksum claim is made for gated LTX weights."""

    model_config = ConfigDict(strict=True)
    filename: str
    destination_category: str | None
    required: bool
    state: Literal["found", "missing", "duplicate", "unknown", "wrong_filename", "wrong_destination"]
    file_size_bytes: int | None = None
    message: str


class H3Ltx25ModelImportRequest(BaseModel):
    model_config = ConfigDict(strict=True)
    file_paths: list[str] = Field(default_factory=list, max_length=16)
    shared_model_paths_config: str = Field(min_length=1, max_length=4096)


class H3Ltx25ModelImportResponse(BaseModel):
    model_config = ConfigDict(strict=True)
    model_root: str | None
    assets: list[H3Ltx25ModelAssetStatus]
    imported_count: int
    checksum_verified: bool = False


class H3SequenceStartRequest(BaseModel):
    model_config = ConfigDict(strict=True)
    base_url: str = "http://127.0.0.1:8188"
    kind: H3SequenceKind
    start_scene_id: str | None = None


class H3SceneReorderRequest(BaseModel):
    model_config = ConfigDict(strict=True)
    scene_ids: list[str] = Field(min_length=1, max_length=999)


class H3ContinuityPrepareResponse(BaseModel):
    model_config = ConfigDict(strict=True)
    project: H3Project
    artifact: H3ContinuityArtifact


class GenerationProgressResponse(BaseModel):
    status: Literal["idle", "running", "complete", "cancelled", "error"]
    phase: str
    progress: int
    currentStep: int | None
    totalSteps: int | None
    result: str | list[str] | None = None
    # Identifies which generation this snapshot belongs to (None only for "idle" — nothing has
    # run yet). Lets a polling client confirm it's still looking at its own generation rather
    # than a different, unrelated one that reused the single global progress slot in the
    # meantime.
    id: str | None = None


class DownloadProgressRunningResponse(BaseModel):
    status: Literal["downloading"]
    current_downloading_file: ModelCheckpointID | None
    current_file_progress: float
    total_progress: float
    total_downloaded_bytes: int
    expected_total_bytes: int
    completed_files: set[ModelCheckpointID]
    all_files: set[ModelCheckpointID]
    error: None = None
    speed_bytes_per_sec: float


class DownloadProgressCompleteResponse(BaseModel):
    status: Literal["complete"]


class DownloadProgressErrorResponse(BaseModel):
    status: Literal["error"]
    error: str


DownloadProgressResponse: TypeAlias = (
    DownloadProgressRunningResponse | DownloadProgressCompleteResponse | DownloadProgressErrorResponse
)


class SuggestGapPromptResponse(BaseModel):
    status: Literal["success"] = "success"
    suggested_prompt: str


class GenerateVideoCompleteResponse(BaseModel):
    status: Literal["complete"]
    video_path: str


class GenerateVideoCancelledResponse(BaseModel):
    status: Literal["cancelled"]


GenerateVideoResponse: TypeAlias = GenerateVideoCompleteResponse | GenerateVideoCancelledResponse


class GenerateImageCompleteResponse(BaseModel):
    status: Literal["complete"]
    image_paths: list[str]


class GenerateImageCancelledResponse(BaseModel):
    status: Literal["cancelled"]


GenerateImageResponse: TypeAlias = GenerateImageCompleteResponse | GenerateImageCancelledResponse


class CancelCancellingResponse(BaseModel):
    status: Literal["cancelling"]
    id: str


class CancelNoActiveGenerationResponse(BaseModel):
    status: Literal["no_active_generation"]


CancelResponse: TypeAlias = CancelCancellingResponse | CancelNoActiveGenerationResponse


class RetakeVideoResponse(BaseModel):
    status: Literal["complete"]
    video_path: str


class RetakePayloadResponse(BaseModel):
    status: Literal["complete"]
    result: JsonObject


class RetakeCancelledResponse(BaseModel):
    status: Literal["cancelled"]


RetakeResponse: TypeAlias = RetakeVideoResponse | RetakePayloadResponse | RetakeCancelledResponse


class IcLoraExtractResponse(BaseModel):
    conditioning: str
    original: str
    conditioning_type: ConditioningType
    frame_time: float


class IcLoraGenerateCompleteResponse(BaseModel):
    status: Literal["complete"]
    video_path: str


class IcLoraGenerateCancelledResponse(BaseModel):
    status: Literal["cancelled"]


IcLoraGenerateResponse: TypeAlias = IcLoraGenerateCompleteResponse | IcLoraGenerateCancelledResponse


# ============================================================
# HuggingFace auth
# ============================================================


class HuggingFaceLoginResponse(BaseModel):
    client_id: str
    redirect_uri: str
    scope: str
    state: str
    code_challenge: str
    code_challenge_method: str


class HuggingFaceAuthStatusResponse(BaseModel):
    status: Literal["authenticated", "pending", "not_authenticated"]


class HuggingFaceLogoutResponse(BaseModel):
    status: Literal["logged_out"]


class ModelDownloadStartResponse(BaseModel):
    status: Literal["started"]
    message: str
    sessionId: str


class ActiveDownloadResponse(BaseModel):
    # The currently-running download session (at most one); session_id is null and cp_ids
    # empty when idle. Lets a UI that remounts mid-download (e.g. a reopened settings modal)
    # reattach to it.
    session_id: str | None
    cp_ids: list[ModelCheckpointID]


class LtxDownloadRecommendationResponse(BaseModel):
    status: Literal["download"]
    cps_to_download: list[ModelCheckpointID]


class LtxUpgradeRecommendationResponse(BaseModel):
    status: Literal["upgrade"]
    ltx_model_id: LTXLocalModelId
    upgrade_message: str | None = None
    cps_to_download: list[ModelCheckpointID]
    cps_to_delete: list[ModelCheckpointID]


class LtxOkRecommendationResponse(BaseModel):
    status: Literal["ok"]


LtxRecommendationResponse: TypeAlias = (
    LtxDownloadRecommendationResponse | LtxUpgradeRecommendationResponse | LtxOkRecommendationResponse
)


class ImageGenRecommendationResponse(BaseModel):
    cp_to_download: ModelCheckpointID | None


class LtxIcLoraRecommendationResponse(BaseModel):
    cps_to_download: list[ModelCheckpointID]


class TextEncoderRecommendationResponse(BaseModel):
    cp_to_download: ModelCheckpointID | None
    expected_size_bytes: int
    expected_size_gb: float


class LtxModelVersionItem(BaseModel):
    model_id: LTXLocalModelId
    label: str
    model_cp: ModelCheckpointID
    size_bytes: int
    installed: bool
    active: bool
    is_newest: bool
    cps_to_download: list[ModelCheckpointID]


class LtxModelVersionsResponse(BaseModel):
    versions: list[LtxModelVersionItem]


class SetActiveLtxModelRequest(BaseModel):
    model_id: LTXLocalModelId


CheckpointRole = Literal["base", "upscaler", "text_encoder", "image", "support"]


class CheckpointDescriptor(BaseModel):
    cp_id: ModelCheckpointID
    name: str
    # User-facing explanatory copy lives in the frontend keyed off `role` (so wording/i18n
    # iterates without a backend deploy); the backend only ships the stable role enum.
    role: CheckpointRole
    size_bytes: int
    downloaded: bool


class DescribeCheckpointsResponse(BaseModel):
    checkpoints: list[CheckpointDescriptor]


class StatusResponse(BaseModel):
    status: str


class HTTPErrorResponse(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None


class LtxInsufficientFundsErrorResponse(BaseModel):
    code: Literal["LTX_INSUFFICIENT_FUNDS"]
    message: str


# ============================================================
# Request Models
# ============================================================


LTXVideoGenResolution: TypeAlias = Literal["540p", "720p", "1080p", "1440p", "2160p"]
LTXVideoGenDuration: TypeAlias = Literal[5, 6, 8, 10, 12, 14, 16, 18, 20]
LTXVideoGenFps: TypeAlias = Literal[24, 25, 48, 50]
LTXVideoGenPipeline: TypeAlias = Literal["fast", "pro"]


class LTXVideoGenerationResolutionSpec(BaseModel):
    fps_to_durations: dict[LTXVideoGenFps, list[LTXVideoGenDuration]]


class LTXVideoGenerationSpec(BaseModel):
    display_name: str
    supported_resolutions_durations: dict[LTXVideoGenResolution, LTXVideoGenerationResolutionSpec]
    a2v_supported_resolutions_durations: dict[LTXVideoGenResolution, LTXVideoGenerationResolutionSpec] | None = None


class LTXVideoGenerationModelSpecItem(BaseModel):
    pipeline: LTXVideoGenPipeline
    spec: LTXVideoGenerationSpec


class GenerateVideoModelsSpecsResponse(BaseModel):
    local_models: list[LTXVideoGenerationModelSpecItem]
    api_models: list[LTXVideoGenerationModelSpecItem]


class InstalledModelResponse(BaseModel):
    path: str
    name: str
    kind: str  # "safetensors"
    size_bytes: int
    is_lora: bool
    is_ic_lora: bool


class InstalledModelsResponse(BaseModel):
    models: list[InstalledModelResponse]


class LoraEntry(BaseModel):
    model_config = ConfigDict(strict=True)

    ref: str
    scale: float = Field(default=1.0, ge=0.0, le=4.0)


class GenerateVideoRequest(BaseModel):
    model_config = ConfigDict(strict=True)

    prompt: NonEmptyPrompt
    resolution: LTXVideoGenResolution = "1080p"
    model: LTXVideoGenPipeline = "fast"
    cameraMotion: VideoCameraMotion = "none"
    negativePrompt: str = ""
    duration: LTXVideoGenDuration = 5
    fps: LTXVideoGenFps = 24
    audio: bool = False
    imagePath: str | None = None
    audioPath: str | None = None
    aspectRatio: Literal["16:9", "9:16"] = "16:9"
    seed: int | None = None
    loras: list[LoraEntry] = Field(default_factory=list[LoraEntry])


class GenerateImageRequest(BaseModel):
    model_config = ConfigDict(strict=True)

    prompt: NonEmptyPrompt
    width: int = Field(default=1024, ge=16)
    height: int = Field(default=1024, ge=16)
    numSteps: int = Field(default=4, ge=1)
    numImages: int = Field(default=1, ge=1)
    imagePath: str | None = None
    strength: float = Field(default=0.6, ge=0.0, le=1.0)


def _default_model_types() -> set[ModelCheckpointID]:
    return set()


class ModelDownloadRequest(BaseModel):
    type: Literal["download", "upgrade"] = "download"
    cp_ids: set[ModelCheckpointID] = Field(default_factory=_default_model_types)


ModelAccessStatus: TypeAlias = Literal["authorized", "not_authorized"]


class CheckModelAccessRequest(BaseModel):
    cp_ids: set[ModelCheckpointID] = Field(default_factory=_default_model_types)


class CheckModelAccessResponse(BaseModel):
    access: dict[str, ModelAccessStatus]


class ModelDeleteRequest(BaseModel):
    cp_ids: set[ModelCheckpointID] = Field(default_factory=_default_model_types)


class DescribeCheckpointsRequest(BaseModel):
    cp_ids: list[ModelCheckpointID]


GapPromptMode: TypeAlias = Literal["text-to-video", "image-to-video", "text-to-image"]


class SuggestGapPromptRequest(BaseModel):
    model_config = ConfigDict(strict=True)

    beforePrompt: str = ""
    afterPrompt: str = ""
    beforeFrame: str | None = None
    afterFrame: str | None = None
    gapDuration: float = 5
    mode: GapPromptMode = "text-to-video"
    inputImage: str | None = None

    @model_validator(mode="after")
    def _validate_input_image_mode(self) -> "SuggestGapPromptRequest":
        if self.inputImage is not None and self.mode != "image-to-video":
            raise ValueError("inputImage is only valid for image-to-video mode")
        return self


RetakeMode: TypeAlias = Literal["replace_audio_and_video", "replace_video", "replace_audio"]


class TargetResolution(BaseModel):
    """Desired output resolution for a local generation. The backend corrects it to the
    nearest valid size (snapped down to a multiple of 32, never above the source)."""

    model_config = ConfigDict(strict=True)

    width: int = Field(gt=0)
    height: int = Field(gt=0)


class RetakeRequest(BaseModel):
    model_config = ConfigDict(strict=True)

    video_path: str
    start_time: float
    duration: float
    prompt: str = ""
    mode: RetakeMode = "replace_audio_and_video"
    resolution: TargetResolution | None = None


ExtendMode: TypeAlias = Literal["start", "end"]


class ExtendRequest(BaseModel):
    model_config = ConfigDict(strict=True)

    video_path: str
    # gt=0 + allow_inf_nan=False so NaN/negative fail validation (clean 422) instead of
    # slipping past the handler's min/max guards and blowing up in frame-count math.
    duration: float = Field(gt=0, allow_inf_nan=False)
    prompt: str = ""
    mode: ExtendMode = "end"
    resolution: TargetResolution | None = None


# Extend returns the same shapes as retake (video file, remote payload, or cancelled).
ExtendResponse: TypeAlias = RetakeResponse


ConditioningType: TypeAlias = Literal["canny", "depth"]

# Generation can additionally run a user-supplied IC-LoRA against a pre-rendered
# control video ("custom"), bypassing the built-in canny/depth preprocessing.
IcLoraGenerateConditioning: TypeAlias = Literal["canny", "depth", "custom"]
IcLoraAudioMode: TypeAlias = Literal["source", "generated", "off"]


class IcLoraExtractRequest(BaseModel):
    model_config = ConfigDict(strict=True)

    video_path: str
    conditioning_type: ConditioningType = "canny"
    frame_time: float = 0


class IcLoraImageInput(BaseModel):
    model_config = ConfigDict(strict=True)

    path: str
    frame: int = 0
    strength: float = 1.0


def _default_ic_lora_images() -> list[IcLoraImageInput]:
    return []


class OutpaintPads(BaseModel):
    """Per-edge pixels to add around the source video (extend-only, so all ≥ 0).

    The +100% cap (each ≤ the source's axis size) needs the source dimensions, so it's enforced
    in `_outpaint_canvas`, not here.
    """

    model_config = ConfigDict(strict=True)
    left: int = Field(ge=0)
    right: int = Field(ge=0)
    top: int = Field(ge=0)
    bottom: int = Field(ge=0)


class IcLoraGenerateRequest(BaseModel):
    model_config = ConfigDict(strict=True)
    # Optional: not required in IC-LoRA mode (input comes via input_path).
    video_path: str = ""
    conditioning_type: IcLoraGenerateConditioning
    # May be empty for catalog IC-LoRAs whose entry sets allows_empty_prompt (e.g. outpainting).
    # Non-emptiness is enforced in the handler per path, not at the DTO level.
    prompt: str
    # These five are overlay settings: None means "use the default" — the IC-LoRA's
    # default_settings in IC-LoRA mode, or the built-in default otherwise. The UI sends
    # an explicit value only when the user edits it (advanced controls).
    conditioning_strength: float | None = None
    # Skip Stage 2 (upscale + refine). Default False = current two-stage behavior.
    # Transformation IC-LoRAs (cross-eye, etc.) need this True or Stage 2 repaints
    # from the prompt and erases the effect.
    skip_stage_2: bool | None = None
    # Keep the IC-LoRA active during Stage 2 refinement (only meaningful when Stage 2
    # runs, i.e. skip_stage_2=False). Default False = canonical behavior (Stage 2 drops
    # the LoRA and refines from the prompt). True preserves the transformation through
    # refinement. EXPERIMENTAL — honoured by services.patches.ic_lora_stage2_lora.
    use_lora_in_stage_2: bool | None = None
    # Target output resolution, used only on the use_lora_in_stage_2 two-stage path
    # (mirrors t2v: snapped down to a valid size, never above source). None = source.
    resolution: TargetResolution | None = None
    # Stage-1-only canvas multiplier (only affects skip_stage_2). Stage 1 runs at
    # half the passed canvas, so 2.0 = native target resolution, 1.0 = half (faster).
    # Intermediate values trade quality for speed/VRAM. Canvas is rounded to a
    # multiple of 64. Sentinel 0 = "source dimensions": ignore the multiplier and
    # size the output to the input video's resolution (see ic_lora_handler).
    resolution_factor: float | None = Field(default=None, ge=0.0, le=2.0)
    # Audio: "generated" = model audio from the prompt (current default); "source" =
    # mux the input clip's soundtrack (transformation LoRAs); "off" = no audio.
    audio_mode: IcLoraAudioMode | None = None
    # LoRA adapter merge weight (baked at load time). Bounded to [0, 2] to match the
    # desktop IC-LoRA strength control (same practical ceiling as the plain-LoRA UI slider).
    lora_strength: float | None = Field(default=None, ge=0.0, le=2.0)
    # Override the control-video fps by temporally resampling it. Lower fps = fewer frames =
    # less compute/VRAM (fits longer clips), at the cost of choppier motion. None = source fps.
    # Only decimates (ignored if >= source fps).
    fps_override: float | None = Field(default=None, gt=0.0)
    num_inference_steps: int = 30
    cfg_guidance_scale: float = 1.0
    negative_prompt: str = ""
    images: list[IcLoraImageInput] = Field(default_factory=_default_ic_lora_images)
    # "custom" conditioning: the user's own IC-LoRA + a pre-rendered control video.
    # Ignored for canny/depth; required (both) when conditioning_type == "custom".
    custom_lora_ref: str | None = None
    control_video_path: str | None = None
    # IC-LoRA mode: when set, the backend resolves catalog weights, builds the control
    # video via the IC-LoRA's preprocessing pipeline, and runs the custom inference path.
    ic_lora_id: str | None = None
    # Optional catalog download.variants[].id. When set, that checkpoint must be on disk.
    # When omitted, any installed candidate is used (preferred filename first).
    variant_id: str | None = None
    # Values for the IC-LoRA's declared `controls`, keyed by control id (e.g. {"duration": 5}).
    # Missing keys fall back to each control's default; values are validated against the control's
    # options. The handler maps known ids to behaviour (duration → frame count).
    control_values: dict[str, int | str] = Field(default_factory=dict)
    # Outpainting only: per-edge pixels to add around the source (extend-only). The canvas UI
    # emits these directly; aspect presets are computed front-end into pads. None for other entries.
    outpaint_pads: OutpaintPads | None = None
    # The user's input media for IC-LoRA mode (image or video per ic_lora.input.kind).
    input_path: str | None = None


# --- LoRA / IC-LoRA catalog ---
# Shared base `LoraCatalogItem` (used as-is for plain LoRAs); `IcLoraCatalogItem` extends it
# with the IC-specific preprocessing / controls / default settings.
InputKind: TypeAlias = Literal["image", "video"]
InstructionTitle: TypeAlias = Literal["What it does", "Input", "Prompt", "Tips", "Notes"]
# Machine-readable counterpart to `title`, so consumers (e.g. a prompt enhancer) can select
# instruction blocks by purpose without string-matching display titles. "tips" also covers
# the "Notes" title; "summary" covers "What it does".
InstructionKind: TypeAlias = Literal["summary", "prompting", "tips", "input"]
# Where a trigger word/phrase must appear in the prompt. Not set (and not applicable) when
# `prompt_template` is present, since the template's placeholder position already encodes it.
TriggerPlacement: TypeAlias = Literal["first_token", "anywhere"]

_TEMPLATE_PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")


class InstructionSection(BaseModel):
    model_config = ConfigDict(strict=True)
    kind: InstructionKind
    title: InstructionTitle
    body: str | list[str]


class PromptTemplatePlaceholder(BaseModel):
    model_config = ConfigDict(strict=True)
    # None = free text (a description Gemma fills in). A list = the value must be exactly one
    # of these choices (e.g. crossview's azimuth/elevation/distance vocabulary).
    choices: list[str] | None = None


class PromptTemplateSpec(BaseModel):
    """A fixed prompt structure a LoRA/IC-LoRA requires verbatim (e.g. a two-part
    "Reference shows X. Edited shows Y." restore template, or crossview's enum-constrained
    camera vocabulary). `template` contains `{name}` placeholders; each must have a matching
    entry in `placeholders`. A degenerate template with no placeholders (e.g. "upscale") is a
    fixed, non-generated prompt.
    """
    model_config = ConfigDict(strict=True)
    template: str
    placeholders: dict[str, PromptTemplatePlaceholder] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_placeholders_match_template(self) -> "PromptTemplateSpec":
        referenced = set(_TEMPLATE_PLACEHOLDER_RE.findall(self.template))
        declared = set(self.placeholders)
        if referenced != declared:
            raise ValueError(
                f"prompt_template placeholders {sorted(declared)} must exactly match "
                f"template references {sorted(referenced)}"
            )
        return self


class DownloadVariant(BaseModel):
    """One downloadable weights file under a catalog item (e.g. strong vs light)."""
    model_config = ConfigDict(strict=True)
    id: str
    label: str
    filename: str
    size_bytes: int


class DownloadSpec(BaseModel):
    """HF download location for a catalog item.

    ``variants`` is always non-empty. The first entry is the default checkpoint
    (preferred for generation / omit-``variant_id`` downloads). See the comment on
    ``LoraCatalogHandler`` listing helpers.
    """
    model_config = ConfigDict(strict=True)
    repo_id: str
    variants: list[DownloadVariant]

    @model_validator(mode="after")
    def _check_variants(self) -> "DownloadSpec":
        if not self.variants:
            raise ValueError("download.variants must contain at least one entry (first = default)")
        filenames = [v.filename for v in self.variants]
        if len(filenames) != len(set(filenames)):
            raise ValueError("download.variants filenames must be unique")
        ids = [v.id for v in self.variants]
        if len(ids) != len(set(ids)):
            raise ValueError("download.variants ids must be unique")
        return self

    def default_variant(self) -> DownloadVariant:
        return self.variants[0]

    def resolve_variant(self, variant_id: str | None) -> DownloadVariant | None:
        """Resolve by id; ``None`` → first variant (the default)."""
        if variant_id is None:
            return self.variants[0]
        return next((v for v in self.variants if v.id == variant_id), None)

    def candidate_filenames(self) -> list[str]:
        """Filenames in preference order (default first)."""
        return [v.filename for v in self.variants]


class InputSpec(BaseModel):
    model_config = ConfigDict(strict=True)
    kind: InputKind
    # False (default) = required, matching every existing entry (IC-LoRAs always require their
    # driving input; a plain LoRA with `input` set has, until now, always meant "requires one").
    # True = accepted/preferred but not mandatory (e.g. product-ad-style: works with or without
    # a product image, image preferred).
    optional: bool = False


class LicenseSpec(BaseModel):
    model_config = ConfigDict(strict=True)
    name: str
    url: str | None = None


AuthorAffiliation: TypeAlias = Literal["ltx", "community"]


class AuthorSpec(BaseModel):
    # Credit back to the community that builds these LoRAs. Extensible (more fields later).
    model_config = ConfigDict(strict=True)
    name: str
    url: str | None = None
    # Product/legal bucket for disclaimer gating. Defaults to community so a missing
    # value fails closed to the safer copy; set "ltx" for official LTX catalog items.
    affiliation: AuthorAffiliation = "community"


class MediaSpec(BaseModel):
    model_config = ConfigDict(strict=True)
    thumbnail: str | None = None
    demo_video: str | None = None


def _empty_instructions() -> list[InstructionSection]:
    return []


def _empty_tags() -> list[str]:
    return []


class LoraCatalogItem(BaseModel):
    """Base catalog entry — used as-is for a plain LoRA."""
    model_config = ConfigDict(strict=True)
    id: str
    name: str
    description: str
    download: DownloadSpec
    requires_hf_login: bool
    # Optional: IC-LoRAs always take a driving image/video; many plain (t2v) LoRAs take none.
    input: InputSpec | None = None
    instructions: list[InstructionSection] = Field(default_factory=_empty_instructions)
    license: LicenseSpec | None = None
    author: AuthorSpec | None = None
    media: MediaSpec | None = None
    # ISO-8601 date the model was created at the source (e.g. HuggingFace).
    created_at: str | None = None
    base_model: str | None = None
    tags: list[str] = Field(default_factory=_empty_tags)
    # Trigger phrase to include in the prompt if the LoRA needs one (e.g. "ADD WATER").
    trigger: str | None = None
    # Required together with `trigger` (and only then), unless `prompt_template` is set —
    # the template's placeholder position already encodes where the trigger goes.
    trigger_placement: TriggerPlacement | None = None
    # Set when the LoRA/IC-LoRA requires a fixed prompt structure rather than a free rewrite
    # (e.g. colorization's two-part restore template, or crossview's enum-constrained camera
    # vocabulary). Some LoRAs/IC-LoRAs with a template have no separate `trigger` at all (e.g.
    # ingredients' "Reference sheet: {panels}. Generated video: {action}." has no trigger word).
    prompt_template: PromptTemplateSpec | None = None
    # Extra few-shot example prompts for a prompt enhancer to draw on — never rendered in the
    # LoRA info UI (unlike the single illustrative example inside a "prompting" instruction).
    # Multi-shot grounding helps an LLM rewrite generalize past one example's specific subject.
    enhancement_examples: list[str] = Field(default_factory=list)
    # Suggested LoRA scale when a plain LoRA is selected (IC-LoRAs use default_settings instead).
    recommended_strength: float | None = None
    # When true, generation may run with an empty prompt (e.g. outpainting fills from the scene).
    # Enforced for the catalog IC-LoRA path; plain-LoRA t2v enforcement is not wired yet.
    allows_empty_prompt: bool = False

    @model_validator(mode="after")
    def _check_trigger_placement(self) -> "LoraCatalogItem":
        if self.prompt_template is not None:
            if self.trigger_placement is not None:
                raise ValueError(
                    f"'{self.id}': trigger_placement is redundant when prompt_template is set"
                )
        elif (self.trigger is None) != (self.trigger_placement is None):
            raise ValueError(f"'{self.id}': trigger and trigger_placement must be set together")
        return self


class IcLoraSettings(BaseModel):
    model_config = ConfigDict(strict=True)
    skip_stage_2: bool = False
    # Keep the IC-LoRA active in Stage 2 (only when skip_stage_2=False). EXPERIMENTAL.
    use_lora_in_stage_2: bool = False
    # 2.0 = native, 1.0 = half; sentinel 0 = source dimensions (see ic_lora_handler).
    resolution_factor: float = Field(default=2.0, ge=0.0, le=2.0)
    audio_mode: IcLoraAudioMode = "generated"
    lora_strength: float = Field(default=1.0, ge=0.0, le=2.0)
    conditioning_strength: float = 1.0


IcLoraControlKind: TypeAlias = Literal["int", "select", "position_canvas"]


class IcLoraControl(BaseModel):
    # A user-facing knob the IC-LoRA exposes in the gen UI. `id` is the field it drives
    # (e.g. "duration", "outpaint_pads"); the frontend renders each control by id + kind.
    # `kind` picks the value type: "int" → integer options (e.g. duration seconds);
    # "select" → string options (e.g. a region); "position_canvas" → the outpainting editor
    # for positioning/sizing the source within the output frame, whose value is structured
    # (per-edge pads) and travels in the typed `outpaint_pads` request field, so it declares
    # no options/default. `kind` defaults to "int" so pre-existing int-only entries parse unchanged.
    model_config = ConfigDict(strict=True)
    id: str
    label: str
    kind: IcLoraControlKind = "int"
    # int/select carry their value via `options`; "position_canvas" leaves both None (value is typed elsewhere).
    default: int | str | None = None
    options: list[int] | list[str] | None = None
    # Display-only metadata so the frontend renders controls generically (data-driven):
    # `unit` is a suffix appended to the value (e.g. "s", "%"); `value_labels` maps an option
    # (as a string) to a friendlier label (e.g. "all" → "All sides"). Both optional.
    unit: str | None = None
    value_labels: dict[str, str] | None = None

    @model_validator(mode="after")
    def _check_value_type(self) -> "IcLoraControl":
        if self.kind == "position_canvas":
            if self.default is not None or self.options is not None:
                raise ValueError("position_canvas control takes no default/options (value is structured)")
            return self
        if self.default is None or self.options is None:
            raise ValueError(f"{self.kind} control requires a default and options")
        if self.kind == "int":
            ok = isinstance(self.default, int) and all(isinstance(o, int) for o in self.options)
            if not ok:
                raise ValueError("int control requires an int default and int options")
        else:
            ok = isinstance(self.default, str) and all(isinstance(o, str) for o in self.options)
            if not ok:
                raise ValueError("select control requires a str default and str options")
        return self


class PreprocessingStep(BaseModel):
    model_config = ConfigDict(strict=True)
    utility: str
    params: dict[str, JsonValue] = Field(default_factory=dict)


def _empty_preprocessing() -> list[PreprocessingStep]:
    return []


def _empty_controls() -> list[IcLoraControl]:
    return []


class IcLoraCatalogItem(LoraCatalogItem):
    """IC-LoRA — base plus IC-specific preprocessing / controls / default settings.

    IC-LoRAs always take a driving image/video; `input` is required in practice (the base
    field is optional for plain LoRAs). Enforced by the validator below, so handlers can rely
    on it being present.
    """
    preprocessing: list[PreprocessingStep] = Field(default_factory=_empty_preprocessing)
    controls: list[IcLoraControl] = Field(default_factory=_empty_controls)
    default_settings: IcLoraSettings = Field(default_factory=IcLoraSettings)
    # When true, the UI offers an optional reference image that seeds the first frame
    # (image conditioning at frame 0, strength 1.0) — e.g. a photoreal seed for 3D-render.
    allows_reference_image: bool = False

    @model_validator(mode="after")
    def _require_input(self) -> "IcLoraCatalogItem":
        # An IC-LoRA always drives off an image/video input — reject a malformed catalog entry
        # at parse time rather than letting it trip the handler's assert at generate time.
        if self.input is None:
            raise ValueError(f"IC-LoRA '{self.id}' must declare an input spec")
        return self


def _empty_ic_loras() -> list[IcLoraCatalogItem]:
    return []


def _empty_loras() -> list[LoraCatalogItem]:
    return []


CATALOG_SCHEMA_VERSION = 1


class LoraCatalogFile(BaseModel):
    model_config = ConfigDict(strict=True)
    schema_version: int
    ic_loras: list[IcLoraCatalogItem] = Field(default_factory=_empty_ic_loras)
    loras: list[LoraCatalogItem] = Field(default_factory=_empty_loras)


def parse_lora_catalog(raw: str) -> LoraCatalogFile:
    catalog = LoraCatalogFile.model_validate_json(raw)
    if catalog.schema_version != CATALOG_SCHEMA_VERSION:
        # A future v2 doc would otherwise parse against v1 fields with no clear error.
        raise ValueError(
            f"Unsupported catalog schema_version {catalog.schema_version} (expected {CATALOG_SCHEMA_VERSION})"
        )
    return catalog


class EnhancePromptRequest(BaseModel):
    """Regular-LoRA, IC-LoRA, and built-in conditioning-type selection are mutually exclusive UI
    surfaces — a request never carries more than one of loraCatalogIds/icLoraId/conditioningType.
    """
    model_config = ConfigDict(strict=True)
    prompt: NonEmptyPrompt
    loraCatalogIds: list[str] = Field(default_factory=list)
    icLoraId: str | None = None
    # Set only for the built-in (non-catalog) "bring your own IC-LoRA" canny/depth conditioning
    # modes — those have no catalog entry to draw a system prompt from, but still need the same
    # "describe the reference scene faithfully, don't invent a different one" discipline a
    # catalog IC-LoRA's template-fill path gets, instead of Gemma's default free-rewrite prompt.
    conditioningType: Literal["canny", "depth"] | None = None
    imagePath: str | None = None
    # "local" runs the on-device Gemma text encoder (default, matches every existing caller);
    # "api" calls Gemini's hosted API instead — no local checkpoint required, gated on
    # AppSettings.gemini_api_key being set.
    provider: Literal["local", "api"] = "local"
    # "video" (default, matches every existing caller) routes through the video-catalog LoRA/
    # IC-LoRA/conditioning-type selection below. "image" is Z-Image-Turbo generation/editing —
    # no catalog LoRA concept, so none of loraCatalogIds/icLoraId/conditioningType apply;
    # imagePath's presence distinguishes editing (img2img) from generation, same convention as
    # video's t2v/i2v split.
    mediaType: Literal["video", "image"] = "video"

    @model_validator(mode="after")
    def _check_selection_is_mutually_exclusive(self) -> "EnhancePromptRequest":
        selected = [bool(self.loraCatalogIds), self.icLoraId is not None, self.conditioningType is not None]
        if sum(selected) > 1:
            raise ValueError("loraCatalogIds, icLoraId, and conditioningType are mutually exclusive")
        if self.mediaType == "image" and sum(selected) > 0:
            raise ValueError("loraCatalogIds, icLoraId, and conditioningType only apply to mediaType='video'")
        return self


class EnhancePromptResponse(BaseModel):
    model_config = ConfigDict(strict=True)
    enhancedPrompt: str


class IcLoraListItem(BaseModel):
    model_config = ConfigDict(strict=True)
    ic_lora: IcLoraCatalogItem
    downloaded: bool
    # Subset of download.variants[].id present on disk (empty when none installed).
    downloaded_variant_ids: list[str] = Field(default_factory=list)


class IcLoraListResponse(BaseModel):
    model_config = ConfigDict(strict=True)
    ic_loras: list[IcLoraListItem]


class IcLoraDownloadRequest(BaseModel):
    model_config = ConfigDict(strict=True)
    ic_lora_id: str
    # Optional catalog download.variants[].id; omit to download the default filename.
    variant_id: str | None = None
    # Dev escape hatch: attach the in-app HuggingFace token even when HF gating is off
    # (gated IC-LoRA repos need auth; gating is normally env-driven in packaged builds).
    use_hf_auth: bool = False


# Shared start-response for both catalog download kinds (IC-LoRA + plain LoRA).
class CatalogDownloadStartResponse(BaseModel):
    model_config = ConfigDict(strict=True)
    status: str
    sessionId: str


CatalogDownloadStatus: TypeAlias = Literal["downloading", "complete", "error"]


class IcLoraDownloadProgressResponse(BaseModel):
    model_config = ConfigDict(strict=True)
    status: CatalogDownloadStatus
    ic_lora_id: str | None = None
    downloaded_bytes: int = 0
    expected_bytes: int = 0
    progress: float = 0.0
    speed_bytes_per_sec: float = 0.0
    error: str | None = None


# --- Plain LoRA catalog (list + download). Mirrors the IC-LoRA flow with a separate
#     download session so it never interferes with an in-flight IC-LoRA download. ---
class LoraListItem(BaseModel):
    model_config = ConfigDict(strict=True)
    lora: LoraCatalogItem
    downloaded: bool
    # Subset of download.variants[].id present on disk (empty when none installed).
    downloaded_variant_ids: list[str] = Field(default_factory=list)


class LoraListResponse(BaseModel):
    model_config = ConfigDict(strict=True)
    loras: list[LoraListItem]


class LoraDownloadRequest(BaseModel):
    model_config = ConfigDict(strict=True)
    lora_id: str
    # Optional catalog download.variants[].id; omit to download the default filename.
    variant_id: str | None = None
    use_hf_auth: bool = False


class LoraDownloadProgressResponse(BaseModel):
    model_config = ConfigDict(strict=True)
    status: CatalogDownloadStatus
    lora_id: str | None = None
    downloaded_bytes: int = 0
    expected_bytes: int = 0
    progress: float = 0.0
    speed_bytes_per_sec: float = 0.0
    error: str | None = None
