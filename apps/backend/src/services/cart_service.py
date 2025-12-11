from typing import Dict, Iterable, List, Optional

from redis import Redis
from sqlalchemy.orm import Session

from ..schemas import CartItem
from ..services.variant_service import VariantService


class CartService:
    """
    Redis-backed cart service for authenticated users.

    All cart data lives in Redis under the key pattern: cart:user:<user_id>
    The service exposes atomic operations that are safe for concurrent access.
    """

    CART_KEY_PREFIX = "cart:user:"

    def __init__(self, redis_client: Redis):
        self.redis = redis_client

    def _key(self, user_id: int) -> str:
        return f"{self.CART_KEY_PREFIX}{user_id}"

    def load_cart(self, user_id: int) -> List[CartItem]:
        """Load all cart items for a user."""
        raw_items = self.redis.hgetall(self._key(user_id))
        return [
            CartItem(product_variant_id=int(variant_id), quantity=int(quantity))
            for variant_id, quantity in raw_items.items()
        ]

    def save_cart(self, user_id: int, cart_items: Iterable[CartItem]) -> None:
        """
        Replace the entire cart for a user atomically.
        Deletes existing hash first, then sets new values.
        """
        key = self._key(user_id)
        pipe = self.redis.pipeline(transaction=True)
        pipe.delete(key)
        mapping: Dict[str, int] = {
            str(item.product_variant_id): item.quantity for item in cart_items if item.quantity > 0
        }
        if mapping:
            pipe.hset(key, mapping=mapping)
        pipe.execute()

    def clear_cart(self, user_id: int) -> None:
        """Remove all items from the user's cart."""
        self.redis.delete(self._key(user_id))

    def add_item(self, user_id: int, variant_id: int, quantity: int) -> int:
        """
        Add or increment a cart item atomically.
        Returns the new quantity for the variant.
        """
        if quantity <= 0:
            raise ValueError("Quantity must be greater than zero when adding items.")
        key = self._key(user_id)
        pipe = self.redis.pipeline(transaction=True)
        pipe.hincrby(key, str(variant_id), quantity)
        result = pipe.execute()
        return int(result[0])

    def update_quantity(self, user_id: int, variant_id: int, quantity: int) -> Optional[int]:
        """
        Set an item's quantity. If quantity <= 0, the item is removed.
        Returns the resulting quantity (or None if removed).
        """
        key = self._key(user_id)
        pipe = self.redis.pipeline(transaction=True)

        if quantity <= 0:
            pipe.hdel(key, str(variant_id))
            pipe.execute()
            return None

        pipe.hset(key, str(variant_id), quantity)
        pipe.execute()
        return quantity

    def delete_item(self, user_id: int, variant_id: int) -> None:
        """Delete an item from the cart."""
        self.redis.hdel(self._key(user_id), str(variant_id))

    def merge_guest_cart(
        self,
        user_id: int,
        guest_cart_items: Iterable[CartItem],
        db: Optional[Session] = None,
    ) -> List[CartItem]:
        """
        Merge a guest cart into the user's Redis cart.

        - Quantities are summed per variant.
        - If stock information is available, quantities are clamped to available stock.
        - Missing variants are skipped gracefully.
        """
        guest_items = list(guest_cart_items or [])
        if not guest_items:
            return self.load_cart(user_id)

        existing = {item.product_variant_id: item.quantity for item in self.load_cart(user_id)}
        merged: Dict[int, int] = dict(existing)

        for item in guest_items:
            variant_id = int(item.product_variant_id)
            qty = int(item.quantity)
            if qty <= 0:
                continue

            max_stock: Optional[int] = None
            if db is not None:
                variant = VariantService.get_variant_by_id(db, variant_id)
                if variant is None:
                    continue
                max_stock = int(variant.stock)

            new_qty = merged.get(variant_id, 0) + qty
            if max_stock is not None:
                new_qty = min(new_qty, max_stock)
            merged[variant_id] = new_qty

        # Persist merged cart atomically
        merged_items = [
            CartItem(product_variant_id=variant_id, quantity=quantity)
            for variant_id, quantity in merged.items()
            if quantity > 0
        ]
        self.save_cart(user_id, merged_items)
        return merged_items

    def get_cart_items(self, user_id: int) -> List[CartItem]:
        """Alias for load_cart for readability in route handlers."""
        return self.load_cart(user_id)

