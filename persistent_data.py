import bisect
import csv
import threading
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Dict, Tuple, override

from pyziggy.message_loop import AsyncUpdater


def datetime_to_string(dt: datetime) -> str:
    utc_offset = dt.strftime("%z")
    split_utc_offset = utc_offset[:3] + ":" + utc_offset[3:]
    return dt.strftime("%Y-%m-%dT%H:%M:%S") + split_utc_offset


def get_datetime_now() -> Tuple[datetime, str]:
    # The minimum number of lines required in Python to get an ISO 8601
    # timestamp with the timezone offset of the machine running this code
    from datetime import datetime, timezone

    dt = datetime.now(datetime.now(timezone.utc).astimezone().tzinfo)
    return dt, datetime_to_string(dt)


def ensure_local_aware(dt: datetime) -> datetime:
    """
    Checks if a datetime is offset-aware. If it is naive, it sets the
    timezone to the system's local timezone.
    """
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        local_tz = datetime.now(timezone.utc).astimezone().tzinfo
        return dt.replace(tzinfo=local_tz)

    return dt


class ResampleStrategy(Enum):
    MINMAX = ("minmax",)
    AVERAGE = ("average",)
    AUTO = "auto"


def resample(
    ordered_data: list[Tuple[datetime, float]],
    max_num_samples: int | None = None,
    strategy: ResampleStrategy = ResampleStrategy.AUTO,
) -> list[Tuple[datetime, float]]:
    if (
        not ordered_data
        or max_num_samples is None
        or len(ordered_data) <= max_num_samples
    ):
        return ordered_data

    # The MINMAX strategy returns 2 values for each window
    max_num_samples_divisor = 2 if strategy == ResampleStrategy.MINMAX else 1

    delta_window = (ordered_data[-1][0] - ordered_data[0][0]) / (
        max_num_samples / max_num_samples_divisor
    )

    if delta_window.total_seconds() <= 1:
        return ordered_data

    if strategy == ResampleStrategy.AUTO:
        strategy = (
            ResampleStrategy.AVERAGE
            if delta_window.total_seconds() < 3600
            else ResampleStrategy.MINMAX
        )

    resampled_data: list[Tuple[datetime, float]] = []

    current_interval_start = ordered_data[0][0]
    current_interval_end = current_interval_start + delta_window
    current_interval_values: list[float] = []

    def commit_interval():
        interval_middle = (
            current_interval_start + (current_interval_end - current_interval_start) / 2
        )
        interval_first_third = (
            current_interval_start + (current_interval_end - current_interval_start) / 3
        )
        interval_second_third = (
            current_interval_start
            + 2 * (current_interval_end - current_interval_start) / 3
        )

        if current_interval_values:
            if strategy == ResampleStrategy.MINMAX:
                min_value = min(current_interval_values)
                max_value = max(current_interval_values)
                resampled_data.append((interval_first_third, min_value))
                resampled_data.append((interval_second_third, max_value))
            else:
                average_value = sum(current_interval_values) / len(
                    current_interval_values
                )
                resampled_data.append((interval_middle, average_value))

    for dt, value in ordered_data:
        if dt > current_interval_end:
            commit_interval()

            current_interval_start = current_interval_end
            current_interval_end = current_interval_start + delta_window
            current_interval_values = [value]
        else:
            current_interval_values.append(value)

    commit_interval()

    return resampled_data


class PersistentData(AsyncUpdater):
    """
    Stores data in .csv files. Each line contains a timestamp, a key and a value.
    """

    def __init__(self, path: Path, ratelimit_s: float | None = None):
        self._path = path
        self._data_to_write: list[Tuple[str, float]] = []
        self._data: Dict[str, list[Tuple[datetime, float]]] = {}
        self._lock = threading.RLock()
        self._ratelimit_s = ratelimit_s

        self._load()

    def write(self, key: str, value: float):
        with self._lock:
            self._data_to_write.append((key, value))
            self._trigger_async_update()

    def retrieve(
        self, start_dt: datetime | None = None, end_dt: datetime | None = None
    ) -> Dict[str, list[Tuple[datetime, float]]]:
        """
        If the specified start_dt or end_dt is naive, it is assumed to be in
        the local timezone of the machine running this code.
        """
        if start_dt is not None:
            start_dt = ensure_local_aware(start_dt)

        if end_dt is not None:
            end_dt = ensure_local_aware(end_dt)

        with self._lock:
            result: Dict[str, list[Tuple[datetime, float]]] = {}

            for key, values in self._data.items():
                if not values:
                    continue

                start_index = (
                    bisect.bisect_left(values, start_dt, key=lambda x: x[0])
                    if start_dt
                    else 0
                )
                end_index = (
                    bisect.bisect_right(values, end_dt, key=lambda x: x[0])
                    if end_dt
                    else len(values)
                )

                result[key] = values[start_index:end_index]

            return result

    # Using an async updater to batch multiple writes from the same call stack
    # together
    @override
    def _handle_async_update(self):
        with self._lock:
            if self._data_to_write:
                self._save()
                self._data_to_write.clear()

    def _save(self):
        with self._lock:
            dt, dt_string = get_datetime_now()

            with self._path.open("a", newline="") as f:
                writer = csv.writer(f)

                for key, value in self._data_to_write:
                    if key not in self._data:
                        self._data[key] = []

                    if self._data[key]:
                        last_dt = self._data[key][-1][0]
                        last_value = self._data[key][-1][1]

                        if (
                            self._ratelimit_s is not None
                            and dt - last_dt < timedelta(seconds=self._ratelimit_s)
                            and value == last_value
                        ):
                            continue

                        if dt <= last_dt:
                            dt = last_dt + timedelta(seconds=1)
                            dt_string = datetime_to_string(dt)

                    writer.writerow([dt_string, key, value])

                    self._data[key].append((dt, value))

    def _resave(self):
        with self._lock:
            with self._path.open("w", newline="") as f:
                writer = csv.writer(f)

                for key, values in self._data.items():
                    for dt, value in values:
                        dt_string = datetime_to_string(dt)
                        writer.writerow([dt_string, key, value])

    def _prune(self):
        """Remove subsequent entries with the same value, unless they are further than one hour apart"""
        with self._lock:
            for key, values in self._data.items():
                pruned_values: list[Tuple[datetime, float]] = []

                for dt, value in values:
                    if pruned_values:
                        last_dt = pruned_values[-1][0]
                        last_value = pruned_values[-1][1]

                        if value == last_value and dt - last_dt < timedelta(hours=1):
                            continue

                    pruned_values.append((dt, value))

                self._data[key] = pruned_values

            self._resave()

    def _load(self):
        with self._lock:
            with self._path.open("r") as f:
                reader = csv.reader(f)

                for row in reader:
                    timestamp_str, key, value_str = row
                    dt = datetime.fromisoformat(timestamp_str)
                    value = float(value_str)

                    if key not in self._data:
                        self._data[key] = []

                    self._data[key].append((dt, value))

                for key in self._data:
                    self._data[key].sort(key=lambda x: x[0])
