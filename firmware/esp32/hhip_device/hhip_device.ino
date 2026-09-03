/*
 * HHIP Device Firmware — ESP32
 *
 * Phase 1.3 (PoC-01): HELLO / HELLO_ACK / HEARTBEAT / ACK over
 * newline-delimited JSON.
 *
 * Phase 1.4: adds a physical button (input, STATE_UPDATE source) and
 * a physical LED (output, STATE_UPDATE sink), extending — not
 * replacing — the Phase 1.3 message loop.
 *
 * Protocol: HHIP Protocol Version 1 (mirrors engine/protocol/messages.py)
 *
 * Dependency note (flagged per project rule "explain decisions that
 * affect the architecture before implementing them"): this firmware
 * uses the ArduinoJson library (https://arduinojson.org) rather than
 * hand-built JSON strings. Hand-rolled JSON on a microcontroller is a
 * common source of subtle bugs (escaping, buffer sizing) and
 * ArduinoJson is small, well-tested, and the de-facto standard for
 * exactly this use case — this is the "strong technical reason"
 * exception to "avoid unnecessary dependencies". Install via the
 * Arduino Library Manager: "ArduinoJson" (v6.x).
 *
 * Does not yet read a wall-clock time from the host, so `timestamp`
 * is device uptime in milliseconds (millis()), not epoch time. Once
 * Phase 1.5 (synchronization) exists, HHIP can supply a time
 * reference during/after HELLO_ACK.
 */

#include <ArduinoJson.h>

// ---- Configuration --------------------------------------------------

static const char* DEVICE_ID = "esp32_01";
static const char* DEVICE_TYPE = "esp32";
static const char* FIRMWARE_VERSION = "0.2.0";
static const uint32_t HEARTBEAT_INTERVAL_MS = 5000;
static const int PROTOCOL_VERSION = 1;
static const long SERIAL_BAUD = 115200;

// Phase 1.4: physical button (input) and physical LED (output).
// BUTTON_PIN uses INPUT_PULLUP, so the button should wire the pin to
// GND when pressed (active LOW) — no external resistor needed on
// most boards. LED_PIN defaults to GPIO2, the commonly-built-in LED
// on many ESP32 dev boards; change it if your board differs.
static const int BUTTON_PIN = 4;
static const int LED_PIN = 2;
static const uint32_t BUTTON_DEBOUNCE_MS = 50;

// Where an outgoing STATE_UPDATE from this device's button should be
// addressed. Matches engine/main.py's DEFAULT_VIRTUAL_LED_ID.
static const char* VIRTUAL_LED_TARGET = "virtual_led_01";

// ---- State ------------------------------------------------------------

static uint32_t outgoingSequence = 0;
static uint32_t lastHeartbeatMillis = 0;
static bool helloAcknowledged = false;

static String incomingLine;

// Phase 1.4 button debounce state.
static int lastStableButtonState = HIGH;   // HIGH = released (INPUT_PULLUP, active LOW)
static int lastRawButtonState = HIGH;
static uint32_t lastButtonChangeMillis = 0;


// ---- Helpers ------------------------------------------------------------

// Generates a reasonably unique message id without pulling in a UUID
// library. Not globally/cryptographically unique — sufficient for
// tracing/dedup within a single PoC-01 session.
String generateMessageId() {
  static uint32_t counter = 0;
  counter++;
  return String(DEVICE_ID) + "-" + String(millis()) + "-" + String(counter);
}

void sendMessage(const char* type, const char* target, JsonObject payload) {
  StaticJsonDocument<256> doc;
  doc["version"] = PROTOCOL_VERSION;
  doc["message_id"] = generateMessageId();
  doc["type"] = type;
  doc["source"] = DEVICE_ID;
  doc["target"] = target;
  doc["sequence"] = ++outgoingSequence;
  doc["timestamp"] = (uint32_t)millis();  // device uptime ms, see file header note
  doc["payload"] = payload;

  serializeJson(doc, Serial);
  Serial.print('\n');
}

void sendHello() {
  StaticJsonDocument<128> payloadDoc;
  JsonObject payload = payloadDoc.to<JsonObject>();
  payload["device_type"] = DEVICE_TYPE;
  payload["firmware_version"] = FIRMWARE_VERSION;
  sendMessage("HELLO", "hhip", payload);
}

void sendHeartbeat() {
  StaticJsonDocument<64> payloadDoc;
  JsonObject payload = payloadDoc.to<JsonObject>();
  sendMessage("HEARTBEAT", "hhip", payload);
}

