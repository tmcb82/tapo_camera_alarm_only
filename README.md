# Tapo: Cameras Control (Alarm & Siren only)

A slimmed-down, **unofficial modified version** of
[JurajNyiri/HomeAssistant-Tapo-Control](https://github.com/JurajNyiri/HomeAssistant-Tapo-Control)
(based on upstream commit `16e2e71`, integration version 7.3.1).

It keeps the sign-in machinery and exactly three kinds of entities, and removes everything else.

## What is kept

**Entities**

| Entity | Platform |
| --- | --- |
| `<device> Siren` | `siren` |
| `<device> Manual Alarm Start` | `button` |
| `<device> Manual Alarm Stop` | `button` |

Entity class code, unique IDs and the capability detection for these three are unchanged from upstream, so existing
entities of the same name keep their entity IDs. Hub (H100/H200) child devices that have a siren are still supported.

**Signing in** (all upstream flows, unchanged)

- Adding a device: IP + control port, Camera Account (third-party account, verified against the RTSP stream, with the
  "skip RTSP check" option), optional Cloud Account password (admin), KLAP devices (TP-Link account e-mail + password),
  DHCP discovery
- Re-authentication for both the Camera Account and the Cloud Account
- Options flow: change IP / port / Camera Account / Cloud Account password, and the polling intervals
- `transport_method` override in `configuration.yaml`

## What was removed

Every other entity and everything that only existed to serve it: camera streams, switches, selects, numbers, lights,
sensors, binary sensors (including ONVIF motion events and webhooks), media player, update entity, the media source and
recording sync, time sync, sound detection, the Reboot / Format SD Card / Sync Time / PTZ / Calibrate / Play Chime
buttons, the `save_preset`, `delete_preset` and `set_record_plan` services, and the matching options and translations.

The integration also no longer requests the data for the removed features. Each poll asks the device for 10 distinct
pytapo methods (device info, privacy mask, IP, alarm and siren data, child device list) instead of 87.

## Installation

This keeps the domain `tapo_control`, so it is a **drop-in replacement** for the original integration and **cannot be
installed next to it**.

1. Remove / replace `custom_components/tapo_control` in your Home Assistant config folder with the one from this archive
   (or add this repository to HACS as a custom repository in place of the original).
2. Restart Home Assistant.

Existing config entries (version 25) keep working. Entries older than version 15 cannot be migrated and must be re-added.

### Things to know when upgrading from the original

- Entities that no longer exist (camera, sensors, switches, ...) stay in the entity registry as *unavailable* until you
  delete them in **Settings -> Devices & services -> Entities**. They are not removed automatically.
- Recordings already synced to disk by the original integration are left untouched, and are no longer cleaned up.
  Delete the folders yourself if you want the space back.
- `aiortc` and the `stream`, `onvif` and `network` Home Assistant dependencies are no longer required. `ffmpeg` still is,
  because the Camera Account is verified against the RTSP stream during sign-in.

## Network

- TCP/443 control (cameras, doorbells, hubs), TCP/80 for chimes
- TCP/554 and TCP/2020 must also be reachable while signing in: the config flow treats a device with these ports closed
  as "Camera Account not available" and asks for the Cloud Account password instead

Make sure Third-Party Compatibility is on in the Tapo app (**Me -> Tapo Lab -> Third-Party Compatibility**).

## License and attribution

Licensed under the Apache License 2.0 (see `LICENSE.md`), like the original. This is a modified version of the work of
Juraj Nyiri and contributors; the files were changed as described above. It is not endorsed by or affiliated with the
original author, so please do not report problems with this version upstream.
