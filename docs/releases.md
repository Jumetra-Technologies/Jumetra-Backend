# Desktop releases

The website's download page and the desktop app's update check read the
newest release from this API. Only the release pipeline writes releases.

## Tables (migration `0003_releases`)

`releases`: one published version on a channel.

| column | |
|---|---|
| `channel` | `stable` or `beta` |
| `version` | semantic version, unique per channel |
| `notes` | what changed, shown in the app |
| `minimum_version` | versions older than this must update before they keep working (optional) |
| `published_at` | when it becomes visible; a future time schedules it |
| `withdrawn_at` | set when a bad build is pulled; it's then never offered |

`release_files`: one installer of a release, unique per platform, architecture and kind.

| column | |
|---|---|
| `platform` | `windows`, `linux`, `macos` |
| `arch` | `x64`, `arm64` |
| `kind` | `nsis`, `dmg`, `zip`, `appimage`, `deb`, `rpm` |
| `url` | https download link (the pipeline uploads the file; this only records it) |
| `sha512` | base64 SHA-512, as electron-builder writes it in `latest.yml` |
| `size` | bytes |

Releases can't be edited: a fix is a new version. Withdrawing is the only change.

## Routes

`GET /releases/latest?channel=stable&platform=windows&arch=x64` (public, cached 5 minutes)

The highest version (semantic order, so `0.10.0` beats `0.9.0` and
`1.0.0-beta.2` comes before `1.0.0`) that is published, not withdrawn, and has
an installer for the platform and architecture asked for. Without `platform`
and `arch`, every installer of the newest release. 404 when there's none.

```json
{
  "channel": "stable",
  "version": "0.5.0",
  "notes": "Build, libraries and error explanations.",
  "minimum_version": null,
  "published_at": "2026-11-02T12:00:00+00:00",
  "files": [{ "platform": "windows", "arch": "x64", "kind": "nsis", "url": "https://…", "sha512": "…", "size": 120000000 }]
}
```

`POST /releases` with `Authorization: Bearer $KIUNGO_RELEASE_TOKEN`: publish.
409 if the version is already on the channel.

`POST /releases/{channel}/{version}/withdraw`, same token: stop offering it.

## Setup

Set `KIUNGO_RELEASE_TOKEN` on the server to a long random value and give the
same value to the release pipeline as a secret. Without it, publishing answers
503 and reading still works.
