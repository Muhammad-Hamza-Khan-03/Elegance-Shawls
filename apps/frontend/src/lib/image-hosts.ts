// Allowlist for remote product images (issue #80). IMAGE_ALLOWED_HOSTS is a comma-separated list of hostnames;
// a leading "*." allows subdomains. Unset keeps the previous open behaviour (any HTTPS host) so existing catalogues keep rendering;
// set it once the real CDN hosts are known. Entries that are not a plain hostname are dropped, never passed through.
const HOST = /^(\*\.)?[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$/;

export const parseImageHosts = (value: string | undefined): string[] =>
  (value ?? '').split(',').map((entry) => entry.trim().toLowerCase()).filter((entry) => HOST.test(entry));

export const remoteImagePatterns = (hosts: string[]) =>
  hosts.length
    ? hosts.map((hostname) => ({ protocol: 'https' as const, hostname }))
    : [{ protocol: 'https' as const, hostname: '**' }];

export const imgSrc = (hosts: string[]) =>
  hosts.length ? `img-src 'self' data: blob: ${hosts.map((host) => `https://${host}`).join(' ')}` : "img-src 'self' data: blob: https:";
