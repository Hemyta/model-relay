import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


RELAY_URL = "https://modelrelay.<your-domain-name>.com/models/gemini-3.1-flash-lite:generateContent"
RELAY_TOKEN = "paste-your-relay-token-here"
GEMINI_API_KEY = "paste-your-gemini-api-key-here"


def main() -> None:
    if RELAY_TOKEN.startswith("paste-") or GEMINI_API_KEY.startswith("paste-"):
        raise ValueError("Fill in RELAY_TOKEN and GEMINI_API_KEY at the top of this file")

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": "Write a short poem about a cat who loves to chase butterflies."}],
            }
        ]
    }
    request = Request(
        RELAY_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 model-relay-test/1.0",
            "Accept": "application/json",
            "X-Relay-Token": RELAY_TOKEN,
            "X-Relay-Upstream": "gemini",
            "X-Goog-Api-Key": GEMINI_API_KEY,
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=60) as response:
            result = json.load(response)
    except HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Request failed with HTTP {error.code}: {body}") from error
    except URLError as error:
        raise RuntimeError(f"Could not reach the relay: {error.reason}") from error

    try:
        text = result["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError):
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(text)


if __name__ == "__main__":
    main()