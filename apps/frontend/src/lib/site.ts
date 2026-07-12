const configuredSiteUrl = process.env.NEXT_PUBLIC_SITE_URL?.trim();

export const getSiteUrl = () => {
  if (!configuredSiteUrl) return null;
  try {
    const url = new URL(configuredSiteUrl);
    return url.protocol === 'https:' || url.hostname === 'localhost' ? url.origin : null;
  } catch {
    return null;
  }
};

export const absoluteUrl = (path: string) => {
  const siteUrl = getSiteUrl();
  return siteUrl ? new URL(path, `${siteUrl}/`).toString() : null;
};
