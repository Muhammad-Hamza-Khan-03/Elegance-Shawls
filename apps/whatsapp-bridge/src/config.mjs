// The only place the switch is parsed. Anything but the literal "true" (case-insensitive) is off.
export function loadConfig(env = process.env) {
  const enabled = String(env.WHATSAPP_BRIDGE_ENABLED ?? 'false').trim().toLowerCase() === 'true';
  const config = {
    enabled,
    token: env.WHATSAPP_BRIDGE_TOKEN ?? '',
    redisUrl: env.REDIS_URL ?? '',
    sessionDir: env.WHATSAPP_SESSION_DIR ?? '/data/session',
    authStore: String(env.WHATSAPP_AUTH_STORE ?? 'file').toLowerCase(),
    authDatabaseUrl: env.WHATSAPP_AUTH_DATABASE_URL ?? '',
    authKey: env.WHATSAPP_AUTH_ENCRYPTION_KEY ?? '',
    imageEnabled: String(env.WHATSAPP_IMAGE_ENABLED ?? 'false').trim().toLowerCase() === 'true',
    voiceEnabled: String(env.WHATSAPP_VOICE_ENABLED ?? 'false').trim().toLowerCase() === 'true',
    port: Number(env.PORT ?? 3000),
    sendRatePerMin: Number(env.WHATSAPP_SEND_RATE_PER_MIN ?? 20),
  };
  const problems = [];
  if (enabled && !config.token) problems.push('WHATSAPP_BRIDGE_TOKEN is not set');
  if (enabled && !config.redisUrl) problems.push('REDIS_URL is not set');
  if (enabled && !['file', 'postgres'].includes(config.authStore)) problems.push('WHATSAPP_AUTH_STORE must be file or postgres');
  if (enabled && config.authStore === 'postgres' && !config.authDatabaseUrl) problems.push('WHATSAPP_AUTH_DATABASE_URL is not set');
  if (enabled && config.authStore === 'postgres' && !/^[0-9a-fA-F]{64}$/.test(config.authKey)) problems.push('WHATSAPP_AUTH_ENCRYPTION_KEY must be 64 hex characters');
  return { ...config, problems };
}
