import json
import os
from pathlib import Path
from typing import Dict, Any

from flask import Flask, request

from automation import (
    turn_off_everything,
    turn_things_back_on,
    toggle_office,
    toggle_couch,
)
from pyziggy.message_loop import message_loop

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


@app.route("/pyziggy")
def http_pyziggy_help():
    commands = [
        {"action": "turn_off_all_lights"},
        {"action": "turn_things_back_on"},
        {"action": "toggle_office"},
        {"action": "toggle_couch"},
    ]

    html = make_html("Send commands to <code>/pyziggy/post</code>.", commands)
    return html, 200


@app.route("/pyziggy/post", methods=["POST"])
def http_pyziggy_post():
    payload = request.get_json()

    def message_callback():
        http_message_handler(payload)

    message_loop.post_message(message_callback)

    return "", 200
