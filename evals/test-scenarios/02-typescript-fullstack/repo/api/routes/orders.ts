import { Router } from "express";
import { createOrder } from "../services/orderService";
import { validateLines } from "@shared/validation";

export const ordersRouter = Router();

ordersRouter.post("/", async (req, res) => {
  const lines = validateLines(req.body.lines);
  res.json(await createOrder(lines));
});
