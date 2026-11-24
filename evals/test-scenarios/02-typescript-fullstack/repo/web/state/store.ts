import type { OrderLine, Product } from "@shared/types";

let state = { products: [] as Product[], cart: [] as OrderLine[] };
const setProducts = (p: Product[]) => { state = { ...state, products: p }; };

export function useStore() {
  return { ...state, setProducts };
}
