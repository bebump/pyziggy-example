import datetime
import os
from enum import Enum
from typing import Callable, Any

from pyziggy.device_bases import LightWithColorTemp, LightWithColor, LightWithDimming
from pyziggy.message_loop import MessageLoopTimer
from pyziggy.parameters import Broadcaster, NumericParameter
from pyziggy.parameters import (
    SettableBinaryParameter,
    SettableToggleParameter,
    SettableAndQueryableBinaryParameter,
    SettableAndQueryableToggleParameter,
)
from pyziggy.util import LightWithDimmingScalable as L2S
from pyziggy.util import ScaleMapper

from astral_mired import MiredCalculator, TimeOfDay, EasyAstral
from device_helpers import (
    IkeaN2CommandRepeater,
    PhilipsTapDialRotaryHelper,
    PlugScalable,
)
from pushover import send_push_notification_to_home_group
from pyziggy_autogenerate.available_devices import (
    AvailableDevices,
    Philips_RDM002,
    SONOFF_TRVZB,
)
from secrets import get_secret_or_else


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


requested_temps = {
    Rooms.OFFICE: 23.5,
    Rooms.LIVING_ROOM: 23.5,
    Rooms.KITCHEN: 23.5,
    Rooms.BEDROOM: 22.5,
}

devices = AvailableDevices()

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


class TemperatureController:
    HYSTERESIS = 0.5

    def __init__(self):
        self._timer = MessageLoopTimer(self._timer_callback)
        self._timer.start(60)

    def _timer_callback(self, timer: MessageLoopTimer):
        for room, temp in requested_temps.items():
            if room in temps:
                if room not in trvs:
                    continue

                current_temp = temps[room].temperature.get()
                if current_temp == 0.0:
                    trvs[room].set_fallback_temperature(temp)
                elif current_temp < temp - TemperatureController.HYSTERESIS:
                    trvs[room].turn_on_heating()
                elif current_temp > temp + TemperatureController.HYSTERESIS:
                    trvs[room].turn_off_heating()


temperature_controller = TemperatureController()


xmas_lights: list[LightWithColorTemp] = [devices.xmas1, devices.xmas2, devices.xmas3]

kitchen = ScaleMapper(
    [
        (L2S(devices.hue_lightstrip), 0.0, 0.54),
        (L2S(devices.dining_light_1), 0.56, 0.93),
        (L2S(devices.dining_light_2), 0.56, 0.93),
        (L2S(devices.kitchen_light), 0.95, 1.0),
    ],
    [0.55, 0.94],
    lambda: os.system("afplay /System/Library/Sounds/Tink.aiff &"),
)

living_room_with_couch = ScaleMapper(
    [
        (PlugScalable(devices.ikea_smart_plug), 0.0, 0.05),
        (PlugScalable(devices.plug), 0.07, 0.1),
        # (L2S(devices.standing_lamp), 0.07, 0.7),
        (L2S(devices.couch), 0.12, 0.7),
        (L2S(devices.tallbyn), 0.7, 1.0),
    ],
    [0.06, 0.11],
    lambda: os.system("afplay /System/Library/Sounds/Tink.aiff &"),
)

living_room_no_couch = ScaleMapper(
    [
        (PlugScalable(devices.ikea_smart_plug), 0.0, 0.05),
        (PlugScalable(devices.plug), 0.07, 0.1),
        (L2S(devices.tallbyn), 0.07, 1.0),
        # (L2S(devices.standing_lamp), 0.5, 1.0),
    ],
    [0.06],
    lambda: os.system("afplay /System/Library/Sounds/Tink.aiff &"),
)

living_room = living_room_with_couch


def set_mired(mired):
    for device in devices.get_devices():
        if isinstance(device, LightWithColorTemp):
            device.color_temp.set(mired)


def ikea_remote_action_handler():
    toggle_office()


