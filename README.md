# CheerLights for Tildagon Badge

A [Tildagon Badge](https://tildagon.badge.emfcamp.org/) app that connects to the [CheerLights](https://cheerlights.com) service and displays the current color on the badge's 12 LEDs.

## How it works

On launch the app connects to WiFi, fetches the current CheerLights color via HTTP, and sets all LEDs. It then subscribes to the CheerLights MQTT broker for real-time updates. If `umqtt` is not available in the firmware it falls back to polling the ThingSpeak API every 10 seconds.

When a new color is received the LEDs turn off one by one clockwise, then light up again in the new color.

## Install

### From the App Store

Add the `tildagon-app` topic to your fork of this repo and create a release. The app will appear in the [Tildagon App Store](https://apps.badge.emfcamp.org/) within 15 minutes.

### Local install

Copy the app to your badge using `mpremote`:

```bash
mpremote cp -r . :/apps/sammachin_cheerlights/
```

## Controls

Press **CANCEL** to exit the app.

## License

MIT
