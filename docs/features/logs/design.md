---
description: Why baguette's log stream shells out to `xcrun simctl spawn … log stream` rather than calling SimDevice.spawn directly, and how the stream's lifecycle and buffering work.
---

# Logs — design

## Path

```
CLI / WS  →  Simulator.logs()  →  LogStream
                                      │
                   fork+exec `xcrun simctl spawn <udid> log stream …`
                                      │
                                      ▼  (CoreSimulator XPC)
                              simulator's launchd
                                      │
                                      ▼
                   `/usr/bin/log stream` running as
                   the simulator's user (uid 501)
```

The filter is a value type projected into `log stream` argv; the spawn path
treats argv as opaque, so a new `log stream` flag only touches the filter,
the CLI option and the WebSocket query parser. The spawn rides `Subprocess`,
so the state machine and line splitting are unit-covered via `MockSubprocess`;
only `Process.run` / `kill(pid)` are integration-only.

## Why shell out instead of calling SimDevice.spawn directly

The CoreSimulator framework exposes
`-[SimDevice spawnWithPath:options:terminationQueue:terminationHandler:pid:error:]`
and the spawn options dictionary keys (`arguments`, `environment`,
`stdin`, `stdout`, `stderr`, `standalone`, `binpref`, …) are
documented in symbol form. A direct call from our process *almost*
works on iOS 26 — the spawn succeeds, the pid comes back, the pipe
gets bytes — but the spawned `log` binary aborts with:

```
log: mbr_check_membership_ext(): Input/output error
log: Must be admin to run 'stream' command
```

`xcrun simctl spawn` issues the same SimDevice call and works fine.
The difference is bootstrap context: `simctl` is Apple-signed and
`com.apple.CoreSimulator.CoreSimulatorService` accepts it as a
privileged caller, so the spawned process inherits a context where
`log`'s `mbr_check_membership_ext("admin", …)` succeeds. Direct
calls from non-Apple-signed processes don't get that context, the
membership check fails with EIO, and `log stream` refuses to run.

Shelling out via `Process(executableURL: /usr/bin/xcrun, arguments:
["simctl", "spawn", udid] + filter.argv)` sidesteps the gap. simctl
is guaranteed installed alongside the device set we're already
targeting, so there's no extra dependency. SIGTERM via
`Process.terminate()` cleanly stops both simctl and its child.

If the entitlement dance around direct spawn ever gets resolved,
the adapter is one file and the behaviour is fully captured by
`LogStream` — swap the implementation, run the same tests, ship.

## Why `--level` is narrow

The simulator's `/usr/bin/log stream` accepts only `--level default | info |
debug`. Each is "include events at-or-above this severity", so `default`
already covers default / error / fault. macOS's host `log` binary takes
additional values (`notice`, `error`, `fault`), but the iOS simulator runtime
ships a slimmer interface and rejects them — so baguette rejects them at the
wire to fail fast.

## Threading & lifecycle

- `Pipe.fileHandleForReading.readabilityHandler` runs on a private
  background queue — we line-split there and dispatch each line to
  the consumer's `onLine` callback verbatim. The CLI calls
  `FileHandle.standardOutput.write` (thread-safe); the WS path
  enqueues through an `AsyncStream<String>` with bounded
  buffering (2048 lines) so a slow client can't OOM the server.
- `Process.terminationHandler` fires on a Foundation-internal
  queue when the child exits — we collapse non-zero exits into
  `LogStreamError.nonZeroExit(code:)` and route to `onTerminate`.
- `stop()` is idempotent. The CLI's SIGINT handler installs a
  one-shot continuation guard so termination from any source
  (signal, child exit, `onTerminate`) ends the await exactly once.

## Known limits

- **No backpressure feedback to the producer.** A WS client that
  falls 2048 lines behind drops further lines silently
  (`AsyncStream.bufferingNewest`). Phase 2 would emit a
  `{"type":"log_dropped","count":N}` envelope when this happens;
  for now, slow consumers see truncated output.
