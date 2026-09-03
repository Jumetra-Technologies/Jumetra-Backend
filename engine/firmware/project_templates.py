"""Project templates — Blink, sensors, comms starters."""

from __future__ import annotations

from typing import Any

from .firmware_project import FirmwareFile, Language, ProjectType


TEMPLATES: dict[str, dict[str, Any]] = {
    "blink": {
        "name": "Blink",
        "description": "Classic LED blink on GPIO",
        "category": "basic",
    },
    "led": {
        "name": "LED Control",
        "description": "Digital LED on/off via serial",
        "category": "basic",
    },
    "servo": {
        "name": "Servo",
        "description": "Sweep a servo on a PWM pin",
        "category": "actuators",
    },
    "relay": {
        "name": "Relay",
        "description": "Drive a relay module",
        "category": "actuators",
    },
    "dht11": {
        "name": "DHT11",
        "description": "Temperature & humidity sensor",
        "category": "sensors",
    },
    "hc-sr04": {
        "name": "HC-SR04",
        "description": "Ultrasonic distance sensor",
        "category": "sensors",
    },
    "mq2": {
        "name": "MQ2",
        "description": "Gas sensor analog read",
        "category": "sensors",
    },
    "lcd": {
        "name": "LCD",
        "description": "HD44780 / I2C LCD hello world",
        "category": "display",
    },
    "i2c": {
        "name": "I2C Scanner",
        "description": "Scan I2C bus for devices",
        "category": "buses",
    },
    "spi": {
        "name": "SPI Loop",
        "description": "SPI master transfer demo",
        "category": "buses",
    },
    "wifi": {
        "name": "WiFi Connect",
        "description": "ESP WiFi station connect",
        "category": "wireless",
    },
    "bluetooth": {
        "name": "Bluetooth",
        "description": "BLE / Classic BT stub",
        "category": "wireless",
    },
    "mqtt": {
        "name": "MQTT",
        "description": "Publish sensor data over MQTT",
        "category": "wireless",
    },
}


def list_templates() -> list[dict[str, Any]]:
    return [{"id": k, **v} for k, v in TEMPLATES.items()]


def generate_template(
    template_id: str,
    *,
    board_type: str = "esp32",
    project_type: str = ProjectType.ARDUINO_SKETCH.value,
) -> list[FirmwareFile]:
    tid = (template_id or "blink").lower()
    if tid not in TEMPLATES:
        tid = "blink"

    if project_type in (
        ProjectType.MICROPYTHON.value,
        ProjectType.CIRCUITPYTHON.value,
        ProjectType.RASPBERRY_PI.value,
    ):
        return _python_files(tid, board_type)

    if project_type == ProjectType.PLATFORMIO.value:
        return _platformio_files(tid, board_type)

    if project_type == ProjectType.ESP_IDF.value:
        return _esp_idf_files(tid)

    return _arduino_files(tid, board_type)


