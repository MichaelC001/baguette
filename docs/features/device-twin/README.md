---
description: Mirror a real, cable-free iPhone into baguette beside the simulators — live screen over Wi-Fi and a 3D twin that turns with the phone's gyroscope (preview, view-only). Use when you want a physical device on the same page as your simulators.
---

# Device twin — a physical iPhone in baguette

A real iPhone appears in baguette the way a simulator does: listed beside the
simulators, its live screen mirrored into the browser, and the 3D stage driven
by the phone's own gyroscope — the model on the monitor rotates in lockstep
with the phone in your hand, live screen texture-mapped onto its display.

**Status: preview, view-only.** The mirror and the gyro twin work end-to-end
against real hardware. Control (clicking the twin's screen to tap the real
phone) is not wired yet.

## Quick start

1. **Build the companion.** `Companion/DeviceTwin/` is a Tuist project: run
   `tuist generate` there, open the workspace, set your Team under Signing &
   Capabilities on every target (confirm App Groups lists
   `group.com.tddworks.baguette.twin`), and run it on the phone.
2. **Serve on the LAN.** The phone connects to the Mac over Wi-Fi, so bind to
   an interface it can reach:
   ```bash
   baguette serve --host 0.0.0.0
   ```
3. **Pair.** In the companion app, enter the Mac's `address:port`, save it,
   test the connection (accept the Local Network prompt), then start the
   broadcast from the picker.
4. **Watch.** The phone shows up in the **DEVICES** section of the list page,
   between RUNNING and AVAILABLE. Open it — `/devices/<id>` — for the same page
   a simulator gets, reduced to view-only (a "DEVICE · view-only" badge; no
   control, boot or orientation).

`baguette serve`'s flags: [commands.md#baguette-serve](../../commands.md#baguette-serve).

## Workflows

### Pick a bezel and a 3D model

Real hardware has no DeviceKit chrome bundle on the Mac, so the 2D page
borrows one: it offers a picker (simulator device names plus an evergreen set),
and the pick is stored per device.

The 3D twin matches a model by the phone's hardware id (`utsname.machine`,
e.g. `iPhone14,3`). When nothing matches, baguette doesn't substitute a
look-alike — the page offers the installed models as a picker and remembers
the pick per device. The bundled definitions declare no hardware ids yet, so
expect the picker.

### Re-zero the twin

The twin is absolute against gravity: lay the phone on the desk and the model
lies on the stage. Only the compass heading is arbitrary; it's calibrated at
connect and whenever you press **Re-zero**. Use it when the twin has drifted in
yaw.

## HTTP / WebSocket

```text
GET  /devices.json                     connected companions
GET  /devices/:udid                    the unified page (sim.html)
GET  /devices/:udid/3d-model.json      matched model, or choices
GET  /devices/:udid/definition.json    SDK bootstrap, ?chrome=name (required)
GET  /devices/:udid/chrome/:name/…     borrowed bezel + button PNGs
WS   /devices/:udid/companion/video    that device's video ingest
WS   /devices/:udid/companion/motion   its attitude ingest
WS   /devices/:udid/stream?format=     mirror stream, mjpeg|avcc
WS   /devices/:udid/stream.3d.<fmt>    3D twin stage, mjpeg|avcc; ?model=<id> picks the model
```

The UDID is always in the path, companion sockets included. The stream
sockets take the same control lines as a simulator's (`set_fps` / `set_scale`
/ `set_bitrate` / `force_idr` / `snapshot`, see [wire.md](../../wire.md)); on
an H.264 mirror `set_fps`, `set_bitrate` and `force_idr` are accepted and
ignored — the encoder lives on the phone. Gestures are rejected, loudly:

```json
{"ok":false,"error":"device control is not wired yet"}
```

### Companion sockets (phone → host)

Both sockets open with a `hello`; a hello claiming a different udid from the
path is rejected.

```json
{"type":"hello","udid":"…","name":"My iPhone","model":"iPhone14,3","capabilities":["screen"]}
```

The motion socket then carries attitude samples — quaternion order is
**`[x, y, z, w]`, CoreMotion's own**; `t` is the sample timestamp:

```json
{"type":"attitude","q":[0.012,-0.221,0.003,0.975],"t":163412.041}
```

The video socket carries one `format` frame, then binary AVCC chunks
(`[length][tag][payload]`: a stream description, then key/delta frames).
`orientation` is `portrait | portrait-upside-down | landscape-left |
landscape-right`:

```json
{"type":"format","width":1170,"height":2532,"orientation":"portrait","codec":"avcc"}
```

Malformed lines throw rather than being dropped — a silent drop would leave
the twin frozen with no explanation.

## Gotchas

- **The broadcast is yours to start.** The host cannot start or restart it.
  If the mirror stops, restart it on the phone. iOS shows the red recording
  indicator throughout.
- **Mirror latency** is capture → encode → Wi-Fi → decode → render ≈
  150–300 ms. Fine for a mirror.
- **Yaw drifts** over minutes (the reference frame has no compass); press
  **Re-zero**.
- **DRM'd content blanks** in the capture; nothing to do about it.
- **LAN browsers get MJPEG, not H.264.** WebCodecs needs a secure context;
  `localhost` is one, a LAN address over plain HTTP isn't (issue #71).
- **A connected but unwatched phone costs the host nothing**; after the first
  viewer attaches, video can take up to one keyframe interval (~2 s) to appear.
- **Not in the farm view**, as with the simulator 3D stage.

## See also

- [design.md](design.md) — the three pipes, the decision record, gyro-twin principles, performance model
- [3d-rendering](../3d-rendering/README.md) · [motion](../motion/README.md) · [companion-screens](../companion-screens/README.md)
