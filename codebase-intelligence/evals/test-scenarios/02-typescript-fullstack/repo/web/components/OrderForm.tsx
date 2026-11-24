import React from "react";
import { validateLines } from "@shared/validation";
import { submitOrder } from "../services/apiClient";
import { useStore } from "../state/store";

export function OrderForm() {
  const { cart } = useStore();
  return <button onClick={() => submitOrder(validateLines(cart))}>Order</button>;
}
