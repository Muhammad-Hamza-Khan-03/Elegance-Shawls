"""Explicit allow-list of assistant tools: exactly the five kernel actions, nothing else."""
from actions.kernel import ACTIONS

TOOLS: dict[str, str] = {
    "show_products": "Show a list of catalogue products to the customer.",
    "open_product": "Open one product page.",
    "apply_filters": "Apply storefront filters.",
    "add_to_cart": "Propose adding one variant to the cart (needs explicit confirmation).",
    "start_whatsapp_order": "Propose starting a WhatsApp order (needs explicit confirmation).",
}
assert set(TOOLS) == set(ACTIONS)  # drift between registry and kernel fails at import
