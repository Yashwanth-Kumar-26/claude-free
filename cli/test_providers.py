"""Provider test utility — checks health of all configured backends."""

import asyncio

import httpx

# claudefree default settings
BASE_URL = "http://127.0.0.1:16324"
TOKEN = "God"

# These models are aliases for specific backends in claudefree
# We'll try to hit each major backend bypass
TEST_TARGETS = [
    ("nvidia_nim",  "nvidia_nim/meta/llama-3.1-405b-instruct"),
    ("opencode_go", "opencode_go/anthropic/claude-3-5-sonnet"),
    ("opencode_zen","opencode_zen/anthropic/claude-3-opus"),
    ("open_router", "open_router/anthropic/claude-3.5-sonnet"),
]

async def check_backend(name, model_ref):
    print(f"Testing {name:15} ... ", end="", flush=True)

    data = {
        "model": model_ref,
        "messages": [{"role": "user", "content": "Respond with the word 'OK' only."}],
        "max_tokens": 10,
        "stream": False # Use non-streaming for simpler health check
    }

    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json"
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(f"{BASE_URL}/v1/messages", json=data, headers=headers)

            if resp.status_code == 200:
                body_text = resp.text
                # Look for common error indicators in the response body
                low_body = body_text.lower()
                error_markers = ["error", "fail", "invalid", "unauthorized", "illegal header"]

                if any(m in low_body for m in error_markers):
                    print("❌ FAILED (Error in response body)")
                    # Try to extract the message
                    if "text_delta" in body_text:
                        import re
                        match = re.search(r'"text_delta", "text": "(.*?)"', body_text)
                        if match:
                            print(f"   Message: {match.group(1)}")
                    return False

                print("✅ WORKING")
                return True
    except Exception as e:
        print(f"❌ OFFLINE ({type(e).__name__})")

    return False

async def main():
    print("═══ claudefree Provider Health Check ═══")
    print(f"Gateway: {BASE_URL}")
    print("-" * 40)

    tasks = [check_backend(name, m) for name, m in TEST_TARGETS]
    results = await asyncio.gather(*tasks)

    print("-" * 40)
    success = sum(1 for r in results if r)
    print(f"Summary: {success}/{len(TEST_TARGETS)} backends active.")
    if success == 0:
        print("\nTIP: Make sure the gateway is running: 'uv run uvicorn server:app --port 16324 --host 127.0.0.1'")

if __name__ == "__main__":
    import contextlib
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main())
