---
description: Stream a simulator's framebuffer to stdout as MJPEG or H.264 (AVCC), retuned live over stdin. Use when a host process or plugin consumes frames without a browser.
---

# Frame streaming

`baguette stream` writes a booted simulator's frames to stdout for another
process to decode, and reads retune commands on stdin while it runs. The
browser gets the same encoder over a WebSocket instead ([serve.md](../../serve.md)).
Every flag: [commands.md#baguette-stream](../../commands.md#baguette-stream).

## Quick start

```bash
baguette stream --udid <UDID> --format avcc --fps 60 > frames.avcc
baguette stream --udid <UDID> --format mjpeg --scale 2 | my-consumer
```

Ctrl-C stops the stream cleanly.

## Output

| `--format` | stdout bytes |
|---|---|
| `mjpeg` (default) | One `HTTP/1.1 200 OK` + `multipart/x-mixed-replace; boundary=frame` header, then one `--frame` part per JPEG. Frames with unchanged pixels are skipped. |
| `avcc` | A sequence of chunks, each a 4-byte big-endian length (covering the tag and payload) followed by a 1-byte tag and the payload. Every frame is sent: H.264 deltas depend on the ones before them. |

AVCC tags:

| Tag | Payload |
|---|---|
| `0x01` | avcC description (SPS/PPS); feed to `VideoDecoder.configure` |
| `0x02` | Keyframe (IDR) |
| `0x03` | Delta frame |
| `0x04` | JPEG seed, so a consumer paints before the first keyframe lands |

The stream WebSocket carries the same `[tag][payload]` messages without the
length prefix, one per binary message.

## Retune while streaming

Write one JSON line per command to stdin. The key is **`cmd`** (the
WebSocket uses `type` for the same commands, see [wire.md](../../wire.md)):

```json
{"cmd":"set_bitrate","bps":4000000}
{"cmd":"set_fps","fps":30}
{"cmd":"set_scale","scale":2}
{"cmd":"force_idr"}
{"cmd":"snapshot"}
```

`force_idr` makes the next frame a keyframe; `snapshot` sends a fresh JPEG
seed (`0x04`).

## Gotchas

- `--help` lists `h264` as a format, but only `mjpeg` and `avcc` are
  accepted; anything else exits with `Unknown format`.
- The AVCC framing is baguette's own, not a raw H.264 elementary stream, so
  generic players (`ffplay`, VLC) can't read it directly. Strip the length and
  tag, or use the `serve` page.
- An idle simulator still produces AVCC frames: the last frame is re-encoded
  at `--fps` so a decoder never stalls on a stale delta.

## See also

[serve.md](../../serve.md) · [wire.md](../../wire.md) ·
[screenshot](../screenshot/README.md) · [recording](../recording/README.md)
