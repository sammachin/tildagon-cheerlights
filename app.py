import app
import asyncio
import wifi
import time
import json
import requests
from tildagonos import tildagonos
from system.patterndisplay.events import PatternDisable, PatternEnable
from system.eventbus import eventbus
from events.input import Buttons, BUTTON_TYPES
from app_components import TextDialog, clear_background
from umqtt.simple import MQTTClient

NUM_LEDS = 12
ANIM_STEP_S = 0.1
RECONNECT_INTERVAL_S = 15
CHEERLIGHTS_URL = "https://api.thingspeak.com/channels/1417/field/2/last.txt"

DEFAULT_SETTINGS = {
    "server": "mqtt.cheerlights.com",
    "port": "1883",
    "topic": "hex",
}

_dir = __file__.rsplit("/", 1)[0] if "/" in __file__ else "."
SETTINGS_PATH = _dir + "/settings.json"

VIEW_MAIN = 0
VIEW_MENU = 1

FIELDS = [("server", "Server"), ("port", "Port"), ("topic", "Topic")]


def hex_to_rgb(hex_str):
    h = hex_str.strip().lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


class CheerLightsApp(app.App):
    def __init__(self):
        self.button_states = Buttons(self)
        self.current_color = (0, 0, 0)
        self.target_color = None
        self.status = "Starting..."
        self.mqtt = None
        self.mqtt_connected = False
        self.initialised = False
        self.animating = False
        self.anim_phase = 0
        self.anim_led = 1
        self.anim_timer = 0.0
        self.reconnect_timer = 0.0
        self.settings = self._load_settings()
        self.view = VIEW_MAIN
        self.menu_index = 0
        super().__init__()

    # --- Settings persistence ---

    def _load_settings(self):
        try:
            with open(SETTINGS_PATH, "r") as f:
                s = json.load(f)
            for k, v in DEFAULT_SETTINGS.items():
                if k not in s:
                    s[k] = v
            return s
        except Exception:
            return dict(DEFAULT_SETTINGS)

    def _save_settings(self):
        try:
            with open(SETTINGS_PATH, "w") as f:
                json.dump(self.settings, f)
        except Exception:
            pass

    # --- MQTT ---

    def _mqtt_cb(self, topic, msg):
        try:
            color = hex_to_rgb(msg.decode())
            if color != self.current_color:
                self.target_color = color
        except Exception:
            pass

    def _connect_mqtt(self):
        try:
            cid = "tildagon_{}".format(time.ticks_ms() % 99999)
            self.mqtt = MQTTClient(
                cid,
                self.settings["server"],
                port=int(self.settings["port"]),
            )
            self.mqtt.set_callback(self._mqtt_cb)
            self.mqtt.connect()
            self.mqtt.subscribe(self.settings["topic"].encode())
            return True
        except Exception:
            self.mqtt = None
            return False

    def _disconnect_mqtt(self):
        if self.mqtt:
            try:
                self.mqtt.disconnect()
            except Exception:
                pass
            self.mqtt = None
        self.mqtt_connected = False

    # --- LED helpers ---

    def _set_all_leds(self, color):
        for i in range(1, NUM_LEDS + 1):
            tildagonos.leds[i] = color
        tildagonos.leds.write()

    def _shutdown(self):
        self.initialised = False
        self._disconnect_mqtt()
        eventbus.emit(PatternEnable())

    # --- Background (runs in fg and bg) ---

    def background_update(self, delta):
        if not self.initialised:
            return

        if self.animating:
            self.anim_timer += 0.05
            if self.anim_timer >= ANIM_STEP_S:
                self.anim_timer = 0
                self._animate_step()

        if self.mqtt_connected and self.mqtt:
            try:
                self.mqtt.check_msg()
            except Exception:
                self.mqtt_connected = False
                self.mqtt = None
                self.status = "Reconnecting..."

        if not self.mqtt_connected:
            self.reconnect_timer += 0.05
            if self.reconnect_timer >= RECONNECT_INTERVAL_S:
                self.reconnect_timer = 0
                if self._connect_mqtt():
                    self.mqtt_connected = True
                    self.status = "Connected"

        if self.target_color is not None and not self.animating:
            self.animating = True
            self.anim_phase = 0
            self.anim_led = 1

    def _animate_step(self):
        if self.anim_phase == 0:
            tildagonos.leds[self.anim_led] = (0, 0, 0)
            tildagonos.leds.write()
            self.anim_led += 1
            if self.anim_led > NUM_LEDS:
                self.anim_phase = 1
                self.anim_led = 1
        else:
            color = self.target_color or self.current_color
            tildagonos.leds[self.anim_led] = color
            tildagonos.leds.write()
            self.anim_led += 1
            if self.anim_led > NUM_LEDS:
                self.current_color = self.target_color or self.current_color
                self.target_color = None
                self.animating = False

    # --- Settings dialog ---

    async def _edit_field(self, key, label, render_update):
        dialog = TextDialog(
            "{} ({})".format(label, self.settings[key]), self
        )
        self.overlays = [dialog]
        if await dialog.run(render_update):
            value = dialog.text.strip()
            if value:
                old = self.settings[key]
                self.settings[key] = value
                self._save_settings()
                if value != old and self.initialised:
                    self._disconnect_mqtt()
                    if self._connect_mqtt():
                        self.mqtt_connected = True
                        self.status = "Connected"
                    else:
                        self.status = "MQTT failed"
        self.overlays = []

    # --- Setup ---

    async def _setup(self, render_update):
        eventbus.emit(PatternDisable())
        tildagonos.set_led_power(True)

        self.status = "Connecting WiFi..."
        await render_update()
        try:
            wifi.connect()
            await asyncio.sleep(2)
        except Exception:
            self.status = "WiFi failed"
            await render_update()

        if self.settings["server"] == DEFAULT_SETTINGS["server"]:
            self.status = "Fetching color..."
            await render_update()
            try:
                r = requests.get(CHEERLIGHTS_URL)
                color = hex_to_rgb(r.text)
                self.current_color = color
                self._set_all_leds(color)
            except Exception:
                pass
            await render_update()

        self.status = "Connecting MQTT..."
        await render_update()
        if self._connect_mqtt():
            self.mqtt_connected = True
            self.status = "Connected"
        else:
            self.status = "MQTT failed"

        self.initialised = True

    # --- Main loop ---

    async def run(self, render_update):
        await self._setup(render_update)

        self.view = VIEW_MAIN
        await render_update()

        while True:
            if not self.initialised:
                if self.button_states.get(BUTTON_TYPES["CONFIRM"]):
                    self.button_states.clear()
                    self.status = "Connecting..."
                    await render_update()
                    await self._setup(render_update)
                    self.view = VIEW_MAIN
                elif self.button_states.get(BUTTON_TYPES["CANCEL"]):
                    self.button_states.clear()
                    self.minimise()
                await asyncio.sleep(0.05)
                await render_update()
                continue

            if self.view == VIEW_MAIN:
                if self.button_states.get(BUTTON_TYPES["CONFIRM"]):
                    self.button_states.clear()
                    self._shutdown()
                    self.status = "Disconnected"
                elif self.button_states.get(BUTTON_TYPES["CANCEL"]):
                    self.button_states.clear()
                    self.minimise()
                elif self.button_states.get(BUTTON_TYPES["UP"]):
                    self.button_states.clear()
                    self.view = VIEW_MENU
                    self.menu_index = 0

                if self.initialised:
                    if self.animating:
                        self.status = "New color!"
                    elif self.mqtt_connected:
                        self.status = "Connected"
                    else:
                        self.status = "Reconnecting..."

            elif self.view == VIEW_MENU:
                if self.button_states.get(BUTTON_TYPES["UP"]):
                    self.button_states.clear()
                    self.menu_index = (self.menu_index - 1) % 4
                elif self.button_states.get(BUTTON_TYPES["DOWN"]):
                    self.button_states.clear()
                    self.menu_index = (self.menu_index + 1) % 4
                elif self.button_states.get(BUTTON_TYPES["CONFIRM"]):
                    self.button_states.clear()
                    if self.menu_index < len(FIELDS):
                        key, label = FIELDS[self.menu_index]
                        await self._edit_field(key, label, render_update)
                    elif self.menu_index == len(FIELDS):
                        self.settings = dict(DEFAULT_SETTINGS)
                        self._save_settings()
                        self._disconnect_mqtt()
                        if self._connect_mqtt():
                            self.mqtt_connected = True
                            self.status = "Connected"
                        else:
                            self.status = "MQTT failed"
                        self.view = VIEW_MAIN
                elif self.button_states.get(BUTTON_TYPES["CANCEL"]):
                    self.button_states.clear()
                    self.view = VIEW_MAIN

            await asyncio.sleep(0.05)
            await render_update()

    def update(self, delta):
        pass

    # --- Drawing ---

    def draw(self, ctx):
        clear_background(ctx)
        if not self.initialised:
            ctx.save()
            ctx.text_align = ctx.CENTER
            ctx.font_size = 18
            ctx.rgb(1, 1, 1)
            ctx.move_to(0, -30).text("CheerLights")
            ctx.font_size = 14
            ctx.rgb(0.6, 0.6, 0.6)
            ctx.move_to(0, 0).text(self.status)
            ctx.font_size = 10
            ctx.rgb(0.4, 0.4, 0.4)
            ctx.move_to(0, 30).text("CONFIRM: reconnect")
            ctx.move_to(0, 45).text("CANCEL: back")
            ctx.restore()
            return
        if self.view == VIEW_MAIN:
            self._draw_main(ctx)
        elif self.view == VIEW_MENU:
            self._draw_menu(ctx)
        self.draw_overlays(ctx)

    def _draw_main(self, ctx):
        ctx.save()
        ctx.text_align = ctx.CENTER

        ctx.font_size = 20
        ctx.rgb(1, 1, 1)
        ctx.move_to(0, -50).text("CheerLights")

        ctx.font_size = 12
        ctx.rgb(0.6, 0.6, 0.6)
        ctx.move_to(0, -25).text(self.status)

        dc = self.target_color if self.target_color is not None else self.current_color
        r, g, b = dc
        if r or g or b:
            ctx.rgb(r / 255, g / 255, b / 255)
            ctx.arc(0, 20, 30, 0, 6.2832, 1).fill()
            ctx.rgb(0.3, 0.3, 0.3)
            ctx.line_width = 2
            ctx.arc(0, 20, 30, 0, 6.2832, 1).stroke()

        ctx.font_size = 10
        ctx.rgb(0.4, 0.4, 0.4)
        ctx.move_to(0, 65).text("UP:settings")
        ctx.move_to(0, 78).text("CANCEL:bg  CONFIRM:exit")

        ctx.restore()

    def _draw_menu(self, ctx):
        ctx.save()
        ctx.text_align = ctx.CENTER

        ctx.font_size = 18
        ctx.rgb(1, 1, 1)
        ctx.move_to(0, -65).text("Settings")

        for i, (key, label) in enumerate(FIELDS):
            y = -30 + i * 28
            selected = i == self.menu_index
            ctx.font_size = 14 if selected else 12
            ctx.rgb(1, 1, 0) if selected else ctx.rgb(0.6, 0.6, 0.6)
            val = str(self.settings[key])
            if len(val) > 14:
                val = val[:13] + ".."
            prefix = "> " if selected else "  "
            ctx.move_to(0, y).text("{}{}:{}".format(prefix, label, val))

        y = -30 + len(FIELDS) * 28
        selected = self.menu_index == len(FIELDS)
        ctx.font_size = 14 if selected else 12
        ctx.rgb(1, 1, 0) if selected else ctx.rgb(0.6, 0.6, 0.6)
        prefix = "> " if selected else "  "
        ctx.move_to(0, y).text("{}Reset defaults".format(prefix))

        ctx.font_size = 9
        ctx.rgb(0.4, 0.4, 0.4)
        ctx.move_to(0, 80).text("UP/DOWN CONFIRM/CANCEL")

        ctx.restore()


__app_export__ = CheerLightsApp
