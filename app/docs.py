from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse

from app import __version__


OPENAPI_SCHEMA = {
    "openapi": "3.1.0",
    "info": {
        "title": "Model Relay API",
        "version": __version__,
        "description": "A stateless, transparent relay for AI model HTTP APIs.",
    },
    "paths": {
        "/healthz": {
            "get": {
                "summary": "Health check",
                "responses": {"204": {"description": "Service is healthy"}},
            }
        },
        "/version": {
            "get": {
                "summary": "Service version",
                "responses": {
                    "200": {
                        "description": "Current service version",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {"version": {"type": "string"}},
                                    "required": ["version"],
                                }
                            }
                        },
                    }
                },
            }
        },
        "/models/{model_action}": {
            "post": {
                "summary": "Forward a model request",
                "description": (
                    "Forwards the request to the explicitly selected upstream. "
                    "The model name and action are passed through unchanged."
                ),
                "security": [
                    {"relayToken": [], "geminiApiKey": []},
                ],
                "parameters": [
                    {
                        "name": "model_action",
                        "in": "path",
                        "required": True,
                        "example": "gemini-3.1-flash-lite:generateContent",
                        "schema": {"type": "string"},
                    },
                    {
                        "name": "X-Relay-Upstream",
                        "in": "header",
                        "required": True,
                        "schema": {"type": "string", "enum": ["gemini"]},
                    },
                ],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {"type": "object", "additionalProperties": True},
                        }
                    },
                },
                "responses": {
                    "default": {
                        "description": "The unwrapped upstream response",
                    }
                },
            }
        },
    },
    "components": {
        "securitySchemes": {
            "relayToken": {
                "type": "apiKey",
                "in": "header",
                "name": "X-Relay-Token",
                "description": "Relay access token issued by the service operator.",
            },
            "geminiApiKey": {
                "type": "apiKey",
                "in": "header",
                "name": "X-Goog-Api-Key",
                "description": "Gemini API key supplied by the caller.",
            },
        }
    },
}


SWAGGER_UI = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Model Relay API</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css">
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
  <script>
    SwaggerUIBundle({
      url: "/openapi.json",
      dom_id: "#swagger-ui",
      deepLinking: true,
      persistAuthorization: false
    });
  </script>
</body>
</html>
"""


async def openapi(_: Request) -> JSONResponse:
    return JSONResponse(OPENAPI_SCHEMA)


async def swagger_ui(_: Request) -> HTMLResponse:
    return HTMLResponse(SWAGGER_UI)