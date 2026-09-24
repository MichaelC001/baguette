---
description: How describe-ui talks to the simulator's AX server from outside Simulator.app — the AXPTranslator bridge-token dispatcher, the per-call token dance, and the host-window-to-device-point projection. Read before touching accessibility.
---

# Accessibility — design

## Path

```
CLI / WS  →  Simulator.accessibility()  →  Accessibility     
                                                    │
                                                    ▼
                                  AXPTranslatorAccessibility
                                  (Infrastructure/Accessibility/)
                                                    │
                            sets up TokenDispatcher │ as the translator's
                            bridgeTokenDelegate     │ (one-time, process-wide)
                                                    ▼
                          AXPTranslator (sharedInstance)
                                                    │
                            per-call: register UUID │ token → SimDevice;
                            translator's XPC requests│ flow back through
                            the dispatcher's block;  │ block invokes
                            SimDevice.sendAccessibilityRequestAsync
                                                    ▼
                                           in-simulator AX server
```

Cribbed from `cameroncooke/AXe` and
`Silbercue/SilbercueSwift`'s `AXPBridge.swift` — the only public
Swift implementations of the iOS-26 / Xcode 26 dispatcher pattern
we found.

### Why the dispatcher is the trick

`AXPTranslator` is a process-wide singleton in
`AccessibilityPlatformTranslation.framework`. Inside Simulator.app
its `bridgeTokenDelegate` is wired up by `SimulatorKit.SimAccessibilityManager`
when a display view is added per simulator. Out of Simulator.app —
which is where `baguette` runs — the delegate is `nil`, and every
`-frontmostApplicationWithDisplayId:bridgeDelegateToken:` call
returns `nil` because the translator has no idea where to send its
XPC requests.

The fix: install our own `bridgeTokenDelegate` (the
`TokenDispatcher` class). It implements three `@objc dynamic`
methods that AXPTranslator looks up:

- `-accessibilityTranslationDelegateBridgeCallbackWithToken:` —
  returns a **block** `(AXPTranslatorRequest) -> AXPTranslatorResponse`
  that routes the request to the right `SimDevice` via
  `-sendAccessibilityRequestAsync:completionQueue:completionHandler:`.
- `-accessibilityTranslationConvertPlatformFrameToSystem:withToken:` —
  identity transform; we re-project later when we have the AX root.
- `-accessibilityTranslationRootParentWithToken:` — `nil`.

`@objc dynamic` and `NSObject` subclassing are mandatory because
AXP invokes the delegate via ObjC dispatch.

### Per-call dance

```
1. Token = UUID().uuidString
2. dispatcher.register(device: simDevice, token, deadline)
3. translation = translator.frontmostApplicationWithDisplayId:0
                                          bridgeDelegateToken:token
4. translation.bridgeDelegateToken = token   ← critical, see below
5. root = translator.macPlatformElementFromTranslation:translation
6. root.translation.bridgeDelegateToken = token
7. walk root.accessibilityChildren, stamping the token onto each
   child's `translation` sub-property
8. dispatcher.unregister(token)
```

Step 4 is the single most important thing. The translator stores
the token internally, but it re-reads `bridgeDelegateToken` from
**every translation object** it touches — if a child object was
returned by AXP without our token stamped on it, the next sub-XPC
silently fails.

## Coordinates

`AXPTranslator` reports `accessibilityFrame` in **macOS host-window**
coordinates — i.e. where Simulator.app's window would put that
button on the host screen. To project to device points we read
`SimDevice.deviceType.mainScreenSize` (pixels) and
`mainScreenScale`, divide one by the other to get the logical
point size, and apply:

```
scale   = pointSize.width / rootFrame.width
yOffset = (pointSize.height - rootFrame.height * scale) / 2
out.x   = (mac.x - rootFrame.x) * scale
out.y   = (mac.y - rootFrame.y) * scale + yOffset
out.w   = mac.width  * scale
out.h   = mac.height * scale
```

Width-based uniform scale + vertical centring matches Simulator.app's
own letterbox behaviour for tall devices on a short window. The
output is in the same device-point space the gesture wire uses, so
`tap` / `swipe` envelopes can consume the frame directly.

## Adding a field

The mapping from `AXPMacPlatformElement` properties to `AXNode` fields
lives in the adapter's walk; a property that returns a
non-string/bool/CGRect type needs a typed
`class_getMethodImplementation` cast like the frame reader does.

## References

- [Silbercue/SilbercueSwift `AXPBridge.swift`](https://github.com/Silbercue/SilbercueSwift/blob/main/SilbercueSwiftMCP/Sources/SilbercueSwiftCore/AXPBridge.swift)
  — the source of the dispatcher pattern.
- [cameroncooke/AXe](https://github.com/cameroncooke/AXe) — the
  reference implementation for the AXPTranslator path on iOS 26.
- [idb#767](https://github.com/facebook/idb/issues/767) — AXP dropping
  children of `role=group` containers.
