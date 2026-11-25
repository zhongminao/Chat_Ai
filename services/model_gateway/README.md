# Optional cloud model gateway

This loopback-only gateway forwards requests to fixed cloud APIs. It does not run,
start, or proxy local models. It can run alongside the old API gateway on `18100` until clients have switched.

From the repository root, make `GPT_API_KEY` and/or `DEEPSEEK_API_KEY` available in
your shell environment, then run in the foreground:

```sh
python -m pip install -r services/model_gateway/requirements.txt
python services/model_gateway/gateway.py --config services/model_gateway/config.example.yaml
```

The example listens at `127.0.0.1:18101`. Point the corresponding client API base
URLs to `http://127.0.0.1:18101/gpt/v1` and `http://127.0.0.1:18101/deepseek/v1`.
The gateway supplies upstream credentials from the environment; it does not forward
client credentials or authenticate local callers. Do not expose it beyond loopback.
A provider with no key, or with `enabled: false`, returns `503`.

- `GET /health` reports gateway liveness only.
- `POST /{provider}/v1/chat/completions` forwards the request body as-is, streams the
  upstream response, and cancels upstream work on downstream disconnect.
- `GET /{provider}/v1/models` makes one upstream `GET /models` per request (no cache,
  retries, or chat probes). Model entries include `reasoning_efforts` when known and
  `default_reasoning_effort` when known and present in that list. Valid upstream
  standardized levels take precedence. For DeepSeek native `effort.supported_levels`,
  the gateway prepends `none` if absent and uses it as the default to keep thinking off by default.
  GPT's example `reasoning_fallback` attaches levels only to matching discovered IDs;
  it never creates a model entry.

Tests use fake credentials and mock or ephemeral loopback upstreams:

```sh
python -m unittest discover -s services/model_gateway -v
```

## Replace the old cloud API gateway on this host

Run in a quiet window on the host as the service owner, not as root. Keep the
existing KVM cloud-model SSH tunnel open. This migration briefly takes the cloud
endpoint offline, then starts `chat-ai-model-gateway.service` on `127.0.0.1:18100`
with the same credentials file. No change to `chat_ai` URLs or to the tunnel is
needed. The local-model gateway and its configuration are not changed.

```sh
bash "$HOME/mydisk/tools/chat_ai/services/model_gateway/migrate_api_gateway.sh"
```

The script installs dependencies in an independent venv, checks `/models` for
both providers from the host and the VM, and restores the old service if the
cutover checks fail. It removes only the old cloud service files and `config.yaml`
after verification, leaving a backup under `~/.local/share/chat-ai-model-gateway/`.
The example at `18101` is still available for standalone testing; the script
copies it to a separate deployment configuration and changes the port to `18100`.
