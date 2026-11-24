import type { Order, OrderLine } from "@shared/types";
import { insertOrder, findProduct } from "../db/client";
import { totalFor } from "./pricing";

export async function createOrder(lines: OrderLine[]): Promise<Order> {
  const products = await Promise.all(lines.map((l) => findProduct(l.productId)));
  const totalCents = totalFor(lines, products);
  return insertOrder({ lines, totalCents });
}
