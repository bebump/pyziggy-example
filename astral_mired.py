import datetime
from typing import Tuple, List

from astral import Observer
from astral.sun import sun


def get_decimal_time(dt: datetime.datetime) -> float:
    """Convert a datetime object to decimal time."""
    return dt.hour + dt.minute / 60 + dt.second / 3600


class EasyAstral:
    def __init__(self, location: Tuple[float, float, float]):
        self._location = location
        self._sun = sun(
            Observer(*self._location),
            tzinfo=self._get_tzinfo(),
        )
        self._day = datetime.datetime.now().day

    def _get_tzinfo(self) -> datetime.tzinfo:
        info = datetime.datetime.now().astimezone().tzinfo
        assert info is not None
        return info

    def _get_sun_time(self, event: str) -> float:
        new_day = datetime.datetime.now().day

        if new_day != self._day:
            self._day = new_day
            self._sun = sun(
                Observer(*self._location),
                tzinfo=self._get_tzinfo(),
            )

        return get_decimal_time(self._sun[event])

    @staticmethod
    def get_now_decimal() -> float:
        now = datetime.datetime.now()
        return get_decimal_time(now)

    def get_dawn(self) -> float:
        return self._get_sun_time("dawn")

    def get_sunrise(self) -> float:
        return self._get_sun_time("sunrise")

    def get_noon(self) -> float:
        return self._get_sun_time("noon")

    def get_sunset(self) -> float:
        return self._get_sun_time("sunset")

    def get_dusk(self) -> float:
        return self._get_sun_time("dusk")


class TimeOfDayEvent:
    def __init__(self, name: str, offset: float):
        self._name = name
        self._offset = offset

    def __add__(self, offset: float):
        if isinstance(offset, (int, float)):
            return TimeOfDayEvent(self._name, self._offset + offset)
        return NotImplemented

    def __sub__(self, offset: float):
        return self.__add__(-offset)


class TimeOfDay:
    DAWN = TimeOfDayEvent("dawn", 0)
    SUNRISE = TimeOfDayEvent("sunrise", 0)
    NOON = TimeOfDayEvent("noon", 0)
    SUNSET = TimeOfDayEvent("sunset", 0)
    DUSK = TimeOfDayEvent("dusk", 0)

    def __init__(self):
        assert False, "This class is not meant to be instantiated."


class MiredCalculator:
    def __init__(
        self,
        lat_long_height: Tuple[float, float, float],
        values: List[Tuple[float, float] | Tuple[TimeOfDayEvent, float]],
    ):
        self._values = values
        self._astral = EasyAstral(lat_long_height)

    def _get_time_and_value(
        self, item: Tuple[float, float] | Tuple[TimeOfDayEvent, float]
    ) -> Tuple[float, float]:
        time, value = item

        if isinstance(time, TimeOfDayEvent):
            time = self._astral._get_sun_time(time._name) + time._offset

        assert isinstance(time, (float, int))

        return time, value

    def get_current_mired(self, for_time_hr_decimal: float | None = None):
        """
        :param for_time_hr_decimal: For testing purposes. If None, uses current time.
                                    The format should be in decimal hours i.e.
                                    12.5 for 12:30.
        """

        now = (
            for_time_hr_decimal
            if for_time_hr_decimal is not None
            else EasyAstral.get_now_decimal()
        )

        d = [self._get_time_and_value(item) for item in self._values]

        for i in range(len(d) - 1):
            assert (
                d[i][0] < d[i + 1][0]
            ), f"Times passed to MiredCalculator must be in ascending order."

        new_d: list[Tuple[float, float]] = []

        for time, value in d:
            new_d.append((time - 24, value))

        for time, value in d:
            new_d.append((time, value))

        for time, value in d:
            new_d.append((time + 24, value))

        d = new_d

        prev = None
        next = None

        for i, (time, value) in enumerate(d):
            if time > now:
                next = (time, value)
                break

            prev = (time, value)

        if prev is None and next is not None:
            return next[1]

        if next is None and prev is not None:
            return prev[1]

        assert prev is not None
        assert next is not None

        a, v1 = prev
        b, v2 = next

        return v1 + (v2 - v1) * (now - a) / (b - a)