ikea_remote_action_broadcaster = IkeaN2CommandRepeater(devices.ikea_remote)
ikea_remote_action_broadcaster.repeating_action.add_listener(ikea_remote_action_handler)


def rodret_remote_action_handler():
    action = devices.rodret.action.get_enum_value()
    types = devices.rodret.action.enum_type

    if action == types.on:
        turn_things_back_on()
    elif action == types.off:
        turn_off_everything()


devices.rodret.action.add_listener(rodret_remote_action_handler)


def tradfri_remote_action_handler():
    action = devices.tradfri_remote.action.get_enum_value()
    types = devices.tradfri_remote.action.enum_type

    bedroom_devices: list[LightWithDimming] = [devices.lampion, devices.fado]

    if action == types.toggle:
        state_to = 0 if bedroom_devices[0].state.get() else 1
        for device in bedroom_devices:
            device.state.set(state_to)
            device.brightness.set_normalized(1)
    elif action == types.toggle_hold:
        turn_off_everything()
    elif action == types.brightness_down_click:
        for device in bedroom_devices:
            device.brightness.add_normalized(-0.2)
    elif action == types.brightness_up_click:
        for device in bedroom_devices:
            device.brightness.add_normalized(0.2)


devices.tradfri_remote.action.add_listener(tradfri_remote_action_handler)


def kitchen_dimmer(step: int):
    kitchen.add(step / 8 * 0.022)


def living_room_dimmer(step: int):
    living_room.add(step / 8 * 0.022)


def hue_changer(step: int):
    current_hue: float | None = None

    for device in devices.get_devices():
        if isinstance(device, LightWithColor):
            if current_hue is None:
                current_hue = device.color_hs.hue.get()

            assert current_hue is not None
            device.color_hs.hue.set((current_hue + step) % 360)


def saturation_changer(step: int):
    current_saturation: float | None = None

    for device in devices.get_devices():
        if isinstance(device, LightWithColor):
            if current_saturation is None:
                current_saturation = device.color_hs.saturation.get()

            assert current_saturation is not None
            device.color_hs.saturation.set(current_saturation + step)


device_params_turned_off: list | None = None


def turn_off_everything():
    global device_params_turned_off

    new_device_params_turned_off = []

    for device in devices.get_devices():
        for name, param in vars(device).items():
            if name == "state":
                if (
                    isinstance(param, SettableBinaryParameter)
                    or isinstance(param, SettableAndQueryableBinaryParameter)
                    or isinstance(param, SettableToggleParameter)
                    or isinstance(param, SettableAndQueryableToggleParameter)
                ):
                    if param.get() > 0:
                        new_device_params_turned_off.append(param)

                    param.set(0)

    if new_device_params_turned_off:
        device_params_turned_off = new_device_params_turned_off


def turn_things_back_on():
    global device_params_turned_off

    if device_params_turned_off is None:
        return

    for param in device_params_turned_off:
        param.set(1)

    device_params_turned_off = None


default_button_mapping = {
    devices.philips_switch: living_room_dimmer,
    devices.switch_poang: living_room_dimmer,
    devices.switch_kitchen: kitchen_dimmer,
}


def switch_living_room_scene():
    global living_room

    if living_room is living_room_with_couch:
        living_room = living_room_no_couch
        devices.couch.state.set(0)
    else:
        living_room = living_room_with_couch
        devices.couch.state.set(1)


