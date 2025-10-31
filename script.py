import json
from pathlib import Path


def state_to_cookie_header(state_path="connect_state.json"):
    with Path.open(state_path) as f:
        state = json.load(f)
    cookies = state.get("cookies", [])
    cookie_str = "; ".join(f"{c['name']}={c['value']}" for c in cookies)
    return cookie_str


if __name__ == "__main__":
    print(state_to_cookie_header())
