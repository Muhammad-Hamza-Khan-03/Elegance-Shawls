// Saved products: slugs only, in localStorage. Prices and stock are always read live, so nothing stale or personal is stored.
export const WISHLIST_KEY = 'elegance-shawls.wishlist.v1';
export const WISHLIST_MAX = 50;

export const normalizeWishlist = (value: unknown): string[] =>
  Array.isArray(value)
    ? Array.from(new Set(value.filter((slug): slug is string => typeof slug === 'string' && slug.length > 0 && slug.length <= 200))).slice(0, WISHLIST_MAX)
    : [];

export const toggleWishlist = (list: string[], slug: string): string[] =>
  list.includes(slug) ? list.filter((entry) => entry !== slug) : [slug, ...list].slice(0, WISHLIST_MAX);

export const readWishlist = (): string[] => {
  try {
    return normalizeWishlist(JSON.parse(localStorage.getItem(WISHLIST_KEY) || '[]'));
  } catch {
    return [];
  }
};

export const writeWishlist = (list: string[]): void => {
  try {
    localStorage.setItem(WISHLIST_KEY, JSON.stringify(list));
    window.dispatchEvent(new Event('wishlist-change'));
  } catch {
    // storage unavailable (private mode): the feature degrades to session-less no-op
  }
};
