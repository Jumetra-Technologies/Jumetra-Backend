/*
 * HHIP Hybrid Agent — ESP32 (Sprint 27)
 *
 * Newline-delimited JSON over Serial @ 115200.
 * Messages: DEVICE_DISCOVERY (EVENT), HEARTBEAT, GPIO_STATE (EVENT),
 * accepts GPIO_WRITE (EVENT) and WRITE.
 *
 * Requires ArduinoJson v6 (Library Manager).
 */

#include <ArduinoJson.h>
#include <WiFi.h>

static const long SERIAL_BAUD = 115200;
static const int PROTOCOL_VERSION = 1;
static const uint32_t HEARTBEAT_INTERVAL_MS = 5000;
static const char* BOARD_TYPE = "esp32";
static const char* FIRMWARE_VERSION = "1.0.0-hhip-agent";

// Built-in LED on many ESP32 dev boards
static const int LED_PIN = 2;
static const int BUTTON_PIN = 4;

static char deviceId[32];
static uint32_t outgoingSequence = 0;
static uint32_t lastHeartbeatMs = 0;
static String incomingLine;

static const int MAX_PINS = 4;
struct PinSpec {
  const char* pin_id;
  const char* name;
  int number;
  int state;
};

static PinSpec pins[MAX_PINS] = {
  {"D2", "GPIO2", 2, 0},
  {"D4", "GPIO4", 4, 0},
  {"D13", "GPIO13", 13, 0},
  {"D25", "GPIO25", 25, 0},
};

String generateMessageId() {
  static uint32_t counter = 0;
  counter++;
  return String(deviceId) + "-" + String(millis()) + "-" + String(counter);
}

void sendJsonDoc(JsonDocument& doc) {
  serializeJson(doc, Serial);
  Serial.print('\n');
}

void sendEvent(const char* eventName, JsonObject payload) {
  StaticJsonDocument<512> doc;
  doc["version"] = PROTOCOL_VERSION;
  doc["message_id"] = generateMessageId();
  doc["type"] = "EVENT";
  doc["source"] = deviceId;
  doc["target"] = "hhip";
  doc["sequence"] = ++outgoingSequence;
  doc["timestamp"] = (uint32_t)millis();
  JsonObject pl = doc.createNestedObject("payload");
  pl["event"] = eventName;
  for (JsonPair kv : payload) {
    pl[kv.key()] = kv.value();
  }
  sendJsonDoc(doc);
}

void sendHeartbeat() {
  StaticJsonDocument<128> doc;
  doc["version"] = PROTOCOL_VERSION;
  doc["message_id"] = generateMessageId();
  doc["type"] = "HEARTBEAT";
  doc["source"] = deviceId;
  doc["target"] = "hhip";
  doc["sequence"] = ++outgoingSequence;
  doc["timestamp"] = (uint32_t)millis();
  doc.createNestedObject("payload");
  sendJsonDoc(doc);
}

void sendGpioState(const char* pinId, int value) {
  StaticJsonDocument<128> payloadDoc;
  JsonObject payload = payloadDoc.to<JsonObject>();
  payload["pin"] = pinId;
  payload["value"] = value;
  sendEvent("GPIO_STATE", payload);
}

void sendDeviceDiscovery() {
  StaticJsonDocument<768> payloadDoc;
  JsonObject payload = payloadDoc.to<JsonObject>();
  payload["event"] = "DEVICE_DISCOVERY";
  payload["device_id"] = deviceId;
  payload["board_type"] = BOARD_TYPE;
  payload["device_type"] = BOARD_TYPE;
  payload["firmware_version"] = FIRMWARE_VERSION;
  payload["label"] = "ESP32 HHIP Agent";

  JsonArray caps = payload.createNestedArray("capabilities");
  caps.add("gpio");
  caps.add("pwm");
  caps.add("adc");
  caps.add("wifi");

  JsonArray pinArr = payload.createNestedArray("pins");
  for (int i = 0; i < MAX_PINS; i++) {
    JsonObject p = pinArr.createNestedObject();
    p["pin_id"] = pins[i].pin_id;
    p["name"] = pins[i].name;
    p["number"] = pins[i].number;
    p["interfaces"] = "gpio,pwm";
    p["state"] = pins[i].state;
  }

  StaticJsonDocument<896> doc;
  doc["version"] = PROTOCOL_VERSION;
  doc["message_id"] = generateMessageId();
  doc["type"] = "EVENT";
  doc["source"] = deviceId;
  doc["target"] = "hhip";
  doc["sequence"] = ++outgoingSequence;
  doc["timestamp"] = (uint32_t)millis();
  doc["payload"] = payload;
  sendJsonDoc(doc);
}

void generateDeviceId() {
  uint64_t mac = ESP.getEfuseMac();
  snprintf(deviceId, sizeof(deviceId), "esp32_%04X%08X",
           (uint16_t)(mac >> 32), (uint32_t)mac);
}

PinSpec* findPin(const char* pinId) {
  for (int i = 0; i < MAX_PINS; i++) {
    if (strcmp(pins[i].pin_id, pinId) == 0) return &pins[i];
  }
  return nullptr;
}

void applyGpioWrite(const char* pinId, int value) {
  PinSpec* pin = findPin(pinId);
  if (pin == nullptr) return;
  pin->state = value ? 1 : 0;
  if (strcmp(pinId, "D13") == 0 || pin->number == LED_PIN) {
    digitalWrite(LED_PIN, pin->state ? HIGH : LOW);
  } else {
    pinMode(pin->number, OUTPUT);
    digitalWrite(pin->number, pin->state ? HIGH : LOW);
  }
  sendGpioState(pinId, pin->state);
}

void handleMessage(JsonDocument& doc) {
  const char* type = doc["type"];
  JsonObject payload = doc["payload"];
  if (!type) return;

  if (strcmp(type, "EVENT") == 0) {
    const char* eventName = payload["event"];
    if (eventName && strcmp(eventName, "GPIO_WRITE") == 0) {
      const char* pin = payload["pin"];
      int value = payload["value"] | 0;
      if (pin) applyGpioWrite(pin, value);
    }
    return;
  }

  if (strcmp(type, "WRITE") == 0) {
    const char* pin = payload["pin"];
    int value = payload["value"] | 0;
    if (pin) applyGpioWrite(pin, value);
    return;
  }

  if (strcmp(type, "HELLO") == 0 || strcmp(type, "HELLO_ACK") == 0) {
    sendDeviceDiscovery();
  }
}

void setup() {
  Serial.begin(SERIAL_BAUD);
  pinMode(LED_PIN, OUTPUT);
  pinMode(BUTTON_PIN, INPUT_PULLUP);
  generateDeviceId();
  delay(300);
  sendDeviceDiscovery();
  lastHeartbeatMs = millis();
}

void loop() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n') {
      if (incomingLine.length() > 0) {
        StaticJsonDocument<512> doc;
        DeserializationError err = deserializeJson(doc, incomingLine);
        if (!err) handleMessage(doc);
        incomingLine = "";
      }
    } else {
      incomingLine += c;
    }
  }

  if (millis() - lastHeartbeatMs >= HEARTBEAT_INTERVAL_MS) {
    sendHeartbeat();
    lastHeartbeatMs = millis();
  }
}
