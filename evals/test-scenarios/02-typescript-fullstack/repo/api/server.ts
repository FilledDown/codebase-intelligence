import express from "express";
import { ordersRouter } from "./routes/orders";
import { productsRouter } from "./routes/products";

const app = express();
app.use(express.json());
app.use("/api/orders", ordersRouter);
app.use("/api/products", productsRouter);

const port = Number(process.env.PORT ?? 3000);
app.listen(port);
