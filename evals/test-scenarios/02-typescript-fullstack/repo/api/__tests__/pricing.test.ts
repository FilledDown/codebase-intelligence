import { totalFor } from "../services/pricing";

test("sums lines", () => {
  expect(totalFor([{ productId: "a", quantity: 2 }], [{ id: "a", name: "A", priceCents: 150 }])).toBe(300);
});
