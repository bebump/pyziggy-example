import datetime
import json
import os
from pathlib import Path
from typing import Callable, Any

from pyziggy.device_bases import LightWithColorTemp, LightWithColor, LightWithDimming
from pyziggy.message_loop import MessageLoopTimer
from pyziggy.parameters import Broadcaster
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
)
from pyziggy_autogenerate.available_devices import (
    AvailableDevices,
    Philips_RDM002,
    IKEA_TRADFRI_remote_control,
)

devices = AvailableDevices()

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

living_room = ScaleMapper(
    [
        (L2S(devices.standing_lamp), 0.0, 0.7),
        (L2S(devices.couch), 0.2, 0.7),
        (L2S(devices.color_bulb), 0.7, 1.0),
    ]
)


def set_mired(mired):
    for device in devices.get_devices():
        if isinstance(device, LightWithColorTemp):
            device.color_temp.set(mired)


def ikea_remote_action_handler():
    action = devices.ikea_remote.action.get_enum_value()
    types = devices.ikea_remote.action.enum_type

    if action == types.brightness_move_up:
        kitchen.add(0.075)
    elif action == types.brightness_move_down:
        kitchen.add(-0.075)
    elif action == types.on:
        devices.dining_light_1.state.set(1)
        devices.dining_light_2.state.set(1)
    elif action == types.off:
        devices.dining_light_1.state.set(0)
        devices.dining_light_2.state.set(0)
    elif action == types.arrow_left_click:
        set_mired(417)
    elif action == types.arrow_right_click:
        set_mired(370)


ikea_remote_action_broadcaster = IkeaN2CommandRepeater(devices.ikea_remote)
ikea_remote_action_broadcaster.repeating_action.add_listener(ikea_remote_action_handler)


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
        if action == t.button_3_press:
            self.philips_dial_handler = hue_changer
            self.start()
        if action == t.button_4_press:
            self.philips_dial_handler = saturation_changer
            self.start()
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
        self._timer.start(5)

    def stop(self):
        self._timer.stop()

    def _timer_callback(self, timer: MessageLoopTimer):
        new_mired = self._calculator.get_current_mired()

        if new_mired != self._last_mired:
            self.on_change._call_listeners()
            self._last_mired = new_mired


auto_color_temp = AutoColorTemp()

lights_with_color_temp: list[LightWithColorTemp] = [
    l for l in devices.get_devices() if isinstance(l, LightWithColorTemp)
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
    devices.color_bulb,
    devices.hue_lightstrip,
    devices.standing_lamp,
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

    for light in [devices.dining_light_1, devices.dining_light_2]:
        light.brightness.set_normalized(0.5)


turn_on_lights_in_the_morning = OnceADay(8.5, turn_on_morning_lights)
devices.on_connect.add_listener(lambda: turn_on_lights_in_the_morning.start())
