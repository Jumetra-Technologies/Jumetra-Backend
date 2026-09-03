# HHIP ESP32 Sync Agent (Sprint 9)

Measurement-only prototype. Receives `SYNC_REQUEST`, captures `millis()`,
returns `SYNC_RESPONSE`. **No clock correction.**

## Flash

1. Install ArduinoJson (v6.x) via Library Manager.
2. Open `sync_agent.ino` in Arduino IDE / PlatformIO.
3. Select your ESP32 board and serial port.
4. Upload at 115200 baud.

## Wire format

Host → device:

```json
{"version":1,"type":"SYNC_REQUEST","source":"hhip","target":"esp32_01","sequence":1,"timestamp":...,"payload":{"request_id":"...","sequence_number":1,"device_id":"esp32_01","server_timestamp":...,"device_timestamp":0,"correlation_id":"..."}}
```

Device → host: `SYNC_RESPONSE` with `device_timestamp = millis()`.

## Note

This sketch is separate from `firmware/esp32/hhip_device/` (full device
firmware). Merge sync handling into the main sketch in a later sprint.
