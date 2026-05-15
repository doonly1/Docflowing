# When to Mock
Mock at **system boundaries** only:
- External APIs (payment, email, etc.)
- Databases (sometimes - prefer test DB)
- Time/randomness
- File system (sometimes)
Don't mock:
- Your own classes/modules
- Internal collaborators
- Anything you control
## Designing for Mockability
1. **Use dependency injection**
   ```typescript
   // Easy to mock
   function processPayment(order, paymentClient) {
     return paymentClient.charge(order.total);
   }
   ```
2. **Prefer SDK-style interfaces** over generic fetchers
   ```typescript
   // GOOD: Each function is independently mockable
   const api = {
     getUser: (id) => fetch(`/users/${id}`),
     getOrders: (userId) => fetch(`/users/${userId}/orders`),
   };
   ```
