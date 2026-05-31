# CheerLights for Tildagon Badge

A [Tildagon Badge](https://tildagon.badge.emfcamp.org/) app that connects to the [CheerLights](https://cheerlights.com) service and displays the current color on the badge's 12 LEDs.

## How it works

On launch the app connects to WiFi, fetches the current CheerLights color via HTTP, and sets all LEDs. It then subscribes to the CheerLights MQTT broker for real-time updates.

When a new color is received the LEDs turn off one by one clockwise, then light up again in the new color. This animation runs whether the app is in the foreground or background.

## Settings

Press **UP** from the main screen to open the settings menu. You can configure a custom MQTT server, port, and topic. Settings are saved to the badge and persist across reboots. Select **Reset defaults** to restore the CheerLights defaults.

## Controls

- **UP** - Open settings
- **CANCEL** - Send app to background (MQTT stays connected, LEDs keep updating)
- **CONFIRM** - Disconnect and exit (LEDs return to system pattern)

From the disconnected screen press **CONFIRM** to reconnect or **CANCEL** to return to the menu.

## Install

### From the App Store

Add the `tildagon-app` topic to your fork of this repo and create a release. The app will appear in the [Tildagon App Store](https://apps.badge.emfcamp.org/) within 15 minutes.

### Local install

Copy the app to your badge using `mpremote`:

```bash
mpremote cp -r . :/apps/sammachin_cheerlights/
```

## License

MIT
