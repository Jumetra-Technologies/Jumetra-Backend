# Compile service

Compiles Arduino Uno and Nano sketches to Intel HEX for the website's Engineering Lab, which runs the program in its emulator. It holds no accounts, no database and no secrets, and runs as its own Render web service (Docker, `compile_service/Dockerfile`).

## API

`POST /firmware/compile`

```json
{ "board": "arduino-uno", "files": [{ "path": "Blink.ino", "content": "void setup(){} void loop(){}" }] }
```

Answer (200):

| Field | |
|---|---|
| `ok` | The build worked. |
| `hex` | The program as Intel HEX, when `ok`. |
| `log` | Everything the compiler said. The website turns it into problems with `parseDiagnostics(log, sketchDir)` from `@kiungo/core/build`, the parser the desktop app uses. |
| `sketchDir` | The folder the files were built in, for that parser. |
| `flash`, `ram` | `{ used, max }` in bytes. |
| `durationMs`, `cached` | How long it took; whether an identical sketch's build was reused. |
| `message` | Why it couldn't build at all, in plain words (timeout, compiler didn't run). |

Errors: `422` the sketch was refused before compiling (the detail says why), `429` too many builds from this address or the compiler is busy (with `Retry-After`), `403` a website that isn't allowed.

`GET /health` answers `{ "ok": true }`.

## Limits and safety

- **Boards:** `arduino-uno` and `arduino-nano` (`arduino:avr@1.8.6`, installed when the image is built; nothing is downloaded at run time).
- **Files:** up to 16 flat files and 256 KB, named like `Blink.ino` or `motor.h`, with exactly one `.ino`. There is no `sketch.yaml`.
- **Includes:**
  - Every `#include` must name a plain header.
  - These are refused: absolute paths, `..`, macro includes, line continuations, `__has_include`, `#include_next`, `#embed` and `.incbin`.
  - The rules hold for the text as the preprocessor sees it: lines joined by `\`, comments, digraphs (`%:`) and trigraphs (`??=`) are resolved first, so `# /**/ include`, a split `#in\` + `clude`, and `%:include` are checked like `#include`.
- **Inline assembly:** `asm(...)` takes plain string literals and no assembler directives (no line starting with `.`, such as `.incbin` or `.include`). Strings next to each other count as one. The template can't come from a macro, and `asm` can't be renamed with `#define`.
- **Token pasting:** `##` (and `%:%:`) is refused, since it could build any of the above from pieces.
- **Limits:**
  - 60 s per build.
  - Per address, 6 builds a minute and 60 an hour (`COMPILE_RATE_PER_MINUTE`, `COMPILE_RATE_PER_HOUR`). The address is the first `X-Forwarded-For` entry, or the header named in `COMPILE_CLIENT_IP_HEADER` when the host sets one callers can't (for example `cf-connecting-ip`).
  - Each file's text is at most 256 KB, refused while the request is read.
  - 2 builds at once and 8 waiting (`COMPILE_WORKERS`, `COMPILE_QUEUE`).
- **Isolation:**
  - The container runs as an unprivileged user and holds no credentials.
  - The compiler gets a cut-down environment.
  - Each build gets a fresh folder, deleted afterwards.
  - The input checks are a first line, not a sandbox: never give this service secrets or database access.
- **Allowed websites:** `COMPILE_CORS_ORIGINS`, comma-separated. The default is the production websites and localhost.
