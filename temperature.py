from enum import Enum
from pathlib import Path

from pyziggy.message_loop import MessageLoopTimer

from astral_mired import EasyAstral
from devices import devices
from persistent_data import PersistentData
from pyziggy_autogenerate.available_devices import SONOFF_TRVZB


class Trv:
    def __init__(self, valve: SONOFF_TRVZB):
        self.valve = valve

    def turn_off_heating(self):
        self.valve.occupied_heating_setpoint.set_normalized(0.0)

    def turn_on_heating(self):
        self.valve.occupied_heating_setpoint.set_normalized(1.0)

    def set_fallback_temperature(self, temperature: float):
        self.valve.occupied_heating_setpoint.set(temperature)


class Rooms(Enum):
    OFFICE = "office"
    LIVING_ROOM = "living_room"
    KITCHEN = "kitchen"
    BEDROOM = "bedroom"
    BATHROOM = "bathroom"


trvs = {
    Rooms.OFFICE: Trv(devices.office_valve),
    Rooms.BEDROOM: Trv(devices.bedroom_valve),
    Rooms.KITCHEN: Trv(devices.kitchen_valve),
    Rooms.LIVING_ROOM: Trv(devices.living_room_valve),
}

temps = {
    Rooms.OFFICE: devices.office_temp,
    Rooms.LIVING_ROOM: devices.living_room_temp,
    Rooms.KITCHEN: devices.living_room_temp,
    Rooms.BEDROOM: devices.bedroom_temp,
    Rooms.BATHROOM: devices.bathroom_temp,
}


def get_target_temperatures():
    now_decimal = EasyAstral.get_now_decimal()

    daytime = {
        Rooms.OFFICE: 23.2,
        Rooms.LIVING_ROOM: 24,
        Rooms.KITCHEN: 24,
        Rooms.BEDROOM: 22.4,
    }

    if 7 <= now_decimal <= 24:
        return daytime

    nighttime = {
        Rooms.OFFICE: daytime[Rooms.OFFICE] - 1.2,
        Rooms.LIVING_ROOM: daytime[Rooms.LIVING_ROOM] - 1.2,
        Rooms.KITCHEN: daytime[Rooms.KITCHEN] - 1.2,
        Rooms.BEDROOM: daytime[Rooms.BEDROOM],
    }

    return nighttime


class TemperatureController:
    HYSTERESIS = 0.3

    def __init__(self):
        self._timer = MessageLoopTimer(self._timer_callback)
        self._timer.start(60)

    def _timer_callback(self, timer: MessageLoopTimer):
        for room, temp in get_target_temperatures().items():
            if room in temps:
                if room not in trvs:
                    continue

                current_temp = temps[room].temperature.get()
                if current_temp == 0.0:
                    trvs[room].set_fallback_temperature(temp)
                elif current_temp <= temp - TemperatureController.HYSTERESIS:
                    trvs[room].turn_on_heating()
                elif current_temp >= temp + TemperatureController.HYSTERESIS:
                    trvs[room].turn_off_heating()


temperature_controller = TemperatureController()


def get_room_infos():
    room_infos = {}

    for room in Rooms:
        target_temp = (
            get_target_temperatures()[room] if room in get_target_temperatures() else 0
        )

        room_info = {
            "controllable": room in trvs,
            "current_temperature": (
                temps[room].temperature.get() if room in temps else 0
            ),
            "target_temperature": target_temp,
            "max_allowed_deviation_from_target": TemperatureController.HYSTERESIS,
            "heating_on": (
                trvs[room].valve.occupied_heating_setpoint.get_normalized() > 0.5
                if room in trvs
                else False
            ),
        }

        room_infos[room.value] = room_info

    return room_infos


# ==============================================================================
def temperature_data_source():
    return {
        room.value: temps[room].temperature.get() for room in Rooms if room in temps
    }


temperature_data = PersistentData(
    Path.home() / "pyziggy_temperature_data.csv", temperature_data_source
)

save_temperature_data_timer = MessageLoopTimer(lambda timer: temperature_data.save())
save_temperature_data_timer.start(300)
