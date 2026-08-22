'use client';

import { createContext, ReactNode, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { Product, ProductVariant } from '@/types/types';
import {
  CART_STORAGE_KEY,
  CartItem,
  addCartItem,
  clearCartItems,
  decrementCartItem,
  getCartSummary,
  incrementCartItem,
  normalizeCartItems,
  removeCartItem,
  setCartItemQuantity,
} from '@/lib/cart';

type CartContextValue = {
  items: CartItem[];
  hydrated: boolean;
  itemCount: number;
  subtotal: number;
  currency: string;
  addItem: (product: Product, variant: ProductVariant, quantity?: number) => void;
  setItemQuantity: (lineId: string, quantity: number) => void;
  incrementItem: (lineId: string) => void;
  decrementItem: (lineId: string) => void;
  removeItem: (lineId: string) => void;
  clearCart: () => void;
};

const CartContext = createContext<CartContextValue | null>(null);

export const CartProvider = ({ children }: { children: ReactNode }) => {
  const [items, setItems] = useState<CartItem[]>(() => {
    if (typeof window === 'undefined') return [];
    try {
      const stored = window.localStorage.getItem(CART_STORAGE_KEY);
      if (!stored) return [];
      const parsed = JSON.parse(stored) as CartItem[];
      return normalizeCartItems(Array.isArray(parsed) ? parsed : []);
    } catch {
      return [];
    }
  });
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    const loadCart = () => {
      try {
        const stored = window.localStorage.getItem(CART_STORAGE_KEY);
        if (stored) {
          const parsed = JSON.parse(stored) as CartItem[];
          setItems(normalizeCartItems(Array.isArray(parsed) ? parsed : []));
        }
      } catch {
        setItems([]);
      } finally {
        setHydrated(true);
      }
    };

    if (typeof queueMicrotask === 'function') {
      queueMicrotask(loadCart);
    } else {
      window.setTimeout(loadCart, 0);
    }
  }, []);

  useEffect(() => {
    if (!hydrated) return;
    try {
      window.localStorage.setItem(CART_STORAGE_KEY, JSON.stringify(items));
    } catch {
      // Persisting cart is a progressive enhancement; a failed write should not break shopping.
    }
  }, [hydrated, items]);

  const addItem = useCallback((product: Product, variant: ProductVariant, quantity = 1) => {
    setItems((current) => addCartItem(current, product, variant, quantity));
  }, []);

  const setItemQuantity = useCallback((lineId: string, quantity: number) => {
    setItems((current) => setCartItemQuantity(current, lineId, quantity));
  }, []);

  const incrementItem = useCallback((lineId: string) => {
    setItems((current) => incrementCartItem(current, lineId));
  }, []);

  const decrementItem = useCallback((lineId: string) => {
    setItems((current) => decrementCartItem(current, lineId));
  }, []);

  const removeItem = useCallback((lineId: string) => {
    setItems((current) => removeCartItem(current, lineId));
  }, []);

  const clearCart = useCallback(() => setItems(clearCartItems()), []);

  const summary = useMemo(() => getCartSummary(items), [items]);

  const value = useMemo<CartContextValue>(() => ({
    items,
    hydrated,
    itemCount: summary.itemCount,
    subtotal: summary.subtotal,
    currency: summary.currency,
    addItem,
    setItemQuantity,
    incrementItem,
    decrementItem,
    removeItem,
    clearCart,
  }), [addItem, clearCart, decrementItem, hydrated, incrementItem, items, removeItem, setItemQuantity, summary.currency, summary.itemCount, summary.subtotal]);

  return <CartContext.Provider value={value}>{children}</CartContext.Provider>;
};

export const useCart = () => {
  const context = useContext(CartContext);
  if (!context) throw new Error('useCart must be used within a CartProvider.');
  return context;
};