def _arduino_files(tid: str, board_type: str) -> list[FirmwareFile]:
    sketches = {
        "blink": '''\
// HHIP Blink — {board}
void setup() {{
  pinMode(LED_BUILTIN, OUTPUT);
  Serial.begin(115200);
  Serial.println("HHIP Blink ready");
}}

void loop() {{
  digitalWrite(LED_BUILTIN, HIGH);
  Serial.println("GPIO HIGH");
  delay(500);
  digitalWrite(LED_BUILTIN, LOW);
  Serial.println("GPIO LOW");
  delay(500);
}}
''',
        "led": '''\
void setup() {{
  pinMode(2, OUTPUT);
  Serial.begin(115200);
}}
void loop() {{
  if (Serial.available()) {{
    String cmd = Serial.readStringUntil('\\n');
    cmd.trim();
    if (cmd == "ON") digitalWrite(2, HIGH);
    if (cmd == "OFF") digitalWrite(2, LOW);
  }}
}}
''',
        "servo": '''\
#include <Servo.h>
Servo s;
void setup() {{
  s.attach(9);
  Serial.begin(115200);
}}
void loop() {{
  for (int a = 0; a <= 180; a++) {{ s.write(a); delay(15); }}
  for (int a = 180; a >= 0; a--) {{ s.write(a); delay(15); }}
}}
''',
        "relay": '''\
#define RELAY_PIN 5
void setup() {{ pinMode(RELAY_PIN, OUTPUT); Serial.begin(115200); }}
void loop() {{
  digitalWrite(RELAY_PIN, HIGH); Serial.println("RELAY ON"); delay(1000);
  digitalWrite(RELAY_PIN, LOW); Serial.println("RELAY OFF"); delay(1000);
}}
''',
        "dht11": '''\
// Requires DHT library
#include <DHT.h>
#define DHTPIN 4
#define DHTTYPE DHT11
DHT dht(DHTPIN, DHTTYPE);
void setup() {{ Serial.begin(115200); dht.begin(); }}
void loop() {{
  float h = dht.readHumidity();
  float t = dht.readTemperature();
  Serial.print("T="); Serial.print(t); Serial.print(" H="); Serial.println(h);
  delay(2000);
}}
''',
        "hc-sr04": '''\
#define TRIG 9
#define ECHO 10
void setup() {{ pinMode(TRIG, OUTPUT); pinMode(ECHO, INPUT); Serial.begin(115200); }}
void loop() {{
  digitalWrite(TRIG, LOW); delayMicroseconds(2);
  digitalWrite(TRIG, HIGH); delayMicroseconds(10);
  digitalWrite(TRIG, LOW);
  long dur = pulseIn(ECHO, HIGH);
  float cm = dur * 0.034 / 2;
  Serial.print("CM="); Serial.println(cm);
  delay(200);
}}
''',
        "mq2": '''\
void setup() {{ Serial.begin(115200); }}
void loop() {{
  int v = analogRead(A0);
  Serial.print("MQ2="); Serial.println(v);
  delay(500);
}}
''',
        "lcd": '''\
#include <LiquidCrystal_I2C.h>
LiquidCrystal_I2C lcd(0x27, 16, 2);
void setup() {{ lcd.init(); lcd.backlight(); lcd.print("HHIP LCD"); }}
void loop() {{}}
''',
        "i2c": '''\
#include <Wire.h>
void setup() {{ Wire.begin(); Serial.begin(115200); }}
void loop() {{
  byte err, addr; int n = 0;
  for (addr = 1; addr < 127; addr++) {{
    Wire.beginTransmission(addr);
    err = Wire.endTransmission();
    if (err == 0) {{ Serial.print("0x"); Serial.println(addr, HEX); n++; }}
  }}
  Serial.print("Found "); Serial.println(n);
  delay(3000);
}}
''',
        "spi": '''\
#include <SPI.h>
void setup() {{ SPI.begin(); Serial.begin(115200); }}
void loop() {{
  SPI.transfer(0xAA);
  Serial.println("SPI xfer");
  delay(500);
}}
''',
        "wifi": '''\
#include <WiFi.h>
const char* ssid = "HHIP";
const char* pass = "password";
void setup() {{
  Serial.begin(115200);
  WiFi.begin(ssid, pass);
  while (WiFi.status() != WL_CONNECTED) {{ delay(500); Serial.print("."); }}
  Serial.println(WiFi.localIP());
}}
void loop() {{}}
''',
        "bluetooth": '''\
// ESP32 BLE stub — expand with BLEDevice
void setup() {{ Serial.begin(115200); Serial.println("BT stub"); }}
void loop() {{ delay(1000); }}
''',
        "mqtt": '''\
#include <WiFi.h>
#include <PubSubClient.h>
WiFiClient wifi;
PubSubClient mqtt(wifi);
void setup() {{ Serial.begin(115200); /* connect WiFi + mqtt */ }}
void loop() {{ mqtt.loop(); mqtt.publish("hhip/telemetry", "ok"); delay(2000); }}
''',
    }
    body = sketches.get(tid, sketches["blink"]).format(board=board_type)
    return [
        FirmwareFile(path="src/main.ino", content=body, language="cpp"),
        FirmwareFile(
            path="README.md",
            content=f"# HHIP {TEMPLATES[tid]['name']}\n\nBoard: {board_type}\n",
            language="markdown",
        ),
    ]


