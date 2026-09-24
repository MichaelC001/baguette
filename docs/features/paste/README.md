---
description: Move text and images between the host Mac's clipboard and the simulator's pasteboard, and paste any unicode into the focused field. Use when typing emoji, accents or non-Latin text, or copying something out of the simulator.
---

# Paste & clipboard

Move text and images between the host Mac and the booted simulator's
pasteboard. Pasting **into** the sim is the path around `type`'s
US-ASCII keystroke limit, so emoji, accents, and non-Latin scripts all
land intact; copying **out** of the sim ferries whatever it last
copied onto the host Mac's clipboard. Every flag:
[commands.md#baguette-paste](../../commands.md#baguette-paste) ·
[commands.md#baguette-clipboard](../../commands.md#baguette-clipboard).

## Quick start

```bash
baguette paste --udid <UDID> --text "héllo 🥖"          # set the pasteboard, then Cmd+V
baguette paste --udid <UDID> --text "x" --no-press      # set only, for apps that read UIPasteboard
baguette clipboard get  --udid <UDID>                   # print the sim's pasteboard text
baguette clipboard copy --udid <UDID>                   # sim → host Mac, images included
```

`baguette clipboard sync --udid <UDID>` goes the other way: host Mac →
sim, **full-fidelity, images included**. `clipboard get` pipes
byte-faithfully, like `pbpaste`; `clipboard copy` is a pure ferry, no
keystroke.

On the `serve` page, with the device screen focused:

- **Cmd+V** (or Ctrl+V) pastes the host clipboard's text into the sim.
- **Cmd+C** (or Ctrl+C) copies the focused field's selection sim-side
  and lands it on the host Mac's clipboard.

No permission prompts: the paste reads the browser's own paste event,
and copy syncs host-side instead of using the Clipboard API, so both
work over plain LAN http.

## Why a pasteboard, not keystrokes

Forwarding Cmd+V as a raw key chord makes iOS paste **its own, empty
pasteboard** — nothing in the stream pipeline syncs the host clipboard
the way Simulator.app does. `paste` closes the loop server-side: put
the text on the sim's pasteboard first, then press Cmd+V.

## Wire (`baguette input` / stream WebSocket)

Envelope framing: [wire.md](../../wire.md).

```json
{ "type": "paste", "text": "héllo 🥖 — any unicode" }
{ "type": "paste", "text": "clipboard only", "press": false }
{ "type": "copy" }
{ "type": "copy", "press": false }
```

- `paste.text` — required. Any unicode; UTF-8 on the wire.
- `paste.press` — optional bool, default `true`. When true, Cmd+V is
  pressed after the pasteboard is set (the set must succeed first —
  a failed set never fires the keystroke). `false` = set-only.
- `copy.press` — optional bool, default `true`. When true, Cmd+C is
  pressed sim-side (so the focused field copies its selection) before
  the pasteboard is ferried onto the host Mac. `false` = ferry-only
  (whatever the sim already holds, no keystroke).

Acks: on `baguette input`, the usual one-line `{"ok":true}` /
`{"ok":false,"error":"…"}`. On the stream WS, a typed reply frame
(like `describe_ui_result`) so the browser's text-frame router can
claim it:

```json
{ "type": "paste_result", "ok": true }
{ "type": "paste_result", "ok": false, "error": "xcrun simctl pasteboard command exited 1" }
{ "type": "copy_result", "ok": true }
{ "type": "copy_result", "ok": false, "error": "xcrun simctl pasteboard command exited 1" }
```

## Gotchas

- **Paste wire verb is text-only.** For images, copy on the host Mac
  and run `baguette clipboard sync` — full-fidelity host→sim. Pasting
  image *bytes* from the browser's clipboard is a follow-up.
- **Copy's settle is a fixed ~200 ms.** Cmd+C presses sim-side, then
  after a fixed beat the pasteboard is read back — long enough in
  practice, but a very sluggish guest could be read before it finishes
  copying (stale content). The CLI `clipboard copy` and wire
  `press:false` sidestep this entirely (pure ferry, no keystroke).
- **Copy only helps views that honor hardware Cmd+C.** Editable text
  fields copy their selection; a non-editable / no-selection view
  makes Cmd+C a no-op, so `copy` just ferries whatever the pasteboard
  already holds.
- **Browser copy targets the server's Mac.** The copy lands on the
  clipboard of the machine running baguette. Local dev (browser on
  that same Mac) is the happy path; a remote browser's Cmd+C lands on
  the server, not the viewer's clipboard.
- **Needs a booted device** — the pasteboard commands exit non-zero on
  a shutdown sim and the error surfaces in the ack.
- **Safari paste-event caveat.** Chrome/Firefox fire `paste` with focus
  on the non-editable screen; a Safari version may not.

## See also

- [design.md](design.md) — dispatch path, the Xcode 27 `pbcopy` fallback, ordering and browser capture
- [Keyboard](../keyboard/README.md)
