# Language
Shared vocabulary for architecture discussions.
## Terms
**Module** — Anything with an interface and an implementation. Scale-agnostic: function, class, package, or slice.

**Interface** — Everything a caller must know to use the module: types, invariants, error modes, ordering, config.

**Implementation** — The code inside. Distinct from Adapter.

**Depth** — Leverage at the interface: a lot of behaviour behind a small interface. **Deep** = high leverage. **Shallow** = interface nearly as complex as the implementation.

**Seam** — A place where you can alter behaviour without editing in that place. The location at which a module's interface lives.

**Adapter** — A concrete thing that satisfies an interface at a seam.

**Leverage** — What callers get from depth: more capability per unit of interface they have to learn.

**Locality** — What maintainers get from depth: change, bugs, knowledge concentrated at one place.
## Principles
- **Depth is a property of the interface, not the implementation.**
- **The deletion test.** Imagine deleting the module. If complexity vanishes, it was a pass-through. If complexity reappears across N callers, it was earning its keep.
- **The interface is the test surface.** Callers and tests cross the same seam.
- **One adapter = hypothetical seam. Two adapters = real seam.**
## Rejected framings
- "Component", "service", "boundary" — use Module, Seam, Interface instead.
