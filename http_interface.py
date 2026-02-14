import datetime
import json
import os
from pathlib import Path
from typing import Dict, Any

from flask import Flask, request, jsonify
from flask.json.provider import DefaultJSONProvider
from pyziggy.message_loop import message_loop

from automation import (
    turn_off_everything,
    turn_things_back_on,
    toggle_office,
    toggle_couch,
)
from persistent_data import resample, datetime_to_string

app = Flask(__name__)


# Interprets the provided path constituents relative to the location of this
# script, and returns an absolute Path to the resulting location.
#
# E.g. rel_to_py(".") returns an absolute path to the directory containing this
# script.
def rel_to_py(*paths) -> Path:
    return Path(
        os.path.realpath(
            os.path.join(os.path.realpath(os.path.dirname(__file__)), *paths)
        )
    )


# ==============================================================================
def http_message_handler(payload):
    if "action" in payload:
        action = payload["action"]

        if action == "turn_off_all_lights":
            turn_off_everything()

        if action == "turn_things_back_on":
            turn_things_back_on()

        if action == "toggle_office":
            toggle_office()

        if action == "toggle_couch":
            toggle_couch()


# ==============================================================================
def make_html(description: str, commands: list[Dict[Any, Any]]):
    raw_template: str | None = None

    with open(rel_to_py("http_interface_html_template.html"), "r") as file:
        raw_template = file.read()

    if raw_template is None:
        return ""

    result = ""

    for line in raw_template.splitlines(keepends=True):
        if "$welcome_text" in line:
            result += line.replace("$welcome_text", description)
            continue

        if "$button_text" in line:
            for command in commands:
                result += line.replace("$button_text", json.dumps(command))
            continue

        result += line

    return result


@app.route("/pyziggy/rooms")
def http_pyziggy_help():
    with open(rel_to_py("rooms_gui.html"), "r") as file:
        return file.read(), 200


@app.route("/pyziggy/api/post_command", methods=["POST"])
def http_pyziggy_post():
    payload = request.get_json()

    def message_callback():
        http_message_handler(payload)

    message_loop.post_message(message_callback)

    return "", 200


@app.route("/pyziggy/api/room_infos")
def http_room_infos():
    """
    Returns an info object for each room. An example output is shown below.

    {
        "office": {
            "controllable": true,
            "target_temperature": 22.0,
            "max_allowed_deviation_from_target": 0.3,
            "heating_on": false
        },
        "living_room": {
            "controllable": true,
            "target_temperature": 22.8,
            "max_allowed_deviation_from_target": 0.3,
            "heating_on": false
        },
        "kitchen": {
            "controllable": true,
            "target_temperature": 22.8,
            "max_allowed_deviation_from_target": 0.3,
            "heating_on": false
        },
        "bedroom": {
            "controllable": true,
            "target_temperature": 22.4,
            "max_allowed_deviation_from_target": 0.3,
            "heating_on": false
        },
        "bathroom": {
            "controllable": false,
            "target_temperature": 0,
            "max_allowed_deviation_from_target": 0.3,
            "heating_on": false
        }
    }
    """

    from temperature import get_room_infos

    return jsonify(get_room_infos())


class CustomJSONProvider(DefaultJSONProvider):
    def default(self, obj):
        if isinstance(obj, datetime.datetime):
            return datetime_to_string(obj)
        return super().default(obj)


app.json = CustomJSONProvider(app)


@app.route("/pyziggy/api/temperature_data")
def http_temperature_data():
    """
    Returns historical temperature data for each room. An example output is shown below.

    The data for each room is a list of timestamp-temperature pairs, where the timestamp
    is in ISO 8601 format.

    Supports 'start' and 'end' query parameters as ISO 8601 strings.

    {
      "bathroom": [
        [
          "2026-02-12T17:24:43+01:00",
          27.7
        ],
        [
          "2026-02-12T17:26:29+01:00",
          27.7
        ],
        [
          "2026-02-12T18:59:41+01:00",
          27.4
        ],
        [
          "2026-02-12T19:01:26+01:00",
          27.4
        ],
        [
          "2026-02-12T20:34:38+01:00",
          27.5
        ],
        [
          "2026-02-12T20:36:24+01:00",
          27.5
        ],
        [
          "2026-02-12T22:09:36+01:00",
          27.6
        ],
        [
          "2026-02-12T22:11:21+01:00",
          27.6
        ]
      ],
      "bedroom": [
        [
          "2026-02-12T17:24:43+01:00",
          22.8
        ],
        [
          "2026-02-12T17:26:29+01:00",
          22.8
        ],
        [
          "2026-02-12T18:59:42+01:00",
          22.6
        ],
        [
          "2026-02-12T19:01:27+01:00",
          22.6
        ],
        [
          "2026-02-12T20:34:41+01:00",
          22.7
        ],
        [
          "2026-02-12T20:36:26+01:00",
          22.7
        ],
        [
          "2026-02-12T22:09:40+01:00",
          22.9
        ],
        [
          "2026-02-12T22:11:25+01:00",
          22.9
        ]
      ],
      "kitchen": [
        [
          "2026-02-12T17:24:43+01:00",
          24.2
        ],
        [
          "2026-02-12T17:26:29+01:00",
          24.2
        ],
        [
          "2026-02-12T18:59:42+01:00",
          23.8
        ],
        [
          "2026-02-12T19:01:27+01:00",
          23.8
        ],
        [
          "2026-02-12T20:34:41+01:00",
          23.8
        ],
        [
          "2026-02-12T20:36:26+01:00",
          23.8
        ],
        [
          "2026-02-12T22:09:40+01:00",
          24.3
        ],
        [
          "2026-02-12T22:11:25+01:00",
          24.3
        ]
      ],
      "living_room": [
        [
          "2026-02-12T17:24:43+01:00",
          24.2
        ],
        [
          "2026-02-12T17:26:29+01:00",
          24.2
        ],
        [
          "2026-02-12T18:59:42+01:00",
          23.8
        ],
        [
          "2026-02-12T19:01:27+01:00",
          23.8
        ],
        [
          "2026-02-12T20:34:41+01:00",
          23.8
        ],
        [
          "2026-02-12T20:36:26+01:00",
          23.8
        ],
        [
          "2026-02-12T22:09:40+01:00",
          24.3
        ],
        [
          "2026-02-12T22:11:25+01:00",
          24.3
        ]
      ],
      "office": [
        [
          "2026-02-12T17:24:43+01:00",
          23.3
        ],
        [
          "2026-02-12T17:26:29+01:00",
          23.3
        ],
        [
          "2026-02-12T18:59:42+01:00",
          23.1
        ],
        [
          "2026-02-12T19:01:27+01:00",
          23.1
        ],
        [
          "2026-02-12T20:34:41+01:00",
          23.4
        ],
        [
          "2026-02-12T20:36:26+01:00",
          23.4
        ],
        [
          "2026-02-12T22:09:40+01:00",
          23.3
        ],
        [
          "2026-02-12T22:11:25+01:00",
          23.3
        ]
      ]
    }
    """
    from datetime import datetime

    start_str = request.args.get("start")
    end_str = request.args.get("end")

    start_dt = datetime.fromisoformat(start_str) if start_str else None
    end_dt = datetime.fromisoformat(end_str) if end_str else None

    from temperature import temperature_data

    data = temperature_data.retrieve(start_dt, end_dt)

    resampled_data = {}
    for room, entries in data.items():
        resampled_data[room] = resample(entries, 1000)

    return jsonify(resampled_data)
