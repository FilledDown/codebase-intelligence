import { Router } from "express";
import { listProducts } from "../db/client";

export const productsRouter = Router();

productsRouter.get("/", async (_req, res) => {
  res.json(await listProducts());
});
