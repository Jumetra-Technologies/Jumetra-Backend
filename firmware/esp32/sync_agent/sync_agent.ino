/*
 * HHIP ESP32 Sync Agent Prototype (Sprint 16)
 *
 * Measurement + bounded software clock correction (no hardware oscillator change).
 *
 * Receives SYNC_REQUEST / SYNC_CORRECTION_REQUEST over serial (newline-delimited JSON),
 * maintains a software clock offset model, and returns SYNC_RESPONSE /
 * SYNC_CORRECTION_RESPONSE.
 *
 * Protocol: HHIP Protocol Version 1 envelope + Sprint 9/16 sync fields.
 *
 * Dependency: ArduinoJson (Library Manager, v6.x)
 *
 * Flash this sketch alone for sync measurement + correction experiments.
 * Does not replace firmware/esp32/hhip_device/ (full device firmware).
 */

#include <ArduinoJson.h>

static const char* DEVICE_ID = "esp32_01";
static const int PROTOCOL_VERSION = 1;
static const long SERIAL_BAUD = 115200;

static uint32_t outgoingSequence = 0;
static String incomingLine;

// Software clock model — does NOT modify hardware oscillator.
static int32_t softwareClockOffsetMs = 0;
static float accumulatedCorrectionMs = 0.0f;

uint32_t deviceClockNow() {
  return (uint32_t)((int32_t)millis() + softwareClockOffsetMs);
}

String generateMessageId() {
  static uint32_t counter = 0;
  counter++;
  return String(DEVICE_ID) + "-" + String(millis()) + "-" + String(counter);
}

void sendSyncResponse(JsonObjectConst requestDoc) {
  uint32_t device_timestamp = deviceClockNow();

  JsonObjectConst payloadIn = requestDoc["payload"].as<JsonObjectConst>();

  uint32_t sequence_number = 0;
  if (!payloadIn.isNull() && payloadIn.containsKey("sequence_number")) {
    sequence_number = payloadIn["sequence_number"] | 0;
  } else if (requestDoc.containsKey("sequence")) {
    sequence_number = requestDoc["sequence"] | 0;
  }

  const char* correlation_id = "";
  if (!payloadIn.isNull() && payloadIn["correlation_id"].is<const char*>()) {
    correlation_id = payloadIn["correlation_id"];
  }

  uint32_t server_timestamp = 0;
  if (!payloadIn.isNull()) {
    if (payloadIn.containsKey("server_timestamp")) {
      server_timestamp = payloadIn["server_timestamp"] | 0;
    } else if (payloadIn.containsKey("request_time")) {
      server_timestamp = payloadIn["request_time"] | 0;
    }
  }

  const char* request_id = "";
  if (!payloadIn.isNull() && payloadIn["request_id"].is<const char*>()) {
    request_id = payloadIn["request_id"];
  } else if (requestDoc["message_id"].is<const char*>()) {
    request_id = requestDoc["message_id"];
  }

  StaticJsonDocument<384> doc;
  doc["version"] = PROTOCOL_VERSION;
  doc["message_id"] = generateMessageId();
  doc["type"] = "SYNC_RESPONSE";
  doc["source"] = DEVICE_ID;
  doc["target"] = "hhip";
  doc["sequence"] = ++outgoingSequence;
  doc["timestamp"] = device_timestamp;

  JsonObject payload = doc.createNestedObject("payload");
  payload["sequence_number"] = sequence_number;
  payload["device_id"] = DEVICE_ID;
  payload["server_timestamp"] = server_timestamp;
  payload["device_timestamp"] = device_timestamp;
  payload["correlation_id"] = correlation_id;
  payload["request_id"] = request_id;
  payload["request_time"] = server_timestamp;
  payload["server_timestamp"] = device_timestamp;
  payload["server_timestamp_host"] = server_timestamp;
  payload["software_clock_offset"] = softwareClockOffsetMs;

  serializeJson(doc, Serial);
  Serial.print('\n');
}

