---
description: How baguette's one-shot screenshot captures a single IOSurface, why it isn't "stream + read one frame", the JPEG hop behind the PNG routes, and how the bezel composite is layered and sized.
---

# Screenshot — design

## Path

- `baguette screenshot`, `GET …/screenshot.{jpg,png}` and
  `GET …/screenshot-bezel.png` share one capture helper,
  `ScreenSnapshot.capture` → SimulatorKit `Screen` (framebuffer callbacks) →
  the first `IOSurface`.
- Sizing goes through `CaptureSize.plan` (pure Domain, unit-covered) and
  `CaptureCanvas` (CoreGraphics); only the CoreGraphics and
  `CGImageDestination` calls are integration-only.

## Why

`baguette serve` already streams via WebSocket and accepts `snapshot`
as an inline verb on that channel, but two real workflows wanted a
plain HTTP fetch:

- **Browser cache-busting** — `<img src="…/screenshot.jpg?t=…">` with
  a rotating timestamp is the simplest possible "refresh on demand"
  affordance for review tools and dashboards. No WS plumbing needed
  in the embedding page.
- **CLI / CI** — `curl -o shot.jpg …` and `baguette screenshot --output
  shot.jpg` drop into shell pipelines, golden-image diffs, and bug
  reports without spinning up a stream session.

The endpoint name and content-type match what every browser already
expects from an `<img>` tag — no new client code path on the page.

Three later requests reshaped it:

