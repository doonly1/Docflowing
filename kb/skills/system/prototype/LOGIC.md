# Logic Prototype
A tiny interactive terminal app for state/business logic validation.
## When this is the right shape
- "I'm not sure if this state machine handles edge case X then Y."
- "Does this data model let me represent the case where..."
- "I want to feel out what the API should look like before writing it."
## Process
### 1. State the question
Write down what state model and what question you're prototyping. One paragraph.
### 2. Isolate the logic
Put the actual logic behind a small, pure interface:
- **Pure reducer**: `(state, action) => state`
- **State machine**: explicit states and transitions
- **Pure functions** over a plain data type
### 3. Build the TUI
```typescript
while (true) {
  console.clear();
  printState(currentState);
  const input = readline();
  currentState = reducer(currentState, parseAction(input));
}
```
### 4. Make it runnable in one command
Add to project's task runner: `pnpm run prototype-name`
### 5. Capture the answer
When done, keep the **logic** (liftable into production), delete the **TUI**.
## Anti-patterns
- Don't add tests
- Don't wire to real database
- Don't generalise
- Don't blur logic and TUI together
