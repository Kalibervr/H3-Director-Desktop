# H3 render timing

`render_elapsed_seconds` is local, backend-measured provider time from provider
invocation through discovery, verification, and immutable adoption of a usable
MP4. It excludes UI idle time and is never derived from a frontend timer.

Successful render versions persist `render_started_at`, `render_completed_at`,
and `render_elapsed_seconds` in `project.json`. Existing immutable versions
without a provider measurement remain `null` and display **Not recorded**.

RTX VSR is a derived output. Its `processing_elapsed_seconds` is stored on the
derived variant and is not substituted for, or added to, source generation time.
All timing stays in local project metadata; H3 Director sends no timing
telemetry or cloud analytics.