class PhilipsButtonHandler:
    def __init__(self, switch: Philips_RDM002):
        self.switch = switch
        self.button_1_released = True
        self.button_2_released = True

        self.philips_dial_handler = default_button_mapping[self.switch]

        self.switch.action.add_listener(self.button_handler)

        self._timer = MessageLoopTimer(self._timer_callback)

        self.rotary_helper = PhilipsTapDialRotaryHelper(self.switch)
        self.rotary_helper.on_rotate.add_listener(
            lambda step: self.philips_dial_handler(step)
        )

    def button_handler(self):
        t = self.switch.action.enum_type
        action = self.switch.action.get_enum_value()

        if action == t.button_1_press:
            self.philips_dial_handler = living_room_dimmer
            self.start()
        if action == t.button_2_press:
            self.philips_dial_handler = kitchen_dimmer
            self.start()
        if action == t.button_3_press or action == t.button_4_press:
            switch_living_room_scene()
        if action == t.button_1_hold and self.button_1_released:
            self.button_1_released = False
            turn_off_everything()
        if action == t.button_2_hold and self.button_2_released:
            self.button_2_released = False
            turn_things_back_on()
        if action == t.button_1_hold_release:
            self.button_1_released = True
        if action == t.button_2_hold_release:
            self.button_2_released = True

    def start(self):
        self._timer.start(300)

    def _timer_callback(self, timer: MessageLoopTimer):
        self.philips_dial_handler = default_button_mapping[self.switch]


philips_switches = (
    devices.philips_switch,
    devices.switch_kitchen,
    devices.switch_poang,
)
button_handlers = [PhilipsButtonHandler(s) for s in philips_switches]

devices.fado.brightness.add_listener(
    lambda: devices.fado.brightness.set_normalized(
        min(0.55, devices.fado.brightness.get_normalized())
    )
)

office: list[LightWithDimming] = [devices.printer, devices.tokabo, devices.reading_lamp]


def toggle_office():
    lights_are_off = any([light.state.get() == 0 for light in office])

    for light in office:
        if lights_are_off:
            light.state.set(1)
            light.brightness.set_normalized(1.0)
        else:
            light.state.set(0)


def toggle_couch():
    devices.couch.state.set(0 if devices.couch.state.get() > 0 else 1)


class AutoColorTemp:
    def __init__(self):
        self._calculator = MiredCalculator(
            get_secret_or_else("location", (47.402339, 19.251788, 0.0)),
            [
                (2.0, 417),
                (TimeOfDay.SUNRISE - 0.5, 370),
                (TimeOfDay.SUNRISE + 0.5, 179),  # 5600 K daylight
                (TimeOfDay.SUNSET - 1, 179),
                (TimeOfDay.SUNSET, 370),  # 2700 K in the evening
                (23, 370),
                (24, 417),  # 2400 K late night
            ],
        )
        self._timer = MessageLoopTimer(self._timer_callback)
        self._last_mired = self._calculator.get_current_mired()
        self.on_change = Broadcaster()

    def get_mired(self):
        return self._last_mired

    def start(self):
        self._timer.start(10)

    def stop(self):
        self._timer.stop()

    def _timer_callback(self, timer: MessageLoopTimer):
        new_mired = self._calculator.get_current_mired()

        if new_mired != self._last_mired:
            self.on_change._call_listeners()
            self._last_mired = new_mired


auto_color_temp = AutoColorTemp()

lights_with_color_temp: list[LightWithColorTemp] = [
    l
    for l in devices.get_devices()
    if isinstance(l, LightWithColorTemp)
    if l not in xmas_lights
]


def change_mired_for_light(light: LightWithColorTemp):
    if light.state.get() > 0:
        light.color_temp.set(auto_color_temp.get_mired())


for light in lights_with_color_temp:
    light.state.add_listener(lambda light=light: change_mired_for_light(light))  # type: ignore


def change_mired():
    for light in lights_with_color_temp:
        light.color_temp.set(auto_color_temp.get_mired())


auto_color_temp.on_change.add_listener(change_mired)
devices.on_connect.add_listener(lambda: auto_color_temp.start())


