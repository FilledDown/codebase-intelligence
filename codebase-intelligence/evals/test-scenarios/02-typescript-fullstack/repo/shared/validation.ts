import { z } from "zod";
import type { OrderLine } from "./types";

export const orderLineSchema = z.object({ productId: z.string(), quantity: z.number().int().positive() });
export const orderSchema = z.object({ lines: z.array(orderLineSchema).min(1) });

export function validateLines(lines: unknown): OrderLine[] {
  return orderSchema.parse({ lines }).lines;
}
