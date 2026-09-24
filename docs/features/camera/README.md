---
description: Feed a Mac webcam, a still image or a looping video into an iOS app's camera inside the simulator, from the serve page's camera card or its WebSocket. Use when testing barcode scanners, photo capture or camera viewfinders.
---

# Camera

Pipe a camera source into an iOS app's `AVCaptureVideoPreviewLayer`,
`AVCapturePhotoOutput`, and `UIImagePickerController` running inside
the simulator. The source can be a **live Mac webcam** (FaceTime HD,
USB, Continuity Camera), a **still image**, or a **looping video** —
the app sees it as if it were a real iOS camera — barcode scanners
scan, profile-photo uploads work, viewfinders fill — without opening
Xcode, without installing a separate menu-bar app. It works on a Mac
with no camera too: apps get a virtual capture device.

There's no CLI verb: the surface is the page's camera card and its
WebSocket, which agents can drive directly.

## Quick start

The app must be (re)launched **after** Start — the camera is injected
into apps at launch:

1. Open `/simulators/<UDID>` in `baguette serve`; in the sidebar's
   **Camera** disclosure pick a source (Webcam / Image / Video), a
   device or a file, and **Start**. Fit/Fill, Mirror and live FPS sit
   on the same card.
2. **Relaunch the target app** — tap its icon, `xcrun simctl launch <udid> <bundle-id>`,
   or `expo run:ios` (which launches via `simctl`). An app already running
   from *before* Start won't have the camera; a Metro JS reload doesn't
   re-exec, so relaunch the native process.
3. Open the camera screen — the app sees the virtual camera.

**Stop** disarms, so apps launched afterwards no longer load it.

## Workflow: inject into a single app

To inject into a single app without arming the whole sim (e.g. a launch
that bypasses launchd, like some Xcode Run configs),
`SIMCTL_CHILD_DYLD_INSERT_LIBRARIES` passes the dylib to one launch:

```
SIMCTL_CHILD_DYLD_INSERT_LIBRARIES="$HOME/Library/Application Support/Baguette/builds/<sha>/VirtualCamera.dylib" \
  xcrun simctl launch --terminate-running-process <udid> <bundle-id>
```

The dylib survives Metro/JS reloads; relaunch only when the native app
restarts.

## HTTP / WebSocket

The browser opens `ws://<host>:<port>/simulators/<udid>/camera` and
exchanges text frames.

**Browser → server:**

```json
{ "type": "camera_list" }
{ "type": "camera_start",
  "source": "webcam",          // "webcam" | "image" | "video"; default "webcam"
  "deviceUID": "0x14600000046d0825",  // required for webcam, ignored otherwise
  "fit": "fit",                // "fit" | "fill"
  "mirror": false }
{ "type": "camera_start", "source": "image", "fit": "fit", "mirror": false }
{ "type": "camera_start", "source": "video", "fit": "fill", "mirror": false }
{ "type": "camera_stop" }
{ "type": "camera_set_flags",
  "fit": "fill",
  "mirror": true }
```

For `image` / `video` there is **no path on the wire** — the browser
uploads the file first (see the route below) and the server resolves
the staged host file for this udid. A missing `source` defaults to
`webcam`, so pre-existing clients keep working.

**Server → browser:**

```json
{ "type": "camera_devices",
  "devices": [
    { "uid": "0x14600000046d0825",
      "name": "FaceTime HD Camera",
      "isDefault": true }
  ]
}
{ "type": "camera_state",
  "ok": true,
  "phase": "streaming",        // "idle" | "streaming"
  "fps": 29.97,
  "source": "webcam",          // "webcam" | "image" | "video" while streaming
  "device": "0x14600000046d0825" }  // present only for a webcam source
{ "type": "camera_state",
  "ok": false,
  "phase": "idle",
  "fps": 0,
  "error": "Camera access denied. Open System Settings → Privacy → Camera and enable baguette." }
```

### Uploading an image / video source

```
POST /simulators/:udid/camera-source?name=<filename>
     body = raw file bytes (application/octet-stream)
     → { "ok": true, "kind": "image" }   // or "video"
```

Accepts images (`png jpg jpeg gif heic heif`) and videos
(`mov mp4 m4v`); anything else is refused `415` before the body is
read, and a udid that isn't a known device is refused `404`. Unlike
`/files` (consumed synchronously by `simctl`), the bytes are staged
into a **persistent per-udid slot** because the camera WebSocket
streams them *later* — a new upload replaces the previous one, and the
slot is cleared when the camera socket closes. The browser never sends
a host path; `camera_start` just names the `source` kind and the
server reads the staged file.

Both halves of the staged path are treated as untrusted: `?name=` is
reduced to its last path component, and the udid must name a
`CameraSourceSlot` (letters, digits, `-`, `_`) before it becomes a
directory — the slot is replaced with a recursive delete on every
upload, and the udid arrives percent-decoded off the request path, so
an unchecked one could carry `..` out of the staging root.

`camera_devices` lands once on connect and again after every
`camera_list`. `camera_state` lands after every `camera_start` /
`camera_stop` / `camera_set_flags`.

## Gotchas

- **Relaunch after Start.** dyld honours `DYLD_INSERT_LIBRARIES` only
  at exec time; baguette doesn't reopen apps for you. If frames don't
  appear, terminate and relaunch the iOS app.
- **One camera at a time per host.** All simulators write
  `/tmp/SimCam.bgra`; the dylib reads whichever bytes landed last.
  The Server's camera WS doesn't reject a second concurrent start
  in v1 — the second one just trashes the first one's frames.
- **Video rotation isn't applied.** `VideoFileCapture` streams frames
  in their *encoded* orientation — a clip recorded with a rotation
  transform (many phone videos) plays sideways. Fitting and looping
  work; rotation correction is deferred.
- **No audio.** A video's audio track is ignored — the camera path
  carries frames only.
- **Verified on iOS 26 with expo-camera 57.** On a camera-less Mac the
  app gets a mocked capture graph; a future iOS that reads a different
  private format accessor could crash the target app until it's shimmed.
- **No metadata/barcode delivery from the virtual camera.** Frames reach
  `AVCaptureVideoDataOutput` and the preview, but `AVCaptureMetadataOutput`
  isn't fed synthesized barcode objects — an app that scans via metadata
  output sees the camera but won't detect a code.
- **Shares `DYLD_INSERT_LIBRARIES` with [motion](../motion/README.md).**
  Starting the camera while motion is armed keeps both loaded; stopping
  either leaves the other alone. A dylib you armed by hand is preserved.

## See also

- [design.md](design.md) — the Mac/simulator halves, the shared frame buffer, the hooks, the capture-graph mock and iOS 26 dylib gotchas
- [Motion](../motion/README.md) · [File upload](../file-upload/README.md)
