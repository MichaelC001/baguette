---
description: Record a simulator to video, either the live view as you see it (bezel, pinch dots) from the browser's Record button, or the raw framebuffer to H.264 .mp4/.mov with baguette record. Use for bug-report clips, App Store previews or CI video artefacts.
---

# Recording

Video capture of a simulator, from two places that answer two different
questions:

- **In the browser**: the live view exactly as you see it (bezel + screen +
  pinch overlay) to an MP4 or WebM file.
- **`baguette record`**: a headless CLI verb that writes H.264 video (`.mp4` or
  `.mov`) of the raw framebuffer, for CI and scripted capture where no browser is
  involved. Every flag: [commands.md#baguette-record](../../commands.md#baguette-record).

Both take an output size from the shared [capture size](../capture-size/README.md)
vocabulary, so `--size appstore-6.9` on the command line and "App Store 6.9″" in
the toolbar picker mean the same pixels.

## Quick start

```bash
baguette record --udid <UDID> --output demo.mp4 --duration 10
baguette record --udid <UDID> --output hero.mp4 --size appstore-6.9
baguette record --udid <UDID> --output demo.mov --fps 60     # Ctrl-C to stop
```

In the browser (`baguette serve`): press **Record** in the focus-mode toolbar,
the stream sidebar, or the device-farm focus pane; press again to stop. Pick the
size with the size chip beside it first.

## `baguette record`

- **Container = extension.** There is no `--format`; an unrecognised extension is
  a validation error (`Unknown recording container 'webm'. Expected one of: mp4 | mov`).
  There's no stdout path either: the writer needs a seekable file.
- **Stopping.** `--duration` elapsing and Ctrl-C do the same thing, whichever
  comes first: flush and close. An interrupted recording is a playable file
  (`kill -9` is not, and can't be).
- **Output.** H.264, High profile, a keyframe every 2 s. On success one line goes
  to **stderr**, so `--output` stays the only thing that touches your data:
  `Recorded 152 frames · 5.03s · 2796×2796 → /tmp/r.mp4`.
- **The size resolves against the first frame**, since the simulator's frame
  dimensions aren't known until one arrives, and holds for the take.
- **Even dimensions, always.** H.264 4:2:0 wants even width and height, so the
  canvas is rounded **up** and the frame re-centred; never stretched.
- **`--background` is `#RRGGBB` only.** `transparent` is rejected at
  argument-parse time: MP4 has no alpha. (Screenshots quietly mat white instead;
  a still is cheap to redo, a ten-second take is not.)

### An idle simulator records nothing

The simulator delivers a frame **when the screen changes**, not on a clock.
`--fps` is a ceiling enforced by dropping frames, never by duplicating one, so a
quiet stretch mid-recording just holds the last frame. A device nobody drives
delivers *zero* frames, and there's no video of no frames, so the command exits
non-zero:

```
No frames captured — the simulator screen never changed.
Drive some input while recording.
```

Drive some input while recording. It's the same quiescence that makes
`screenshot` need a 2-second timeout.

## In the browser

- **Where:** the focus-mode (native) toolbar, beside the size chip, shows an
  elapsed `mm:ss` readout while running; finished clips collect in a dock of
  download links. The stream sidebar lists them as download links too. The
  device-farm focus pane has its own Record button and size picker.
- **One size choice per view.** Capture and Record share the picker, so a
  screenshot and a clip taken a second apart come out at the same dimensions.
  The focus-mode view and the sidebar remember separate selections.
- **"Include bezel"** in the picker decides whether the device frame is drawn.
- **The size is locked when you press Record.** Changing the picker takes effect
  on the *next* recording.
- **Filenames carry the size**, so a folder of clips says what each one is:
  `iPhone_17_Pro-<stamp>-appstore-6.9-1290x2796.mp4`, or
  `<device>-<stamp>-1206x2622.mp4` at native size. A ratio lands as
  `16-9-4971x2796` (a colon shows as a slash in Finder).
- **Stopping for you.** An in-flight recording is cancelled when you flip 2D↔3D,
  when the stream restarts (a codec swap), and on page unload.

| Browser | Container |
| --- | --- |
| Chrome 113+ | MP4 (H.264) or WebM (VP9) |
| Safari 14.1+ | MP4 (H.264) |
| Firefox | WebM (VP9 / VP8); no MP4 muxer |
| Older / strict CSP | The Record button hides itself when `MediaRecorder` is unavailable |

## Recording the 3D stage

With the 3D view open, Record captures the rendered device, with no DeviceKit
bezel around it (that would draw a phone around a phone). The size vocabulary
applies unchanged, but the **fit is picked for you**: the 3D canvas is a
viewport onto a scene, a device in the middle of empty margins, so letterboxing
it into a tall App Store size would shrink the device into the emptiness.

- **`cover`** when the target is narrower than the stage: side margins are
  cropped, full height kept.
- **`contain`** when the target is wider: past that point cropping would cut
  into the device, so you get bars instead.

From a 1600 × 1250 stage:

| Size | Fit | Kept from the stage |
| --- | --- | --- |
| `appstore-6.9` | cover | 577 × 1250 — full height, sides cropped |
| `square` | cover | 1250 × 1250 |
| `9:16` | cover | 703 × 1250 |
| `16:9` | contain | letterboxed, the phone intact |

Picking a size also raises the 3D stream's density so the crop has pixels to
spare ([3D rendering](../3d-rendering/README.md)). In 2D your own fit choice
stands. 3D *screenshots* don't need any of this: they re-render at the exact size.

## HTTP / WebSocket

None. The browser recorder records in the page from the stream it already has;
`baguette record` isn't wired into `baguette serve`: no route, no WS verb.

## Gotchas

- **Don't run `baguette record` on a device a browser is streaming** if you care
  about that browser's smoothness: you get a good recording and a choppier live
  view.
- **`baguette record` records the framebuffer, not the view.** No bezel, no pinch
  overlay, no cursor; if you want the composite, record in the browser.
- **No audio.**
- **Single taps don't show** in a browser recording: only pinch / 2-finger
  gestures draw dots.
- **Long browser recordings live in RAM** until Stop. Multi-minute at 1080p is
  fine; multi-hour is not. `baguette record` writes to disk as it goes.
- **The size is fixed for the whole clip.** Rotating mid-recording letterboxes
  rather than resizing, so a portrait→landscape clip is framed for whichever came
  first.
- **Recording starts on a dark screen** if you press Record before the stream's
  first frame: the bezel paints, the screen fills in when frames arrive.
- **Nothing trims.** `--duration` is a stop condition, not an edit.

## See also

[design.md](design.md): why the browser composites client-side, why
`baguette record` is server-side, and the paint pipeline ·
[capture size](../capture-size/README.md) · [screenshot](../screenshot/README.md) ·
[3D rendering](../3d-rendering/README.md) · [device farm](../device-farm/README.md)
