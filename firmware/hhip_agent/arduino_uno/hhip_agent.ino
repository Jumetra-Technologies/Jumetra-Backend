/*
 * HHIP Hybrid Agent — Arduino Uno (Sprint 27)
 *
 * Newline-delimited JSON @ 115200.
 * Minimal JSON builder (no external libraries).
 */

static const long SERIAL_BAUD = 115200;
static const int PROTOCOL_VERSION = 1;
static const uint32_t HEARTBEAT_INTERVAL_MS = 5000;
static const int LED_PIN = 13;

static char deviceId[24] = "uno_000000";
static uint32_t outgoingSequence = 0;
static uint32_t lastHeartbeatMs = 0;
static String incomingLine;

static int pinStates[3] = {0, 0, 0};  // D2, D13, A0 mapped

uint32_t simpleHash() {
  uint32_t h = 0;
  for (int i = 0; i < 6; i++) {
    h = h * 31 + analogRead(A0) + i * 17;
  }
  return h;
}

void sendLine(const String& line) {
  Serial.println(line);
}

String nextMessageId() {
  static uint32_t counter = 0;
  counter++;
  return String(deviceId) + "-" + String(millis()) + "-" + String(counter);
}

void sendHeartbeat() {
  String msg = "{";
  msg += "\"version\":" + String(PROTOCOL_VERSION) + ",";
  msg += "\"message_id\":\"" + nextMessageId() + "\",";
  msg += "\"type\":\"HEARTBEAT\",";
  msg += "\"source\":\"" + String(deviceId) + "\",";
  msg += "\"target\":\"hhip\",";
  msg += "\"sequence\":" + String(++outgoingSequence) + ",";
  msg += "\"timestamp\":" + String(millis()) + ",";
  msg += "\"payload\":{}";
  msg += "}";
  sendLine(msg);
}

void sendGpioState(const char* pinId, int value) {
  String msg = "{";
  msg += "\"version\":" + String(PROTOCOL_VERSION) + ",";
  msg += "\"message_id\":\"" + nextMessageId() + "\",";
  msg += "\"type\":\"EVENT\",";
  msg += "\"source\":\"" + String(deviceId) + "\",";
  msg += "\"target\":\"hhip\",";
  msg += "\"sequence\":" + String(++outgoingSequence) + ",";
  msg += "\"timestamp\":" + String(millis()) + ",";
  msg += "\"payload\":{\"event\":\"GPIO_STATE\",\"pin\":\"" + String(pinId) + "\",\"value\":" + String(value) + "}";
  msg += "}";
  sendLine(msg);
}

void sendDeviceDiscovery() {
  String msg = "{";
  msg += "\"version\":" + String(PROTOCOL_VERSION) + ",";
  msg += "\"message_id\":\"" + nextMessageId() + "\",";
  msg += "\"type\":\"EVENT\",";
  msg += "\"source\":\"" + String(deviceId) + "\",";
  msg += "\"target\":\"hhip\",";
  msg += "\"sequence\":" + String(++outgoingSequence) + ",";
  msg += "\"timestamp\":" + String(millis()) + ",";
  msg += "\"payload\":{";
  msg += "\"event\":\"DEVICE_DISCOVERY\",";
  msg += "\"device_id\":\"" + String(deviceId) + "\",";
  msg += "\"board_type\":\"arduino-uno\",";
  msg += "\"device_type\":\"arduino-uno\",";
  msg += "\"firmware_version\":\"1.0.0-hhip-agent\",";
  msg += "\"label\":\"Arduino Uno HHIP Agent\",";
  msg += "\"capabilities\":[\"gpio\",\"adc\",\"pwm\"],";
  msg += "\"pins\":[";
  msg += "{\"pin_id\":\"D2\",\"name\":\"Digital 2\",\"number\":2,\"interfaces\":[\"gpio\"],\"state\":" + String(pinStates[0]) + "},";
  msg += "{\"pin_id\":\"D13\",\"name\":\"LED\",\"number\":13,\"interfaces\":[\"gpio\"],\"state\":" + String(pinStates[1]) + "},";
  msg += "{\"pin_id\":\"A0\",\"name\":\"Analog 0\",\"number\":\"A0\",\"interfaces\":[\"adc\"],\"signal\":\"input\",\"state\":" + String(pinStates[2]) + "}";
  msg += "]}}";
  sendLine(msg);
}

void applyGpioWrite(const String& pinId, int value) {
  if (pinId == "D13") {
    pinStates[1] = value ? 1 : 0;
    digitalWrite(LED_PIN, pinStates[1] ? HIGH : LOW);
    sendGpioState("D13", pinStates[1]);
  } else if (pinId == "D2") {
    pinStates[0] = value ? 1 : 0;
    pinMode(2, OUTPUT);
    digitalWrite(2, pinStates[0] ? HIGH : LOW);
    sendGpioState("D2", pinStates[0]);
  }
}

bool jsonExtract(const String& json, const String& key, String& out) {
  String needle = "\"" + key + "\":";
  int idx = json.indexOf(needle);
  if (idx < 0) return false;
  idx += needle.length();
  while (idx < (int)json.length() && json[idx] == ' ') idx++;
  if (idx >= (int)json.length()) return false;
  if (json[idx] == '"') {
    idx++;
    int end = json.indexOf('"', idx);
    if (end < 0) return false;
    out = json.substring(idx, end);
    return true;
  }
  int end = idx;
  while (end < (int)json.length() && json[end] != ',' && json[end] != '}') end++;
  out = json.substring(idx, end);
  return true;
}

void handleLine(const String& line) {
  String type, event, pin, valueStr;
  if (!jsonExtract(line, "type", type)) return;

  if (type == "EVENT") {
    jsonExtract(line, "event", event);
    if (event == "GPIO_WRITE") {
      jsonExtract(line, "pin", pin);
      jsonExtract(line, "value", valueStr);
      applyGpioWrite(pin, valueStr.toInt());
    } else if (type == "HELLO" || type == "HELLO_ACK") {
      sendDeviceDiscovery();
    }
    return;
  }

  if (type == "WRITE") {
    jsonExtract(line, "pin", pin);
    jsonExtract(line, "value", valueStr);
    applyGpioWrite(pin, valueStr.toInt());
    return;
  }

  if (type == "HELLO" || type == "HELLO_ACK") {
    sendDeviceDiscovery();
  }
}

void setup() {
  Serial.begin(SERIAL_BAUD);
  pinMode(LED_PIN, OUTPUT);
  snprintf(deviceId, sizeof(deviceId), "uno_%06lu", (unsigned long)(simpleHash() % 1000000UL));
  delay(300);
  sendDeviceDiscovery();
  lastHeartbeatMs = millis();
}

void loop() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n') {
      if (incomingLine.length() > 0) {
        handleLine(incomingLine);
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
