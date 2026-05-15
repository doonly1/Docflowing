# ADR Format
ADRs live in `docs/adr/` and use sequential numbering: `0001-slug.md`, `0002-slug.md`, etc.
## Template
```md
# {Short title of the decision}
{1-3 sentences: what's the context, what did we decide, and why.}
```
An ADR can be a single paragraph.
## Optional sections
- **Status** frontmatter (`proposed | accepted | deprecated | superseded by ADR-NNNN`)
- **Considered Options** — only when the rejected alternatives are worth remembering
- **Consequences** — only when non-obvious downstream effects
## Numbering
Scan `docs/adr/` for the highest existing number and increment by one.
## When to offer an ADR
All three of these must be true:
1. **Hard to reverse** — the cost of changing your mind later is meaningful
2. **Surprising without context** — a future reader will wonder "why did they do it this way?"
3. **The result of a real trade-off** — there were genuine alternatives and you picked one for specific reasons
## What qualifies
- Architectural shape, integration patterns between contexts
- Technology choices that carry lock-in (database, message bus, auth provider)
- Boundary and scope decisions
- Deliberate deviations from the obvious path
- Constraints not visible in the code
- Rejected alternatives when the rejection is non-obvious