// Phase 1.4: sends a STATE_UPDATE reporting this device's physical
// button state to the virtual LED it drives (Demonstration A).
void sendButtonStateUpdate(const char* state) {
  StaticJsonDocument<64> payloadDoc;
  JsonObject payload = payloadDoc.to<JsonObject>();
  payload["state"] = state;
  sendMessage("STATE_UPDATE", VIRTUAL_LED_TARGET, payload);
}

// Phase 1.4: polls the physical button with simple time-based
// debouncing and sends a STATE_UPDATE on genuine state changes only.
void checkButton() {
  int raw = digitalRead(BUTTON_PIN);

  if (raw != lastRawButtonState) {
    lastButtonChangeMillis = millis();
    lastRawButtonState = raw;
  }

  if ((millis() - lastButtonChangeMillis) >= BUTTON_DEBOUNCE_MS && raw != lastStableButtonState) {
    lastStableButtonState = raw;
    // Active LOW: pin reads LOW when pressed (INPUT_PULLUP wired to GND).
    if (raw == LOW) {
      sendButtonStateUpdate("ON");
    } else {
      sendButtonStateUpdate("OFF");
    }
  }
}

void handleIncomingLine(const String& line) {
  if (line.length() == 0) {
    return;
  }

  StaticJsonDocument<256> doc;
  DeserializationError err = deserializeJson(doc, line);
  if (err) {
    // Malformed line; drop it. A diagnostics/ERROR channel back to
    // the host is future work, not required for PoC-01.
    return;
  }

  const char* type = doc["type"];
  if (type == nullptr) {
    return;
  }

  if (strcmp(type, "HELLO_ACK") == 0) {
    helloAcknowledged = true;
  } else if (strcmp(type, "ACK") == 0) {
    // HHIP acknowledged a HEARTBEAT (or other message). Nothing
    // further required in PoC-01 beyond having received it.
  } else if (strcmp(type, "ERROR") == 0) {
    // Error handling policy is defined in later phases; PoC-01 just
    // needs to not crash on receiving one.
  } else if (strcmp(type, "STATE_UPDATE") == 0) {
    handleStateUpdate(doc);
  }
}

// Phase 1.4: applies an inbound STATE_UPDATE to the physical LED
// (Demonstration B), if this message is actually addressed to us —
// `target` is checked explicitly per the protocol's addressing
// semantics, even though this point-to-point serial link currently
// has only one possible recipient.
void handleStateUpdate(const JsonDocument& doc) {
  const char* target = doc["target"];
  if (target == nullptr || strcmp(target, DEVICE_ID) != 0) {
    return;  // not addressed to this device; ignore
  }

  const char* state = doc["payload"]["state"];
  if (state == nullptr) {
    return;
  }

  if (strcmp(state, "ON") == 0) {
    digitalWrite(LED_PIN, HIGH);
  } else if (strcmp(state, "OFF") == 0) {
    digitalWrite(LED_PIN, LOW);
  } else {
    return;  // unrecognized state; don't ACK something we didn't apply
  }

  StaticJsonDocument<64> payloadDoc;
  JsonObject ackPayload = payloadDoc.to<JsonObject>();
  ackPayload["ack_type"] = "STATE_UPDATE";
  sendMessage("ACK", "hhip", ackPayload);
}

// ---- Arduino entry points -----------------------------------------------

void setup() {
  Serial.begin(SERIAL_BAUD);
  // Give the host side a moment to open the port before we start
  // talking; avoids losing the very first HELLO on some USB-serial
  // chipsets that reset the ESP32 when the port opens.
  delay(1000);

  incomingLine.reserve(256);

  pinMode(BUTTON_PIN, INPUT_PULLUP);
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);
  lastRawButtonState = digitalRead(BUTTON_PIN);
  lastStableButtonState = lastRawButtonState;

  sendHello();
  lastHeartbeatMillis = millis();
}

void loop() {
  // Non-blocking line assembly from Serial.
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\n') {
      handleIncomingLine(incomingLine);
      incomingLine = "";
    } else if (c != '\r') {
      incomingLine += c;
    }
  }

  checkButton();

  uint32_t now = millis();
  if (now - lastHeartbeatMillis >= HEARTBEAT_INTERVAL_MS) {
    sendHeartbeat();
    lastHeartbeatMillis = now;
  }
}
