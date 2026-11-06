// The only place the switch is parsed. Anything but the literal "true" (case-insensitive) is off.
export function loadConfig(env = process.env) {
  const enabled = String(env.WHATSAPP_BRIDGE_ENABLED ?? 'false').trim().toLowerCase() === 'true';
  const config = {
    enabled,
    token: env.WHATSAPP_BRIDGE_TOKEN ?? '',
    redisUrl: env.REDIS_URL ?? '',
    sessionDir: env.WHATSAPP_SESSION_DIR ?? '/data/session',
    port: Number(env.PORT ?? 3000),
    sendRatePerMin: Number(env.WHATSAPP_SEND_RATE_PER_MIN ?? 20),
  };
  const problems = [];
  if (enabled && !config.token) problems.push('WHATSAPP_BRIDGE_TOKEN is not set');
  if (enabled && !config.redisUrl) problems.push('REDIS_URL is not set');
  return { ...config, problems };
}
