# model-relay

Current version: `v1.0.0`

Model Relay is a small, stateless HTTP relay for accessing AI model APIs through a trusted server. It transparently forwards request methods, paths, query parameters, headers, bodies, status codes, and streaming responses without parsing model payloads.

The service does not use a database and does not store API keys, requests, responses, or user data. Access is protected by a separate relay token. Provider API keys and model parameters are always supplied by the caller.

The current configuration supports Gemini, but no model name or Gemini payload format is built into the relay. Additional providers can be added to `app/upstreams.py`.

## Run

Create the environment file:

```bash
cp .env.example .env
```

Generate a strong `RELAY_TOKEN` with Python:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Copy the generated value into `RELAY_TOKEN` in `.env`, then start the service:

```bash
docker compose up -d --build
```

The service listens on port `7500` by default. The port can be changed with `PORT` in `.env`.

`RELAY_TOKEN` is a shared secret controlled by the service operator. Every caller must send it with each request. The relay does not provide an endpoint for discovering the token: the operator must give it only to authorized callers through a secure channel, such as a secrets manager. Callers should store it as an environment variable or application secret, never in source code. To rotate it, update `.env`, restart the service, and securely distribute the new value.

Interactive Swagger API documentation is available at `https://modelrelay.<your-domain-name>.com/docs`.

## Use

Every model request must explicitly provide:

- `X-Relay-Token`: the relay access token configured in `.env`.
- `X-Relay-Upstream`: the upstream alias configured in `app/upstreams.py`.
- The original provider authentication headers, path, parameters, and body.

Example request to Gemini:

```python
import json
import os
from urllib.request import Request, urlopen


url = "https://modelrelay.<your-domain-name>.com/models/gemini-3.1-flash-lite:generateContent"
payload = {
  "contents": [
    {"parts": [{"text": "Hello"}]},
  ],
}
request = Request(
  url,
  data=json.dumps(payload).encode("utf-8"),
  headers={
    "X-Relay-Token": os.environ["RELAY_TOKEN"],
    "X-Relay-Upstream": "gemini",
    "X-Goog-Api-Key": os.environ["GEMINI_API_KEY"],
    "Content-Type": "application/json",
  },
  method="POST",
)

with urlopen(request) as response:
  print(response.read().decode("utf-8"))
```

The relay forwards the upstream response without wrapping it. `GET /healthz` returns `204` for health checks.
