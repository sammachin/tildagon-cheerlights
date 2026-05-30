import app
import asyncio
import wifi
import time
import requests
from tildagonos import tildagonos
from system.patterndisplay.events import PatternDisable
from system.eventbus import eventbus
from events.input import Buttons, BUTTON_TYPES
from app_components.tokens import clear_background

try:
    from umqtt.simple import MQTTClient
    HAS_MQTT = True
except ImportError:
    HAS_MQTT = False

NUM_LEDS = 12
ANIM_STEP_S = 0.1
POLL_INTERVAL_S = 10
RECONNECT_INTERVAL_S = 15
CHEERLIGHTS_URL = "https://api.thingspeak.com/channels/1417/field/2/last.txt"
MQTT_BROKER = "mqtt.cheerlights.com"
MQTT_PORT = 1883


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
        super().__init__()

    def _mqtt_cb(self, topic, msg):
        try:
            color = hex_to_rgb(msg.decode())
            if color != self.current_color:
                self.target_color = color
        except Exception:
            pass

    def _set_all_leds(self, color):
        for i in range(1, NUM_LEDS + 1):
            tildagonos.leds[i] = color
        tildagonos.leds.write()

    def _cancelled(self):
        if self.button_states.get(BUTTON_TYPES["CANCEL"]):
            self.button_states.clear()
            return True
        return False

    def _cleanup(self):
        if self.mqtt:
            try:
                self.mqtt.disconnect()
            except Exception:
                pass

    def _fetch_color(self):
        try:
            r = requests.get(CHEERLIGHTS_URL)
            return hex_to_rgb(r.text)
        except Exception:
            return None

    def _connect_mqtt(self):
        if not HAS_MQTT:
            return False
        try:
            cid = "tildagon_{}".format(time.ticks_ms() % 99999)
            self.mqtt = MQTTClient(cid, MQTT_BROKER, port=MQTT_PORT)
            self.mqtt.set_callback(self._mqtt_cb)
            self.mqtt.connect()
            self.mqtt.subscribe(b"hex")
            return True
        except Exception:
            self.mqtt = None
            return False

    async def _animate(self, render_update):
        for i in range(1, NUM_LEDS + 1):
            if self._cancelled():
                return False
            tildagonos.leds[i] = (0, 0, 0)
            tildagonos.leds.write()
            await render_update()
            await asyncio.sleep(ANIM_STEP_S)

        color = self.target_color or self.current_color
        for i in range(1, NUM_LEDS + 1):
            if self._cancelled():
                return False
            tildagonos.leds[i] = color
            tildagonos.leds.write()
            await render_update()
            await asyncio.sleep(ANIM_STEP_S)

        self.current_color = color
        self.target_color = None
        return True

    async def run(self, render_update):
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

        self.status = "Fetching color..."
        await render_update()
        color = self._fetch_color()
        if color:
            self.current_color = color
            self._set_all_leds(color)
        await render_update()

        if self._connect_mqtt():
            self.mqtt_connected = True
            self.status = "Connected (MQTT)"
        else:
            self.status = "Polling (HTTP)"
        await render_update()

        poll_timer = 0.0
        reconnect_timer = 0.0

        while True:
            if self._cancelled():
                self._cleanup()
                self.minimise()
                return

            if self.mqtt_connected and self.mqtt:
                try:
                    self.mqtt.check_msg()
                except Exception:
                    self.mqtt_connected = False
                    self.mqtt = None
                    self.status = "Reconnecting..."

            if not self.mqtt_connected:
                poll_timer += 0.05
                if poll_timer >= POLL_INTERVAL_S:
                    poll_timer = 0
                    c = self._fetch_color()
                    if c and c != self.current_color:
                        self.target_color = c

                if HAS_MQTT:
                    reconnect_timer += 0.05
                    if reconnect_timer >= RECONNECT_INTERVAL_S:
                        reconnect_timer = 0
                        if self._connect_mqtt():
                            self.mqtt_connected = True
                            self.status = "Connected (MQTT)"
                            poll_timer = 0

            if self.target_color is not None:
                self.status = "New color!"
                await render_update()
                if not await self._animate(render_update):
                    self._cleanup()
                    self.minimise()
                    return
                self.status = "Connected (MQTT)" if self.mqtt_connected else "Polling (HTTP)"

            await asyncio.sleep(0.05)
            await render_update()

    def update(self, delta):
        pass

    def draw(self, ctx):
        clear_background(ctx)
        ctx.save()
        ctx.text_align = ctx.CENTER

        ctx.font_size = 20
        ctx.rgb(1, 1, 1)
        ctx.move_to(0, -50).text("CheerLights")

        ctx.font_size = 12
        ctx.rgb(0.6, 0.6, 0.6)
        ctx.move_to(0, -25).text(self.status)

        display_color = self.target_color if self.target_color is not None else self.current_color
        r, g, b = display_color
        if r or g or b:
            ctx.rgb(r / 255, g / 255, b / 255)
            ctx.arc(0, 20, 30, 0, 6.2832, 1).fill()
            ctx.rgb(0.3, 0.3, 0.3)
            ctx.line_width = 2
            ctx.arc(0, 20, 30, 0, 6.2832, 1).stroke()

        ctx.font_size = 10
        ctx.rgb(0.4, 0.4, 0.4)
        ctx.move_to(0, 70).text("CANCEL to exit")

        ctx.restore()


__app_export__ = CheerLightsApp
