---
description: The browser-side Baguette JS SDK — Baguette.use() and sim.mount() turn a simulator's definition.json into an interactive bezel, screen and buttons. Use when building a web page that drives a simulator served by baguette serve.
---

# Baguette JS SDK

The **browser-side library** behind every `baguette serve` page that drives a
simulator. A consumer page calls `Baguette.use(...)` and `sim.mount(...)`;
everything else — bezel, screen, buttons, pointer gestures, wire envelopes —
is internal. It is served by [`baguette serve`](../../commands.md#baguette-serve).

## Quick start — the entire public surface

```js
import { Baguette } from '/baguette/baguette.js';   // or window.Baguette

// "I want to use this iPhone simulator."
const sim = await Baguette.use({
  host: location.origin,      // baguette server origin
  udid: '...',                // simulator UDID
  send: (payload) => ws.send(JSON.stringify(payload)),  // wire sink
  log: (msg, isErr) => { ... },
});

// "Make it interactive."
sim.mount(document.getElementById('host'));

// Drive the model directly (advanced — same wire envelopes the
// gesture interpreter emits, type-safe, no JSON):
sim.screen.tap({ x: 100, y: 200 });
sim.screen.swipe({ from, to, duration: 0.25 });
sim.buttons[0].press({ hold: 1.5 });
sim.button('powerButton').press({ hold: 1.5 });    // by id

// Cleanup
sim.detach();
```

That's the whole consumer surface. No wire envelopes, no JSON shapes, no DOM
math, no `kind:` discriminators. Adding a new device family doesn't change one
line of the page code that calls this.

**The SDK never opens its own WebSocket.** The page owns the transport
lifecycle (it already needs the socket for frame streaming) and hands its
`send(payload)` callback to `Baguette.use`. What `send` receives is the gesture
wire documented in [wire.md](../../wire.md).

## How a page and the SDK talk

```
Consumer page                Baguette SDK                       Baguette server
─────────────────            ─────────────────                   ───────────────
                                                                /simulators/<udid>/definition.json
const sim = await    ──fetch──>                       ────GET───>     │
  Baguette.use({...})                                                  │
                              new Simulator(def, ...) <───JSON─────────┘
                                creates parts:
                                 • Screen
                                 • Button × N
                                 • Crown?, Keyboard?

sim.mount(container) ──────── Bezel.mount renders                ws://.../stream
                              Screen.bindDOM attaches            (page-owned WS)
                              PointerInterpreter                        ▲
                              Button.mount × N                          │
                                                                        │
user clicks power button ──── Button.press({hold: 1.5})                 │
                                ↓                                       │
                              transport.button(envelope, ...)           │
                                ↓                                       │
                              send({type:"button",button:"power", ──────┘
                                    duration: 1.5})
```

## HTTP — `GET /simulators/<UDID>/definition.json`

The SDK's first call: a per-simulator description of which parts the
simulator has, computed by Swift from the device's `chrome.json` plus
identity.

```json
{
  "identity": {
    "udid":  "1234-...",
    "name":  "iPhone 17 Pro",
    "model": "iPhone 17 Pro"
  },
  "screen": {
    "viewport":   { "width": 436, "height": 906 },
    "rect":       { "x": 22, "y": 22, "width": 392, "height": 862 },
    "clipRadius": 56,
    "bezelImage": {
      "rest": "/simulators/1234-.../bezel.png",
      "bare": "/simulators/1234-.../bezel.png?buttons=false"
    }
  },
  "buttons": [
    {
      "id":       "powerButton",
      "envelope": { "type": "button", "button": "power" },
      "images":   {
        "rest":    "/simulators/1234-.../chrome-button/powerButton.png",
        "pressed": "/simulators/1234-.../chrome-button/powerButton-down.png"
      },
      "z": "below"
    },
    { "id": "volumeUp", "envelope": {"type":"button","button":"volume-up"}, ... }
  ]
}
```

Optional fields arrive on devices that have them:

- `"crown": { ... }` — Apple Watch's Digital Crown (rotary + click)
- `"keyboard": { ... }` — software keyboard input
- `"remote": { ... }` — Apple TV's Siri Remote (future)

**No `kind:` tagged union.** Parts are member fields: the SDK constructs a
`Crown` part if `def.crown` is present, a `Keyboard` part if `def.keyboard` is
present, otherwise skips. Watch's Digital Crown is its own class with
`rotate()` + `click()` — never confused with a press button.

## Gotchas

- **Apple Watch's crown and Apple TV's remote aren't there yet.** The crown
  part and the remote part are planned; today's parts are bezel, screen,
  buttons and keyboard.
- **Pages that have their own canvas** (the farm tile) don't call
  `Baguette.use`; they assemble the SDK's parts — transport, screen,
  keyboard — by hand.

## See also

- [design.md](design.md) — the device / parts / behaviours model and why it isn't data-driven UI
- [chrome-bezel](../chrome-bezel/README.md) — where the bezel and button images come from
- [wire.md](../../wire.md) — the envelopes `send` receives
