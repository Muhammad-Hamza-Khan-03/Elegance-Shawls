// One picture is often listed several times by a shop CDN: `x.jpg`, `x_1800x1800.jpg`, `x.jpg?width=1200`.
// Mirrors the backend's dedupe so products ingested earlier are also shown without repeats.
const SIZE_SUFFIX = /_(?:\d{1,4}x\d{0,4}|x\d{1,4}|pico|icon|thumb|small|compact|medium|large|grande|original|master)(?=\.[A-Za-z0-9]+$)/i;

const pathOf = (url: string) => {
  try {
    return new URL(url, 'https://placeholder.invalid').pathname.toLowerCase();
  } catch {
    return url.split('?')[0].toLowerCase();
  }
};

export const imageIdentity = (url: string): string => {
  const path = pathOf(url);
  const name = (path.split('/').pop() ?? '').replace(SIZE_SUFFIX, '');
  return name || path;
};

const isPlain = (url: string) => !url.includes('?') && !SIZE_SUFFIX.test(pathOf(url));

/** One URL per picture, first-seen order, preferring the unresized original without a query string. */
export const dedupeImages = (urls: string[]): string[] => {
  const chosen = new Map<string, string>();
  for (const url of urls) {
    if (!url) continue;
    const key = imageIdentity(url);
    const current = chosen.get(key);
    if (current === undefined || (isPlain(url) && !isPlain(current))) chosen.set(key, url);
  }
  return [...chosen.values()];
};
