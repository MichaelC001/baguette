# How `describe-ui` finds every element (the hit-test sweep)

`describe-ui` returns the **complete** on-screen tree — app content, the
SpringBoard status bar (clock / Wi-Fi / battery), and the items inside
otherwise-childless SwiftUI containers (tab bars, nav bars, toolbars).
It does this by combining two sources: a precise recursive **walk** of
the frontmost app, plus a positional **hit-test sweep** that fills the
gaps the walk structurally can't reach.

This is the companion to [accessibility.md](../accessibility/README.md) — that
page documents the wire surface; this one explains *how the tree gets
complete*.

## TL;DR

> The walk gives you the precise deep tree; the grid sprays the screen
> finely enough that every normal-sized element the walk couldn't reach
> still gets hit; merge de-dups the spray and grafts the survivors into
> the right place.

## The pipeline

```
                         ┌─────────────────────────┐
                         │      describeAll()       │
                         └────────────┬────────────┘
                                      │
                ┌─────────────────────┴─────────────────────┐
                │                                            │
                ▼                                            ▼
   ┌────────────────────────┐                  ┌──────────────────────────┐
   │  ① RECURSIVE WALK      │                  │  ② GRID HIT-TEST SWEEP   │
   │  frontmost app only    │                  │  whole screen, by point  │
   │                        │                  │                          │
   │  walk accessibility-   │                  │  AXHitTestGrid →          │
   │  Children depth-first  │                  │  sample points (32pt)    │
   └───────────┬────────────┘                  └────────────┬─────────────┘
               │                                            │
               ▼                                            ▼
   ┌────────────────────────┐                  ┌──────────────────────────┐
   │  base tree             │                  │  skip points already     │
   │  (precise, deep,       │   contentLeaf-   │  inside a CONTENT LEAF   │
   │   but process-scoped)  │──Frames()───────▶│  (walk already has it)   │
   │                        │                  │  KEEP points inside      │
   │  • all app content     │                  │  empty CONTAINERS        │
   │  • tab bar = empty     │                  └────────────┬─────────────┘
   │    AXGroup (childless) │                               │
   │  • NO status bar       │                               ▼
   └───────────┬────────────┘                  ┌──────────────────────────┐
               │                                │  for each kept point:    │
               │                                │  objectAtPoint(x,y)      │
               │                                │  → deepest element       │
               │                                │    (crosses processes)   │
               │                                └────────────┬─────────────┘
               │                                             │
               │                                             ▼
               │                                ┌──────────────────────────┐
               │                                │  discovered[] (raw)      │
               │                                │  • status bar items      │
               │                                │  • tab-bar buttons       │
               │                                │  • MANY duplicates       │
               │                                │    (adjacent points hit  │
               │                                │     the same element)    │
               │                                └────────────┬─────────────┘
               │                                             │
               └──────────────────┬──────────────────────────┘
                                  ▼
                    ┌──────────────────────────────┐
                    │  ③ merging(discovered:)      │
                    │                              │
                    │  a. dedupKey: drop anything  │
                    │     already in tree OR a     │
                    │     repeat of another probe  │
                    │  b. graft each survivor under│
                    │     the DEEPEST container    │
                    │     that holds its centre    │
                    └───────────────┬──────────────┘
                                    ▼
                    ┌──────────────────────────────┐
                    │  COMPLETE, SELECTABLE TREE   │
                    │  walk's deep tree  +  status │
                    │  bar  +  tab buttons inside  │
                    │  their group                 │
                    └──────────────────────────────┘
```

## Why a *grid* finds (almost) everything

`objectAtPoint:displayId:bridgeDelegateToken:` is a **positional**
hit-test: give it a screen point, it returns the *deepest* accessibility
element whose frame covers that point — regardless of which process owns
it. Sample the whole screen densely enough and every element bigger than
the spacing is guaranteed to contain at least one sample.

Each `·` below is a 32 pt grid sample:

```
   ·    ·    ·    ·    ·    ·       ← status bar strip (cross-process)
   ┌───────┐ ·    ·  ┌──────┐
   ·  4:51 │·    ·   │battery·      clock & battery each catch a sample
   └───────┘ ·    ·  └──────┘
   ·    ·    ·    ·    ·    ·
        ┌────────────────────┐
   ·    │   "June, 2026"  ·  │·     big elements → many samples
        └────────────────────┘
   ·    ·    ·    ·    ·    ·
   ┌────┬────┬────┬────┬────┐
   │ ·1 │ ·2 │ ·3 │ 4· │ 5· │      each date cell ≥32pt → ≥1 sample
   └────┴────┴────┴────┴────┘
   ┌──────────────────────────┐
   │  Tab Bar (empty AXGroup) │      walk sees an EMPTY group here…
   │ ┌────┐┌────┐┌────┐┌────┐ │
   │ │Cal·││Lst·││Ana·││Set·│ │      …but each button catches a sample
   │ └────┘└────┘└────┘└────┘ │      → hit-test recovers them
   └──────────────────────────┘
```