void sendCorrectionResponse(JsonObjectConst requestDoc, bool applied) {
  uint32_t device_timestamp = deviceClockNow();

  JsonObjectConst payloadIn = requestDoc["payload"].as<JsonObjectConst>();

  const char* transaction_id = "";
  if (!payloadIn.isNull() && payloadIn["transaction_id"].is<const char*>()) {
    transaction_id = payloadIn["transaction_id"];
  } else if (requestDoc["message_id"].is<const char*>()) {
    transaction_id = requestDoc["message_id"];
  }

  float correction_step = 0.0f;
  if (!payloadIn.isNull() && payloadIn.containsKey("correction_step")) {
    correction_step = payloadIn["correction_step"] | 0.0f;
  }

  const char* correlation_id = "";
  if (!payloadIn.isNull() && payloadIn["correlation_id"].is<const char*>()) {
    correlation_id = payloadIn["correlation_id"];
  }

  StaticJsonDocument<384> doc;
  doc["version"] = PROTOCOL_VERSION;
  doc["message_id"] = generateMessageId();
  doc["type"] = "SYNC_CORRECTION_RESPONSE";
  doc["source"] = DEVICE_ID;
  doc["target"] = "hhip";
  doc["sequence"] = ++outgoingSequence;
  doc["timestamp"] = device_timestamp;

  JsonObject payload = doc.createNestedObject("payload");
  payload["transaction_id"] = transaction_id;
  payload["device_id"] = DEVICE_ID;
  payload["correction_step"] = correction_step;
  payload["timestamp"] = device_timestamp;
  payload["applied"] = applied;
  payload["accumulated_correction"] = accumulatedCorrectionMs;
  payload["software_clock_offset"] = (float)softwareClockOffsetMs;
  payload["correlation_id"] = correlation_id;

  serializeJson(doc, Serial);
  Serial.print('\n');
}

void handleCorrectionRequest(JsonObjectConst requestDoc) {
  JsonObjectConst payloadIn = requestDoc["payload"].as<JsonObjectConst>();
  if (payloadIn.isNull()) {
    sendCorrectionResponse(requestDoc, false);
    return;
  }

  float correction_step = payloadIn["correction_step"] | 0.0f;

  // Apply bounded software clock adjustment (device-side mirror of host step).
  // Positive step = device was ahead → subtract from software clock.
  int32_t stepMs = (int32_t)correction_step;
  softwareClockOffsetMs -= stepMs;
  accumulatedCorrectionMs += abs(correction_step);

  sendCorrectionResponse(requestDoc, true);
}

void handleIncomingLine(const String& line) {
  if (line.length() == 0) {
    return;
  }

  StaticJsonDocument<512> doc;
  DeserializationError err = deserializeJson(doc, line);
  if (err) {
    return;
  }

  const char* type = doc["type"];
  if (type == nullptr) {
    return;
  }

  if (strcmp(type, "SYNC_REQUEST") == 0) {
    sendSyncResponse(doc.as<JsonObjectConst>());
  } else if (strcmp(type, "SYNC_CORRECTION_REQUEST") == 0) {
    handleCorrectionRequest(doc.as<JsonObjectConst>());
  }
}

void setup() {
  Serial.begin(SERIAL_BAUD);
  delay(200);
  StaticJsonDocument<128> hello;
  hello["version"] = PROTOCOL_VERSION;
  hello["message_id"] = generateMessageId();
  hello["type"] = "HELLO";
  hello["source"] = DEVICE_ID;
  hello["target"] = "hhip";
  hello["sequence"] = ++outgoingSequence;
  hello["timestamp"] = (uint32_t)millis();
  JsonObject payload = hello.createNestedObject("payload");
  payload["device_type"] = "esp32";
  payload["firmware_version"] = "sync_agent_0.2.0";
  payload["sync_agent"] = true;
  payload["correction_agent"] = true;
  serializeJson(hello, Serial);
  Serial.print('\n');
}

void loop() {
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\n') {
      handleIncomingLine(incomingLine);
      incomingLine = "";
    } else if (c != '\r') {
      incomingLine += c;
      if (incomingLine.length() > 512) {
        incomingLine = "";
      }
    }
  }
}
