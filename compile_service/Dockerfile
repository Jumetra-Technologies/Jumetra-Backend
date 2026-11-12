# Kiungo's compile service: Arduino CLI and the AVR core baked in, no secrets.
# Build from the repository root:  docker build -f compile_service/Dockerfile .
FROM python:3.12-slim

ARG ARDUINO_CLI_VERSION=1.5.1
# From https://github.com/arduino/arduino-cli/releases/download/v1.5.1/1.5.1-checksums.txt (same as the desktop app's fetch script).
ARG ARDUINO_CLI_SHA256=28a8e119c498a25607821c36cb2dc49e8463941b261a0d99091baa7bc692dd2b
ARG AVR_CORE=arduino:avr@1.8.6

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    ARDUINO_DIRECTORIES_DATA=/opt/arduino/data \
    ARDUINO_DIRECTORIES_USER=/opt/arduino/user \
    ARDUINO_DIRECTORIES_DOWNLOADS=/opt/arduino/downloads \
    ARDUINO_BUILD_CACHE_PATH=/var/cache/kiungo-build \
    ARDUINO_UPDATER_ENABLE_NOTIFICATION=false

RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl \
    && curl -fsSL -o /tmp/cli.tgz "https://github.com/arduino/arduino-cli/releases/download/v${ARDUINO_CLI_VERSION}/arduino-cli_${ARDUINO_CLI_VERSION}_Linux_64bit.tar.gz" \
    && echo "${ARDUINO_CLI_SHA256}  /tmp/cli.tgz" | sha256sum -c - \
    && tar -xzf /tmp/cli.tgz -C /usr/local/bin arduino-cli \
    && rm /tmp/cli.tgz \
    && apt-get purge -y curl && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

# The core and its compiler, installed once at build time; the service never downloads anything.
RUN arduino-cli core update-index \
    && arduino-cli core install "${AVR_CORE}" \
    && rm -rf /opt/arduino/downloads/* && mkdir -p /opt/arduino/user

RUN useradd --system --create-home --home-dir /home/compiler --shell /usr/sbin/nologin compiler \
    && mkdir -p "${ARDUINO_BUILD_CACHE_PATH}" && chown compiler "${ARDUINO_BUILD_CACHE_PATH}"

WORKDIR /app
COPY compile_service/requirements.txt compile_service/requirements.txt
RUN pip install --no-cache-dir -r compile_service/requirements.txt
COPY compile_service compile_service

USER compiler
# Warm the core cache, so the first visitor's Blink doesn't pay for compiling the Arduino core.
RUN mkdir -p /tmp/warm/Blink \
    && printf 'void setup(){pinMode(13,OUTPUT);}\nvoid loop(){digitalWrite(13,HIGH);delay(500);digitalWrite(13,LOW);delay(500);}\n' > /tmp/warm/Blink/Blink.ino \
    && arduino-cli compile --fqbn arduino:avr:uno /tmp/warm/Blink \
    && arduino-cli compile --fqbn arduino:avr:nano:cpu=atmega328 /tmp/warm/Blink \
    && rm -rf /tmp/warm

EXPOSE 8080
CMD ["sh", "-c", "exec uvicorn compile_service.app:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips '*'"]
