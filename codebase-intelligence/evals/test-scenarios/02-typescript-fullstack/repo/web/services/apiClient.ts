import type { Order, OrderLine, Product } from "@shared/types";

export async function fetchProducts(): Promise<Product[]> {
  return (await fetch("/api/products")).json();
}

export async function submitOrder(lines: OrderLine[]): Promise<Order> {
  const res = await fetch("/api/orders", { method: "POST", body: JSON.stringify({ lines }) });
  return res.json();
}
