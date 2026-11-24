import type { Order, Product } from "@shared/types";

const url = process.env.DATABASE_URL;

export async function listProducts(): Promise<Product[]> { return query(url, "select * from products"); }
export async function findProduct(id: string): Promise<Product> { return query(url, "select * from products where id=$1", [id]); }
export async function insertOrder(o: Omit<Order, "id">): Promise<Order> { return query(url, "insert into orders ...", [o]); }

declare function query(url: string | undefined, sql: string, args?: unknown[]): Promise<any>;