- Grid step = **32 pt**. Apple's HIG minimum tap target is 44×44 pt and
  most controls are larger, so any element ≥ ~32 pt in both dimensions
  contains at least one sample → it's found.
- **Miss case:** an element *smaller* than the spacing that happens to
  sit entirely between four samples can fall through. Rare in practice;
  a tighter step trades completeness for more XPC round-trips (cost ∝
  points²).

So "finds everything" precisely means "finds every element of normal
interactive size."

## Why both sources are needed

```
                        │ in app's        │ answers a
   element              │ accessibility-  │ positional
                        │ Children walk?  │ hit-test?     →  recovered by
   ─────────────────────┼─────────────────┼───────────────┼────────────────
   normal app content   │   ✅ yes        │   ✅ yes      │  ① walk
   tab/nav bar buttons  │   ❌ no (empty  │   ✅ yes      │  ② sweep
   (childless container)│      container) │               │
   status bar (clock,   │   ❌ no (other  │   ✅ yes      │  ② sweep
    wifi, battery)      │      process)   │               │
   tiny <32pt isolated  │   ✅ if in walk │   ⚠ maybe miss│  ① walk
   ─────────────────────┴─────────────────┴───────────────┴────────────────
            ①  exact + deep, but blind across process / empty groups
            ②  flat + sampled, but sees by position regardless of owner
            ①⊎②  union → complete & selectable
```

The grid is only the **gap-filler**. The walk supplies the bulk
precisely (no sampling); the sweep adds only what the walk structurally
can't reach. To avoid wasting probes, the sweep **skips points already
inside a known content leaf** (`contentLeafFrames`) but **keeps points
inside empty containers** — an empty `AXGroup "Tab Bar"` is exactly
where hit-test-only children live.

## Why discoveries are grafted under a container

`merging()` doesn't just append discoveries to the root — it inserts
each one under the **deepest existing node that contains its centre**.
That matters for selection: a recovered `Calendar` tab button is grafted
*inside* the `AXGroup "Tab Bar"`, so a client-side hit-test descends into
the group and resolves the **button**, not the group that would
otherwise shadow it.

## Reading the log line

```
[ax] hit-test sweep: probed=259 discovered=255
```

- **probed (259)** — grid points actually hit-tested = full grid minus
  the points skipped because a content leaf already covers them.
- **discovered (255)** — probes that returned an element; the rest
  landed in genuine empty gaps.
- These are **mostly duplicates** — a 100 pt-wide tab button gets ~3
  probes across it, all returning the same button. `merging()`'s
  `dedupKey` collapses them, so only a handful of *new* nodes graft in;
  the recursive walk already supplied the rest.

## Cost & tuning knobs

The sweep adds latency (hundreds of XPC round-trips), so `describe-ui`
runs ~1.5–2 s versus near-instant for the bare walk. Bounding constants
live in `AXPTranslatorAccessibility`:

| Constant              | Default | Role                                            |
| --------------------- | ------- | ----------------------------------------------- |
| `gridStep`            | 32 pt   | sample spacing — smaller = more complete, slower |
| `gridCap`             | 600     | hard ceiling on probe count                     |
| `sweepBudgetSeconds`  | 2.5 s   | wall-clock budget; top-down sampling captures the status bar first even if cut short |
| `sweepDepth`          | 0       | each probe reads one element, not a deep subtree (keeps each hit-test cheap) |

## Where the code lives

| Piece                                | File                                                        |
| ------------------------------------ | ----------------------------------------------------------- |
| Recursive walk                       | `Domain/Accessibility/AXNode.swift` (`walk`)                |
| Grid point generator                 | `Domain/Accessibility/AXHitTestGrid.swift`                  |
| Leaf/container classification + merge| `Domain/Accessibility/AXNodeMerge.swift`                    |
| Sweep orchestration + `objectAtPoint`| `Infrastructure/Accessibility/AXPTranslatorAccessibility.swift` |

Pure logic (`AXHitTestGrid`, `contentLeafFrames`, `merging`,
`dedupKey`) is unit-tested in `Tests/BaguetteTests/Accessibility/`; only
the `objectAtPoint` XPC calls are integration-only.
