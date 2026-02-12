from pathlib import Path
from typing import Callable, Dict, Tuple
from datetime import datetime, timedelta
import csv


def get_datetime_now_string() -> str:
    # The minimum number of lines required in Python to get an ISO 8601
    # timestamp with the timezone offset of the machine running this code

    from datetime import datetime, timezone

    dt = datetime.now(datetime.now(timezone.utc).astimezone().tzinfo)
    utc_offset = dt.strftime("%z")
    split_utc_offset = utc_offset[:3] + ":" + utc_offset[3:]
    return dt.strftime("%Y-%m-%dT%H:%M:%S") + split_utc_offset


def resample(data: list[Tuple[str, float]], num_max_samples=1000):
    """
    Resamples the data to at most num_max_samples samples by averaging values in time intervals.
    """

    if len(data) <= num_max_samples:
        return data

    start_dt = datetime.fromisoformat(data[0][0])
    end_dt = datetime.fromisoformat(data[-1][0])
    total_seconds = (end_dt - start_dt).total_seconds()
    interval_seconds = total_seconds / num_max_samples

    resampled_data: list[Tuple[str, float]] = []
    current_interval_start_dt = start_dt
    current_interval_end_dt = start_dt + timedelta(seconds=interval_seconds)
    current_interval_values: list[float] = []

    for timestamp_str, value in data:
        dt = datetime.fromisoformat(timestamp_str)

        while dt >= current_interval_end_dt:
            if current_interval_values:
                average_value = sum(current_interval_values) / len(current_interval_values)
                resampled_data.append((current_interval_start_dt.isoformat(), average_value))

            current_interval_start_dt = current_interval_end_dt
            current_interval_end_dt += timedelta(seconds=interval_seconds)
            current_interval_values = []

        current_interval_values.append(value)

    if current_interval_values:
        average_value = sum(current_interval_values) / len(current_interval_values)
        resampled_data.append((current_interval_start_dt.isoformat(), average_value))

    return resampled_data


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
            data[key] = resample(data[key])

        return data
