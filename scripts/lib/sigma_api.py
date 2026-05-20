"""Shared Sigma REST helpers.

Reads SIGMA_BASE_URL + SIGMA_API_TOKEN from the environment. Tokens come from
get-token.sh (~1h TTL). Functions raise on non-2xx so callers can let stack
traces propagate; wrap in try/except only where you want to recover.
"""

from __future__ import annotations
import json
import os
import sys
import urllib.error
import urllib.request


def base_url() -> str:
    v = os.environ.get("SIGMA_BASE_URL")
    if not v:
        sys.exit("SIGMA_BASE_URL not set — run scripts/setup.py and source the env file")
    return v.rstrip("/")


def token() -> str:
    v = os.environ.get("SIGMA_API_TOKEN")
    if not v:
        sys.exit('SIGMA_API_TOKEN not set — run: eval "$(scripts/get-token.sh)"')
    return v


def _request(method: str, path: str, body=None, accept_json: bool = True) -> tuple[int, bytes]:
    url = f"{base_url()}{path}"
    headers = {
        "Authorization": f"Bearer {token()}",
        "Accept": "application/json" if accept_json else "*/*",
    }
    data = None
    if body is not None:
        if isinstance(body, (dict, list)):
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        elif isinstance(body, (bytes, bytearray)):
            data = bytes(body)
        elif isinstance(body, str):
            data = body.encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def get(path: str, accept_json: bool = True) -> tuple[int, bytes]:
    return _request("GET", path, accept_json=accept_json)


def post(path: str, body) -> tuple[int, bytes]:
    return _request("POST", path, body=body)


def put(path: str, body) -> tuple[int, bytes]:
    return _request("PUT", path, body=body)


def get_json(path: str):
    status, data = get(path)
    if status >= 300:
        sys.exit(f"GET {path} -> {status}: {data[:500].decode('utf-8', errors='replace')}")
    return json.loads(data)


def parse_yaml_or_json(payload: bytes):
    """Sigma /spec endpoints return YAML by default. Try JSON first, then YAML."""
    text = payload.decode("utf-8", errors="replace")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        try:
            import yaml  # PyYAML
        except ImportError:
            sys.exit(
                "Response is YAML but PyYAML is not installed. "
                "Install with: pip install --user pyyaml"
            )
        return yaml.safe_load(text)


def find_home_folder_id() -> str:
    """Return the current user's home folder ID — required for spec POST."""
    me = get_json("/v2/whoami")
    user_id = me.get("userId")
    member = get_json(f"/v2/members/{user_id}")
    folder_id = member.get("homeFolderId")
    if not folder_id:
        sys.exit("Could not determine homeFolderId — check Sigma permissions")
    return folder_id
