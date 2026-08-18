
from __future__ import annotations

from enum import Enum


class TimeFormat(Enum):
    ISO_8601 = "8601"
    EPOCH = "epoch"
    EPOCH_MS = "epoch_ms"
    YYYY_MM_DD = "YYYY-MM-DD"


def save_env_global(app_key: str, app_secret: str, callback_url: str) -> None:
    """Save global credentials to ~/.schwabdev/env.json (keys: app_key, app_secret, callback_url)."""
    import json
    import os

    env_path = os.path.expanduser("~/.schwabdev/env.json")
    os.makedirs(os.path.dirname(env_path), exist_ok=True)
    with open(env_path, "w") as f:
        json.dump({"app_key": app_key, "app_secret": app_secret, "callback_url": callback_url}, f, indent=4, )