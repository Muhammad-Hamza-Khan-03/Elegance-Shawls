import { createHmac, timingSafeEqual } from 'crypto';

export const ADMIN_SESSION_COOKIE = 'es_admin_session';
const SESSION_TTL_SECONDS = 60 * 60 * 8;

const getAdminSecret = () => process.env.ADMIN_API_KEY?.trim() || '';

const base64url = (value: string) => Buffer.from(value, 'utf8').toString('base64url');
const fromBase64url = (value: string) => Buffer.from(value, 'base64url').toString('utf8');

const sign = (payload: string, secret: string) =>
  createHmac('sha256', secret).update(payload).digest('base64url');

export const issueAdminSession = () => {
  const secret = getAdminSecret();
  if (!secret) return null;

  const issuedAt = Math.floor(Date.now() / 1000);
  const expiresAt = issuedAt + SESSION_TTL_SECONDS;
  const payload = `${issuedAt}.${expiresAt}`;
  const token = `${base64url(payload)}.${sign(payload, secret)}`;

  return {
    token,
    expiresAt,
    maxAge: SESSION_TTL_SECONDS,
  };
};

export const verifyAdminSession = (token?: string | null) => {
  const secret = getAdminSecret();
  if (!secret || !token) return false;

  const [encodedPayload, providedSignature] = token.split('.');
  if (!encodedPayload || !providedSignature) return false;

  let payload: string;
  try {
    payload = fromBase64url(encodedPayload);
  } catch {
    return false;
  }

  const [issuedAtRaw, expiresAtRaw] = payload.split('.');
  const issuedAt = Number(issuedAtRaw);
  const expiresAt = Number(expiresAtRaw);

  if (!Number.isFinite(issuedAt) || !Number.isFinite(expiresAt) || expiresAt <= issuedAt) return false;
  if (expiresAt <= Math.floor(Date.now() / 1000)) return false;

  const expectedSignature = sign(payload, secret);
  const provided = Buffer.from(providedSignature, 'utf8');
  const expected = Buffer.from(expectedSignature, 'utf8');

  return provided.length === expected.length && timingSafeEqual(provided, expected);
};

export const hasAdminSecret = () => Boolean(getAdminSecret());
