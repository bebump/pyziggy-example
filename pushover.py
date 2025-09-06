import http.client, urllib

from secrets import get_secret_or_else


def send_push_notification_to_home_group(msg: str) -> None:
    """Send a push notification to the home automation group via Pushover."""

    APP_TOKEN = get_secret_or_else("pushover_app_token", "")
    HOME_AUTOMATION_GROUP_KEY = get_secret_or_else(
        "pushover_home_automation_group_key", ""
    )

    if not APP_TOKEN or not HOME_AUTOMATION_GROUP_KEY:
        return

    conn = http.client.HTTPSConnection("api.pushover.net:443")
    conn.request(
        "POST",
        "/1/messages.json",
        urllib.parse.urlencode(
            {
                "token": APP_TOKEN,
                "user": HOME_AUTOMATION_GROUP_KEY,
                "message": msg,
            }
        ),
        {"Content-type": "application/x-www-form-urlencoded"},
    )
    conn.getresponse()

