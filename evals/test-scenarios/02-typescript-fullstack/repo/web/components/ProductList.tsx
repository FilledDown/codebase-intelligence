import React, { useEffect } from "react";
import { useStore } from "../state/store";
import { fetchProducts } from "../services/apiClient";

export function ProductList() {
  const { products, setProducts } = useStore();
  useEffect(() => { fetchProducts().then(setProducts); }, []);
  return <ul>{products.map((p) => <li key={p.id}>{p.name}</li>)}</ul>;
}
