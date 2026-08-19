import os

import uvicorn


uvicorn.run(
    "app.main:app",
    host="0.0.0.0",
    port=int(os.environ.get("PORT", "7500")),
    access_log=False,
    server_header=False,
    proxy_headers=False,
)