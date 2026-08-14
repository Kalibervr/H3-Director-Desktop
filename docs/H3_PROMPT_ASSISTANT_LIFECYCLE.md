# H3 Prompt Assistant lifecycle

The Prompt Assistant is local-only and uses the configured loopback Ollama endpoint.

## User-visible states

- **Starting Ollama**: the local server lifecycle is starting or probing.
- **Ollama Ready / model cold**: the server responds and the selected model is installed, but it is not resident according to Ollama `/api/ps`.
- **Loading model**: H3 submitted a bounded local warmup request.
- **Ready**: the selected model is resident and can answer prompt requests.
- **Running request**: one correlated Improve, Develop, or Suggest request is active for the selected scene.
- **Failed / cancelled**: the response is kept out of the scene prompt and the UI explains why.

H3 asks Ollama to retain the model for 30 minutes with its supported `keep_alive` API field. During video rendering it sends `keep_alive: 0` to release the model while leaving the Ollama server alive, including when that server is externally owned. After the render becomes inactive, H3 asynchronously warms the selected model again when Keep Prompt Assistant Ready is enabled.

Prompt Assistant output is always reviewable. It never replaces the authored prompt until the user chooses **Apply**. A cancelled or stale response is ignored by its request ID and may not update another scene.
