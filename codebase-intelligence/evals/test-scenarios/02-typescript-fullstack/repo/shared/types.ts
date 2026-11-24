export interface Product { id: string; name: string; priceCents: number }
export interface OrderLine { productId: string; quantity: number }
export interface Order { id: string; lines: OrderLine[]; totalCents: number }
