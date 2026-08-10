# H3 Editor transition export

## Verified transition contract

The existing editor persists a transition on each clip as `transitionIn` and
`transitionOut`, containing a type and duration. The current Program Monitor
implements one paired transition contract: a **Dissolve Out** on the outgoing
clip and a matching **Dissolve In** on the immediately following clip on the
same cut point.

The monitor does not move clip boundaries. During the final dissolve duration
of the outgoing clip, it blends the outgoing media with frame zero of the
incoming clip. The incoming clip begins normally at its persisted cut point.

## Local FFmpeg implementation

Native export uses the verified bundled local FFmpeg executable. For each valid
paired dissolve, the video-only filter graph:

1. prepares both clips at the requested export frame rate;
2. selects and loops the incoming clip's first frame for the dissolve duration;
3. applies `xfade=transition=fade` from the outgoing render chain to that
   first-frame stream at `priorDuration - dissolveDuration`;
4. concatenates the unchanged incoming clip after the dissolve result.

This retains the editor's existing timeline duration and closely matches the
current Program Monitor timing. The dissolve itself is a real FFmpeg video
blend; source H3 render files are inputs only and are never modified.

## Supported and rejected configurations

Verified export support in this milestone is limited to the existing paired
`dissolve` contract. It requires matching in/out types, matching positive
durations, adjacent clips at one cut point, a duration no longer than either
clip, and a single visual track. Invalid pairings return a clear export error.

The editor also preserves `fade-to-black`, `fade-to-white`, and wipe metadata.
Their current monitor behavior is not a paired video-transition contract, so
local export rejects these types explicitly rather than silently rendering a
different effect. Their saved metadata remains unchanged.

## Audio behavior

The existing PCM audio mixer is preserved. Audio clips and embedded video audio
are mixed at their persisted timeline offsets, including the dissolve interval.
No audio crossfade envelope has been verified or added. This means overlapping
audio is mixed and clipped only at the existing final Int16 clamp; it remains
synchronized to the unchanged visual timeline duration. A future audio
crossfade must be separately designed, implemented, and verified.

## Verification record

The real five-scene local verification project contains one 0.500 s paired
dissolve. Its first export is
`exports/h3-editor-five-scene-dissolve.mp4`. Bundled FFprobe reported H.264
video, AAC audio, 640x640, 24 FPS, 620 video frames, and 25.835 seconds.
The unchanged timeline duration is intentional and follows the verified monitor
contract above. The same saved editor project is reopened and exported again as
part of the milestone check; selected H3 source-render SHA-256 values are
compared with their stored provenance before completion. No cloud renderer or
remote media service is used.
