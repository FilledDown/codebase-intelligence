import type { OrderLine, Product } from "@shared/types";

export function totalFor(lines: OrderLine[], products: Product[]): number {
  return lines.reduce((sum, l, i) => sum + l.quantity * products[i].priceCents, 0);
}