class OnceADay:
    def __init__(self, time_hr_decimal: float, callback: Callable[[], Any]):
        self._time_hr_decimal = time_hr_decimal
        self._callback = callback

        # Ensure that we only fire if the specified time is in the future
        self._day_of_last_execution = (
            OnceADay.get_day() - 1
            if EasyAstral.get_now_decimal() < self._time_hr_decimal
            else OnceADay.get_day()
        )
        self._timer = MessageLoopTimer(self._timer_callback)

    def start(self):
        self._timer.start(5)

    @staticmethod
    def get_day():
        return datetime.datetime.now().day

    def _timer_callback(self, timer: MessageLoopTimer):
        current_day = OnceADay.get_day()

        if (
            current_day != self._day_of_last_execution
            and EasyAstral.get_now_decimal() > self._time_hr_decimal
        ):
            self._day_of_last_execution = current_day
            self._callback()


morning_lights: list[LightWithDimming] = [
    devices.couch,
    devices.tallbyn,
    devices.hue_lightstrip,
    # devices.standing_lamp,
    devices.reading_lamp,
    devices.tokabo,
    devices.printer,
    devices.dining_light_1,
    devices.dining_light_2,
]


def turn_on_morning_lights():
    for light in morning_lights:
        light.state.set(1)
        light.brightness.set_normalized(1)

    devices.plug.state.set(1)
    devices.ikea_smart_plug.state.set(1)

    for light in [devices.dining_light_1, devices.dining_light_2]:
        light.brightness.set_normalized(0.5)


turn_on_lights_in_the_morning = OnceADay(8.5, turn_on_morning_lights)
devices.on_connect.add_listener(lambda: turn_on_lights_in_the_morning.start())

sunset_lights: list[LightWithDimming] = [devices.fado, devices.lampion, *xmas_lights]


def turn_on_sunset_lights():
    for light in sunset_lights:
        light.state.set(1)
        light.brightness.set_normalized(1)


sunset = EasyAstral(
    get_secret_or_else("location", (47.402339, 19.251788, 0.0))
).get_sunset()
turn_on_lights_at_sunset = OnceADay(sunset, turn_on_sunset_lights)
devices.on_connect.add_listener(lambda: turn_on_lights_at_sunset.start())

for device in xmas_lights:
    device.brightness.add_listener(
        lambda d=device: d.brightness.set_normalized(0.55)  # type: ignore
    )
    device.color_temp.add_listener(
        lambda d=device: d.color_temp.set_normalized(1.0)  # type: ignore
    )


class WaterSensorAlert:
    def __init__(self):
        self.timer = MessageLoopTimer(self.timer_callback)
        self.callback_counter = 0
        self.timer.start(2)

    def timer_callback(self, timer: MessageLoopTimer):
        if self.callback_counter % 1 == 0:
            os.system("afplay /System/Library/Sounds/Submarine.aiff &")

        if self.callback_counter % 10 == 0:
            send_push_notification_to_home_group("Water sensor alert!")

        self.callback_counter += 1

    def deactivate(self):
        self.timer.stop()


water_sensor_alert: WaterSensorAlert | None = None


def activate_water_sensor_alert():
    global water_sensor_alert

    value = devices.dishwasher_leak_sensor.water_leak.get()

    if value == 1:
        if water_sensor_alert is not None:
            return

        water_sensor_alert = WaterSensorAlert()
    else:
        if water_sensor_alert is not None:
            water_sensor_alert.deactivate()
            water_sensor_alert = None


devices.dishwasher_leak_sensor.water_leak.add_listener(activate_water_sensor_alert)


class Tv(Broadcaster):
    def __init__(self, current: NumericParameter):
        super().__init__()
        self._is_on: bool | None = False

        current.add_listener(self._current_listener)

    def _current_listener(self):
        new_is_on = devices.ikea_smart_plug.current.get() > 0.4

        if self._is_on is None:
            self._is_on = new_is_on
            return

        state_changed = self._is_on != new_is_on
        self._is_on = new_is_on

        if state_changed:
            self._call_listeners()

    def get(self) -> bool:
        if self._is_on is None:
            return False

        return self._is_on


tv_state = Tv(devices.ikea_smart_plug.current)
