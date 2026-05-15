# Interface Design
Based on "Design It Twice" — your first idea is unlikely to be the best.
## Process
### 1. Frame the problem space
Write a user-facing explanation of the problem space for the chosen candidate:
- The constraints any new interface would need to satisfy
- The dependencies it would rely on
- A rough illustrative code sketch

### 2. Spawn sub-agents
Spawn 3+ sub-agents in parallel. Each must produce a **radically different** interface:
- Agent 1: "Minimize the interface — aim for 1–3 entry points max."
- Agent 2: "Maximise flexibility — support many use cases and extension."
- Agent 3: "Optimise for the most common caller — make the default case trivial."

Each outputs:
1. Interface (types, methods, params)
2. Usage example
3. What the implementation hides behind the seam
4. Trade-offs

### 3. Present and compare
Contrast by **depth**, **locality**, and **seam placement**. Give your recommendation.