- **A lossless container.** JPEG is the right default for a dashboard
  thumbnail and the wrong one for anything that gets composited,
  annotated, or re-saved: every round trip through it adds another
  layer of 8×8 block artefacts. PNG stops the *further* bleeding — see
  [the JPEG hop](#the-jpeg-hop-behind-the-png-routes) still in the capture path.
- **A size that means something.** `--scale 2` answers "half of
  whatever the device is", which nobody's App Store submission asks
  for. `--size appstore-6.9` answers the question people actually
  have.
- **The bezel, without a browser.** The device-farm wall composites
  DeviceKit chrome around each tile, and that composite is what people
  want to paste into a PR. Getting it used to mean opening a page,
  taking a screenshot, and cropping it.

## Pipeline

```
ScreenSnapshot.capture(screen, quality, scale, timeout)
   1. open SimulatorKit Screen (registers framebuffer callbacks)
   2. await first IOSurface delivered to the @Sendable callback
        ─ first-claim wins:           timer fires    → throw .timeout
                                      callback fires → encode + return
                                      start() throws → propagate error
   3. if scale ≥ 2: Scaler.downscale → CVPixelBuffer
      else:         use IOSurface zero-copy
   4. size ≠ native → CaptureCanvas
        placement = size.plan(source, fit)
        if placement.isIdentity(for: source) → skip, keep the bytes
        else CoreGraphics: fill background, draw at the plan's rect
   5. bezel route → composite DeviceKit chrome around it first
   6. JPEGEncoder / PNGEncoder → Data
   7. defer { screen.stop() }
```

The `SnapshotSession` actor-of-sorts (`@unchecked Sendable` holder)
owns the encoder, scaler, and a single-shot `claim()` flag. Three
producers race for the flag — the timeout timer, the frame callback,
and the `screen.start()` throw path — and only the first wins, so the
continuation can never resume twice.

The same helper drives both the HTTP routes and the CLI; quality /
scale / size / fit / background defaults match between them so tooling
that calls one sees the same bytes as tooling that calls the other.

`CaptureCanvas` is the CoreGraphics half of the size vocabulary: given
a `CapturePlacement` from `CaptureSize.plan`, it allocates the target
bitmap, fills the background, and draws the source at the planned
rect. Under `cover` the planned origin is negative, so the draw simply
overflows the context and the overflow is the crop — no separate crop
path. `contain` letterboxes onto the background colour, `stretch`
draws to the full canvas.

The identity check earns its keep: at `--size native` (the default)
the placement is a no-op, `CaptureCanvas` is skipped entirely, and the
encoded bytes are exactly what they were before any of this existed.
A frame is never decoded and re-encoded just to be told it was already
the right size.

`--scale` and `--size` compose in that order: scale reduces what came
off the framebuffer, then the size vocabulary resolves against the
*scaled* frame. `--scale 2 --size square` squares up the half-size
frame; it does not square up the device and then halve it.

## The JPEG hop behind the PNG routes

`--quality` has no effect on a PNG from the CLI. The HTTP PNG routes do still
accept `?quality=`, but it governs the **JPEG intermediate** the capture
pipeline produces, not the delivered PNG: `ScreenSnapshot` encodes JPEG
unconditionally, and the PNG routes decode that back to a `CGImage` before
re-encoding. It defaults to `1.0` there (against `0.85` on `screenshot.jpg`),
so a PNG is near-lossless out of the box — but not bit-exact. Removing the
round trip means teaching the capture helper to hand back a `CGImage` rather
than `Data`; it hasn't landed.

`quality` is whatever `kCGImageDestinationLossyCompressionQuality` clamps it
to (effectively `[0, 1]`).

Over HTTP there is no `jpeg` alias: the extension *is* the format, and
`screenshot.jpg` / `screenshot.png` are two literal routes rather than one
route with a parameter — so an `<img src>` and a `curl -O` both get the right
thing for free. A browser picks its decoder off the URL extension and nothing
else, which is the entire reason the second registration exists.

## Why a separate path, not "stream + read one frame"?

Three reasons:

1. **No WS handshake.** The HTTP route is a single GET; embedding pages
   and curl scripts don't need to know how to speak the binary frame
   format or the JSON control verbs.
2. **No reconfig churn.** A streaming session would have to be opened,
   asked to emit a snapshot, then closed — which on a busy simulator
   means waiting for the next encoder seam. The one-shot path bypasses
   the encoder entirely; it just grabs the next IOSurface that
   SimulatorKit hands over.
3. **No live-stream interference.** A snapshot grabbed via the WS
   `snapshot` verb shares the live encoder pacing (`StreamConfig.fps`,
   `scale`). The HTTP screenshot ignores both — `?scale=`, `?quality=`,
   and `?size=` only affect the returned image, never the live stream.

`?quality` and `?scale` mirror the WS knobs deliberately so callers
can pick the same trade-off they're used to from the streaming path;
`?size` / `?fit` / `?background` mirror the CLI flags and the browser
picker instead, because a size is a property of the artefact you're
producing, not of the stream you're watching.

## The bezel route

`screenshot-bezel.png` composites the DeviceKit chrome the farm wall
and the live view already draw:

```
DeviceChrome composite       ← underneath
   clip(innerCornerRadius)
     framebuffer, cover-fitted into the cutout
```

Same z-order as everywhere else in baguette, for the same reason: the
composite artwork paints an opaque dark "off-glass" tint inside the
screen rect, authored to sit *under* live content. The framebuffer is
**cover**-fitted into the cutout, so a device whose capture aspect
doesn't quite match its chrome crops a hair rather than stretching —
a distorted screenshot inside a correct bezel looks broken in a way a
1-pixel crop does not.

It is PNG-only, and that is not an oversight: the device body has
rounded, transparent corners, and JPEG has nowhere to put them —
every composite would arrive already flattened onto a rectangle. `?size=` / `?fit=` / `?background=` then apply to the
composited image, so `?size=square&background=ffffff` gives you the
bezelled device centred on a white square — which is the actual
marketing shot, in one GET, without a browser.

**The composite is sized off the framebuffer, not off the chrome.**
DeviceKit geometry is in 1× points; the captured frame is in device
pixels. Sizing the canvas from the chrome would throw away most of the
capture, so it goes the other way — the canvas takes the capture's
resolution and the chrome is resampled up to meet it. An iPhone 17 Pro
Max asked for `screenshot-bezel.png` with no parameters comes back at
1483 × 2984, not the chrome's ~494 × 995. It never drops below 1×
either, so a heavy `?scale=` shrinks the screen content but not the
bezel around it.

A device with no DeviceKit artwork gets a `404`, not an invented grey
rectangle. See [chrome-bezel](../chrome-bezel/README.md) for which devices
ship chrome.

## In the browser

Every capture surface in the web UI — the legacy stream sidebar, the
focus-mode toolbar, and the device-farm focus pane — mounts the same
size chip (`CaptureSizeMenu`) beside its Screenshot button, and each
remembers its own selection in `localStorage`. A capture then takes
one of two routes to a file:

- **`CaptureGallery`** fetches the screenshot over HTTP and forwards
  the picker's `?size=&fit=&background=` verbatim, so the server does
  the resize. Each thumbnail records the dimensions it actually came
  back at, and the download filename carries the size slug.
- **The composite path** paints locally through `CaptureComposer` when
  the bezel is wanted, because the bezel image is already decoded on
  the page and re-fetching it server-side would be slower and no more
  correct.

Both end up at the same pixels, because both plan through the same
`CaptureSize`. The picker's "Include bezel" checkbox is what chooses
between them; it is hidden on surfaces where a bezel is meaningless
(the 3D stage already contains a device).

## Timeouts

`ScreenSnapshot.capture` takes a `timeout: TimeInterval = 2.0`. Two
real failure modes it guards against:

- **Idle simulator** — SimulatorKit only fires the framebuffer callback
  on a frame change. A simulator booted but quiescent (lock screen
  with no clock tick visible, headless test runner waiting on input)
  may not emit a frame for several seconds. The timeout converts that
  into a clean 500 / `Failure.timeout` instead of a hanging request.
- **Wedged GPU pipe** — pre-iOS-26 simulators occasionally lose their
  framebuffer descriptor mid-session. Without the timeout the await
  is unbounded.

The HTTP layer translates everything to `application/json` error
envelopes; the CLI exits non-zero with the underlying message logged.

A request that has to wait the full 2 s for the timeout pins one Hummingbird
request task. Not a problem at human-scale request rates; would matter under
heavy scripted polling.

## Not built yet

- **Region capture.** A `?rect=x,y,w,h` query param + a one-line
  `CGImage.cropping(to:)` would let dashboards grab just the status
  bar or a known UI region without a server-side composite step. Note
  this is a genuinely different axis from `?size=`: one selects part
  of the source, the other shapes the destination.
- **A bezelled JPEG, on an opaque background.** The bezel route is PNG
  because chrome has alpha — but a solid `?background=` already
  flattens it. Honouring the bezel composite on `screenshot.jpg` when
  a solid background is given would give thumbnail-heavy pages a
  cheaper bezelled image than PNG.
- **A bezel on the CLI.** `baguette screenshot --bezel` would want the
  same composite the route does; the reason it doesn't exist yet is
  that the chrome rasterization currently lives on the server side of
  the split, not that it's hard.
- **A JPEG-free PNG path.** `ScreenSnapshot` returns encoded `Data`,
  which forces the JPEG hop above. Returning a `CGImage` and letting
  each caller choose its encoder would make `screenshot.png` genuinely
  bit-exact and would save the bezel route a decode as well.
- **WebP / AVIF.** The `CGImageDestination` switch is a one-line
  format string; smaller payloads at the same visual quality matter
  for thumbnail-heavy pages like `/farm`.
