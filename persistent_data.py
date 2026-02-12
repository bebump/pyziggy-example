from pathlib import Path
from typing import Callable, Dict, Tuple
from datetime import datetime
import csv


def get_datetime_now_string() -> str:
    # The minimum number of lines required in Python to get an ISO 8601
    # timestamp with the timezone offset of the machine running this code

    from datetime import datetime, timezone

    dt = datetime.now(datetime.now(timezone.utc).astimezone().tzinfo)
    utc_offset = dt.strftime("%z")
    split_utc_offset = utc_offset[:3] + ":" + utc_offset[3:]
    return dt.strftime("%Y-%m-%dT%H:%M:%S") + split_utc_offset


class PersistentData:
    """
    Stores data in .csv files. Each line contains a timestamp, a key and a value.
    """

    def __init__(self, path: Path, source: Callable[[], Dict[str, float]]):
        self.path = path
        self.source = source

    def save(self):
        now = get_datetime_now_string()
        dt = datetime.fromisoformat(now)

        with self.path.open("a", newline="") as f:
            writer = csv.writer(f)

            for key, value in self.source().items():
                writer.writerow([now, key, value])

    def load(
        self, start_dt: datetime | None = None, end_dt: datetime | None = None
    ) -> Dict[str, list[Tuple[str, float]]]:
        data: Dict[str, list[Tuple[str, float]]] = {}

        if not self.path.exists():
            return data

        with self.path.open("r") as f:
            reader = csv.reader(f)

            for row in reader:
                timestamp_str, key, value_str = row
                dt = datetime.fromisoformat(timestamp_str)

                if start_dt and dt < start_dt:
                    continue

                if end_dt and dt > end_dt:
                    continue

                value = float(value_str)

                if key not in data:
                    data[key] = []

                data[key].append((timestamp_str, value))

        for key in data:
            data[key].sort(key=lambda x: datetime.fromisoformat(x[0]))

        return data
