# UI Prototype
Several radically different UI variations on a single route, switchable via URL search param.
## When this is the right shape
- "What should this page look like?"
- "Try a few options for this dashboard."
## Two sub-shapes
### Sub-shape A — adjustment to existing page (preferred)
Variants rendered on the same route, gated by `?variant=` URL param.
### Sub-shape B — new page (last resort)
Throwaway route under `/prototype/<name>`.
## Process
### 1. Generate 3 radically different variants
Each must be **structurally different** — different layout, different information hierarchy.
### 2. Wire them together
```tsx
const variant = searchParams.get('variant') ?? 'A';
return (
  <>
    {variant === 'A' && <VariantA {...data} />}
    {variant === 'B' && <VariantB {...data} />}
    {variant === 'C' && <VariantC {...data} />}
    <PrototypeSwitcher variants={['A','B','C']} current={variant} />
  </>
);
```
### 3. Floating switcher at bottom
- Left/right arrows cycle variants
- URL shareable and reload-stable
- Hidden in production builds
### 4. Clean up
When variant wins: fold winner into page, delete losers and switcher.
## Anti-patterns
- Variants that differ only in colour
- Sharing too much code between variants
- Promoting prototype directly to production