def _platformio_files(tid: str, board_type: str) -> list[FirmwareFile]:
    ino = _arduino_files(tid, board_type)[0]
    env = "esp32dev" if "esp32" in board_type else "uno"
    ini = f"""\
[env:{env}]
platform = espressif32
board = {env}
framework = arduino
monitor_speed = 115200
"""
    if board_type.startswith("arduino"):
        ini = f"""\
[env:uno]
platform = atmelavr
board = uno
framework = arduino
monitor_speed = 115200
"""
    return [
        FirmwareFile(path="platformio.ini", content=ini, language="ini"),
        FirmwareFile(path="src/main.cpp", content=ino.content.replace("LED_BUILTIN", "2"), language="cpp"),
    ]


def _esp_idf_files(tid: str) -> list[FirmwareFile]:
    return [
        FirmwareFile(
            path="main/main.c",
            content='''\
#include <stdio.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/gpio.h"

void app_main(void) {
    gpio_set_direction(GPIO_NUM_2, GPIO_MODE_OUTPUT);
    while (1) {
        gpio_set_level(GPIO_NUM_2, 1);
        printf("GPIO HIGH\\n");
        vTaskDelay(500 / portTICK_PERIOD_MS);
        gpio_set_level(GPIO_NUM_2, 0);
        printf("GPIO LOW\\n");
        vTaskDelay(500 / portTICK_PERIOD_MS);
    }
}
''',
            language="c",
        ),
        FirmwareFile(
            path="CMakeLists.txt",
            content="cmake_minimum_required(VERSION 3.16)\ninclude($ENV{IDF_PATH}/tools/cmake/project.cmake)\nproject(hhip_app)\n",
            language="cmake",
        ),
    ]


def _python_files(tid: str, board_type: str) -> list[FirmwareFile]:
    code = {
        "blink": '''\
# HHIP MicroPython / Pi blink
import time
try:
    from machine import Pin
    led = Pin(2, Pin.OUT)
    while True:
        led.value(1)
        print("GPIO HIGH")
        time.sleep(0.5)
        led.value(0)
        print("GPIO LOW")
        time.sleep(0.5)
except ImportError:
    # Raspberry Pi fallback
    print("Simulated blink on", {board!r})
    while True:
        print("GPIO HIGH"); time.sleep(0.5)
        print("GPIO LOW"); time.sleep(0.5)
'''.format(board=board_type),
        "mqtt": '''\
# HHIP MQTT stub (MicroPython / Pi)
print("MQTT template — configure broker and publish telemetry")
''',
    }
    body = code.get(tid, code["blink"])
    return [FirmwareFile(path="main.py", content=body, language="python")]


def default_language_for(project_type: str) -> str:
    return {
        ProjectType.ARDUINO_SKETCH.value: Language.ARDUINO_CPP.value,
        ProjectType.ESP_IDF.value: Language.ESP_IDF.value,
        ProjectType.PLATFORMIO.value: Language.PLATFORMIO.value,
        ProjectType.MICROPYTHON.value: Language.MICROPYTHON.value,
        ProjectType.CIRCUITPYTHON.value: Language.CIRCUITPYTHON.value,
        ProjectType.STM32.value: Language.ARDUINO_CPP.value,
        ProjectType.RASPBERRY_PI.value: Language.RASPBERRY_PI_PYTHON.value,
    }.get(project_type, Language.ARDUINO_CPP.value)
