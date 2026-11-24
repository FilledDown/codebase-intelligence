import React from "react";
import { ProductList } from "./components/ProductList";
import { OrderForm } from "./components/OrderForm";

export function App() {
  return (
    <main>
      <ProductList />
      <OrderForm />
    </main>
  );
}
