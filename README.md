# Tapo Camera Alarm Control

Version 1.0.2 - [github.com/tmcb82/tapo_camera_alarm_only](https://github.com/tmcb82/tapo_camera_alarm_only)

A slimmed-down, **unofficial modified version** of
[JurajNyiri/HomeAssistant-Tapo-Control](https://github.com/JurajNyiri/HomeAssistant-Tapo-Control)
by Juraj Nyiri and contributors (based on upstream commit `16e2e71`, integration version 7.3.1). Almost all of the
code, including everything that talks to the cameras, is their work.

It keeps the sign-in machinery and three entities from the original, adds one diagnostic sensor of its own, and removes
everything else.

## What is kept

**Entities**

| Entity | Platform |
| --- | --- |
| `<device> Siren` | `siren` |
| `<device> Manual Alarm Start` | `button` |
| `<device> Manual Alarm Stop` | `button` |
| `<device> TP-Link Cloud` | `binary_sensor` (diagnostic, new in this version) |

The entity code and the capability detection for the siren and the two buttons are unchanged from upstream. Hub (H100/H200) child
devices that have a siren are still supported.

**Signing in**

- Adding a device: IP + control port, then the Camera Account (the third-party account created in the Tapo app). Both
  username and password are required, and they are always verified against the RTSP stream. Then the TP-Link Cloud
  password (admin), which is required because the alarm relies on it, and is verified against the device. KLAP devices
  (TP-Link account e-mail + password) and DHCP discovery are supported as well.
- Re-authentication for both the Camera Account and TP-Link Cloud
- Options flow: change IP / port / Camera Account / TP-Link Cloud password, and the polling intervals
- `transport_method` override in `configuration.yaml`, under the `tapo_alarm_control:` key

## TP-Link Cloud sensor

`<device> TP-Link Cloud` is a diagnostic binary sensor that does not exist in the original integration.

- **On** when the last poll of the device succeeded: the camera accepted the stored login (the cloud password) and
  answered.
- **Off** when the last poll failed. The attributes tell you why (`last_failure_reason`: `invalid_authentication`,
  `temporary_suspension` or `error`), how many polls in a row failed (`consecutive_failures`), when the last good poll
  was (`last_successful_poll`) and whether a cloud password is configured (`using_cloud_password`).
- It sends **no requests of its own** and never logs in by itself. It reflects the regular data update, which runs
  every 30 seconds by default (10 minutes for battery devices, see the update interval options).
- After four failed polls in a row because of an invalid login, the integration stops polling and starts Home
  Assistant's re-authentication flow, so a wrong password cannot keep hitting the camera. The sensor stays off until
  you re-authenticate.
- Despite the name, it reflects the TP-Link cloud login (the cloud password), which the camera checks locally. It does
  **not** report whether the camera can reach TP-Link's servers.

## What was removed

Every other entity and everything that only existed to serve it: camera streams, switches, selects, numbers, lights,
sensors, binary sensors (including ONVIF motion events and webhooks; only the new TP-Link Cloud sensor exists), media player, update entity, the media source and
recording sync, time sync, sound detection, the Reboot / Format SD Card / Sync Time / PTZ / Calibrate / Play Chime
buttons, the `save_preset`, `delete_preset` and `set_record_plan` services, and the matching options.

The "skip RTSP check" option of the setup flow was removed as well. The check is always performed.

The integration also no longer requests the data for the removed features. Each poll asks the device for 10 distinct
pytapo methods (device info, privacy mask, IP, alarm and siren data, child device list) instead of 87.

Only the English translation is included. Home Assistant shows English in every other language.

## Installation

1. Copy `custom_components/tapo_alarm_control` into the `custom_components` folder of your Home Assistant
   configuration (or add this repository to HACS as a custom repository).
2. Restart Home Assistant.
3. Go to **Settings -> Devices & services -> Add integration** and pick **Tapo Camera Alarm Control**.

The integration domain is `tapo_alarm_control`, so it does not conflict with the original `tapo_control` integration and
both can be installed at the same time. Everything is new under this domain: devices and entities are created from
scratch and nothing is shared with, or migrated from, the original integration.

### Running next to the original

- Do not add the same device to both integrations. Both would create a `Siren` entity with the same name, so Home
  Assistant would add `_2` to the entity IDs of one of them.
- If you want to replace the original for a device, remove that device's entry from the original integration first, or
  disable its entities.
- `ffmpeg` is the only Home Assistant dependency, because the Camera Account is verified against the RTSP stream during
  sign-in. The `stream`, `onvif` and `network` dependencies and `aiortc` are not required.

## Network

- TCP/443 control (cameras, doorbells, hubs), TCP/80 for chimes
- TCP/554 and TCP/2020 must also be reachable while signing in: the setup flow reports "Port 443, 554, or 2020 is
  closed" otherwise

Make sure Third-Party Compatibility is on in the Tapo app (**Me -> Tapo Lab -> Third-Party Compatibility**).

## Icon

The icon and logo in `custom_components/tapo_alarm_control/brand/` are the Tapo images the original integration uses in the
Home Assistant brands repository, copied unchanged. Tapo and TP-Link are trademarks of TP-Link, and this project is not
affiliated with TP-Link. They need Home Assistant 2026.3 or newer, which the manifest already requires.

## License and attribution

Licensed under the Apache License 2.0 (see `LICENSE.md`), like the original. This is a modified version of
[HomeAssistant-Tapo-Control](https://github.com/JurajNyiri/HomeAssistant-Tapo-Control) by Juraj Nyiri and
contributors, and the files were changed as described above. It is not endorsed by or affiliated with the original
author, so please do not report problems with this version upstream. Use
[this repository](https://github.com/tmcb82/tapo_camera_alarm_only) instead.
