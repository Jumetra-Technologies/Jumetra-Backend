import json

import pytest

from engine.protocol.messages import (
    PROTOCOL_VERSION,
    ErrorCode,
    MessageType,
    ProtocolError,
    create_message,
    decode_message,
    encode_message,
    is_valid,
    validate_message,
)


class TestCreateMessage:
    def test_creates_message_with_required_fields(self):
        msg = create_message(
            type_=MessageType.HELLO,
            source="esp32_01",
            target="hhip",
            sequence=1,
            payload={"device_type": "esp32"},
        )
        assert msg["version"] == PROTOCOL_VERSION
        assert msg["type"] == MessageType.HELLO
        assert msg["source"] == "esp32_01"
        assert msg["target"] == "hhip"
        assert msg["sequence"] == 1
        assert msg["payload"] == {"device_type": "esp32"}
        assert isinstance(msg["message_id"], str) and msg["message_id"]
        assert isinstance(msg["timestamp"], int)

    def test_defaults_payload_to_empty_dict(self):
        msg = create_message(type_=MessageType.HEARTBEAT, source="esp32_01", target="hhip", sequence=2)
        assert msg["payload"] == {}

    def test_generates_unique_message_ids(self):
        msg1 = create_message(type_=MessageType.HELLO, source="esp32_01", target="hhip", sequence=1)
        msg2 = create_message(type_=MessageType.HELLO, source="esp32_01", target="hhip", sequence=2)
        assert msg1["message_id"] != msg2["message_id"]

    def test_explicit_message_id_and_timestamp_are_respected(self):
        msg = create_message(
            type_=MessageType.ACK,
            source="hhip",
            target="esp32_01",
            sequence=3,
            message_id="fixed-id",
            timestamp=1234,
        )
        assert msg["message_id"] == "fixed-id"
        assert msg["timestamp"] == 1234


class TestEncodeDecode:
    def test_encode_produces_valid_json_string(self):
        msg = create_message(type_=MessageType.HELLO, source="esp32_01", target="hhip", sequence=1)
        encoded = encode_message(msg)
        assert isinstance(encoded, str)
        assert json.loads(encoded) == msg

    def test_encode_does_not_append_newline(self):
        msg = create_message(type_=MessageType.HELLO, source="esp32_01", target="hhip", sequence=1)
        encoded = encode_message(msg)
        assert not encoded.endswith("\n")

    def test_decode_round_trips_with_encode(self):
        original = create_message(type_=MessageType.HEARTBEAT, source="esp32_01", target="hhip", sequence=5)
        decoded = decode_message(encode_message(original))
        assert decoded == original

    def test_decode_strips_trailing_newline(self):
        original = create_message(type_=MessageType.ACK, source="hhip", target="esp32_01", sequence=1)
        line = encode_message(original) + "\n"
        assert decode_message(line) == original

    def test_decode_rejects_empty_line(self):
        with pytest.raises(ProtocolError):
            decode_message("")

    def test_decode_rejects_invalid_json(self):
        with pytest.raises(ProtocolError):
            decode_message("{not valid json")

    def test_decode_rejects_non_object_json(self):
        with pytest.raises(ProtocolError):
            decode_message("[1, 2, 3]")

    def test_encode_rejects_non_serializable_payload(self):
        msg = create_message(type_=MessageType.HELLO, source="esp32_01", target="hhip", sequence=1)
        msg["payload"] = {"bad": object()}
        with pytest.raises(ProtocolError):
            encode_message(msg)


class TestValidateMessage:
    def test_valid_message_has_no_errors(self):
        msg = create_message(type_=MessageType.HELLO, source="esp32_01", target="hhip", sequence=1)
        assert validate_message(msg) == []
        assert is_valid(msg) is True

    def test_missing_field_is_reported(self):
        msg = create_message(type_=MessageType.HELLO, source="esp32_01", target="hhip", sequence=1)
        del msg["sequence"]
        errors = validate_message(msg)
        assert errors
        assert is_valid(msg) is False

    def test_unknown_message_type_is_reported(self):
        msg = create_message(type_=MessageType.HELLO, source="esp32_01", target="hhip", sequence=1)
        msg["type"] = "NOT_A_REAL_TYPE"
        errors = validate_message(msg)
        assert any("Unknown message type" in e for e in errors)

    def test_unsupported_version_is_reported(self):
        msg = create_message(type_=MessageType.HELLO, source="esp32_01", target="hhip", sequence=1)
        msg["version"] = 99
        errors = validate_message(msg)
        assert any("Unsupported protocol version" in e for e in errors)

    def test_empty_source_is_reported(self):
        msg = create_message(type_=MessageType.HELLO, source="esp32_01", target="hhip", sequence=1)
        msg["source"] = ""
        errors = validate_message(msg)
        assert any("source" in e for e in errors)

    def test_non_integer_sequence_is_reported(self):
        msg = create_message(type_=MessageType.HELLO, source="esp32_01", target="hhip", sequence=1)
        msg["sequence"] = "1"
        errors = validate_message(msg)
        assert any("sequence" in e for e in errors)

    def test_non_dict_payload_is_reported(self):
        msg = create_message(type_=MessageType.HELLO, source="esp32_01", target="hhip", sequence=1)
        msg["payload"] = "not-a-dict"
        errors = validate_message(msg)
        assert any("payload" in e for e in errors)

    def test_all_poc01_message_types_are_known(self):
        from engine.protocol.messages import ALL_MESSAGE_TYPES, POC01_MESSAGE_TYPES

        assert POC01_MESSAGE_TYPES.issubset(ALL_MESSAGE_TYPES)
        assert POC01_MESSAGE_TYPES == {
            MessageType.HELLO,
            MessageType.HELLO_ACK,
            MessageType.HEARTBEAT,
            MessageType.ACK,
        }

    def test_error_codes_defined(self):
        assert ErrorCode.INVALID_MESSAGE == "INVALID_MESSAGE"
        assert ErrorCode.SEQUENCE_ERROR == "SEQUENCE_ERROR"
