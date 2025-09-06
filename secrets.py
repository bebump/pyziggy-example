import json
import os
from pathlib import Path
from typing import Any


def get_secret_or_else(key: str, default: Any) -> Any:
    def rel_to_py(*paths) -> Path:
        return Path(
            os.path.realpath(
                os.path.join(os.path.realpath(os.path.dirname(__file__)), *paths)
            )
        )

    secrets_path = rel_to_py("secrets", "secrets.json")

    if not secrets_path.exists():
        return default

    with open(secrets_path, "r") as f:
        data = json.load(f)

        if key not in data:
            return default

        return data[key]
