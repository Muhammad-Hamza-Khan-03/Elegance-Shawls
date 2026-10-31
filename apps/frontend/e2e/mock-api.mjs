import crypto from 'node:crypto';
import http from 'node:http';

const products = [
  { _id: 'p1', name: 'Classic Wool Shawl', slug: 'classic-wool-shawl', main_description: 'A warm brown wool shawl.', cover_image_url: 'https://placehold.co/600x800/6f4e37/ffffff?text=Classic+Shawl', images: [], category: 'shawls', price: 4500, currency: 'PKR', material: 'Wool', sizing: 'Free Size', item_number: 'ES-001', status: 'active', created_at: '2026-06-01T00:00:00Z', updated_at: '2026-06-01T00:00:00Z', variants: [{ _id: 'v1', color: 'Brown', size: 'Free Size', image_url: 'https://placehold.co/600x800/6f4e37/ffffff?text=Brown', price: 4500, stock: 3, stock_status: 'In stock' }, { _id: 'v2', color: 'Black', size: 'Free Size', image_url: 'https://placehold.co/600x800/111111/ffffff?text=Black', price: 4800, stock: 0, stock_status: 'Out of stock' }] },
  { _id: 'p2', name: 'Light Silk Stole', slug: 'light-silk-stole', main_description: 'A light silk stole.', cover_image_url: 'https://placehold.co/600x800/d8c0a8/2f241f?text=Silk+Stole', images: [], category: 'stoles', price: 2800, currency: 'PKR', status: 'active', created_at: '2026-07-01T00:00:00Z', updated_at: '2026-07-01T00:00:00Z', variants: [{ _id: 'v3', color: 'Beige', size: 'Free Size', image_url: 'https://placehold.co/600x800/d8c0a8/2f241f?text=Beige', price: 2800, stock: 5, stock_status: 'In stock' }] },
  ...Array.from({ length: 10 }, (_, index) => ({ _id: `extra-${index}`, name: `Everyday Stole ${index + 1}`, slug: `everyday-stole-${index + 1}`, main_description: 'An everyday stole.', cover_image_url: `https://placehold.co/600x800/e5d4bf/2f241f?text=Stole+${index + 1}`, images: [], category: 'stoles', price: 1000 + index * 100, currency: 'PKR', status: 'active', created_at: `2026-05-${String(index + 1).padStart(2, '0')}T00:00:00Z`, updated_at: '2026-05-01T00:00:00Z', variants: [{ _id: `extra-v-${index}`, color: 'Neutral', size: 'Free Size', image_url: `https://placehold.co/600x800/e5d4bf/2f241f?text=Stole+${index + 1}`, price: 1000 + index * 100, stock: 2, stock_status: 'In stock' }] })),
];

// M3-S3: a UUID product outside the listing, so the assistant journey can use the kernel's UUID-only ids.
const AP = '11111111-1111-4111-8111-111111111111';
const AV = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const assistantProduct = { _id: AP, name: 'Pashmina Shawl', slug: 'assistant-pashmina', main_description: 'A soft pashmina.', cover_image_url: 'https://placehold.co/600x800/d8c0a8/2f241f?text=Pashmina', images: [], category: 'shawls', price: 3500, currency: 'PKR', status: 'active', created_at: '2026-07-01T00:00:00Z', updated_at: '2026-07-01T00:00:00Z', variants: [{ _id: AV, color: 'Ivory', size: 'Free Size', image_url: 'https://placehold.co/600x800/d8c0a8/2f241f?text=Ivory', price: 3500, stock: 5, stock_status: 'In stock' }] };
const actionLog = { executions: 0, requests: [] };
const idem = (base, n) => `idem_${crypto.createHash('sha256').update(`${base}:${n}`).digest('hex').slice(0, 24)}`;
const sse = (events) => events.map(([event, data], seq) => `id: ${seq}\nevent: ${event}\ndata: ${JSON.stringify(data)}\n\n`).join('');
const done = new Map();

http.createServer((request, response) => {
  response.setHeader('Access-Control-Allow-Origin', '*');
  if (request.method === 'OPTIONS') {
    // CORS preflight: the storefront sends W3C trace headers on browser reads.
    response.setHeader('Access-Control-Allow-Headers', request.headers['access-control-request-headers'] || '*');
    response.statusCode = 204;
    return response.end();
  }
  response.setHeader('Content-Type', 'application/json');
  // Admin accounts: one fixed owner, one fixed session token. The real checks are covered by the backend integration tests.
  const SESSION = 'es1.mockmockmockmockmockmockmockmockmockmockmock';
  const owner = { id: 'a1', email: 'owner@example.test', display_name: null, role: 'owner', status: 'active' };
  if (request.url === '/v1/admin/auth/login' && request.method === 'POST') {
    let body = '';
    request.on('data', (chunk) => { body += chunk; });
    return request.on('end', () => {
      const ok = body.includes('"password":"test-owner-password"') && body.includes('owner@example.test');
      response.statusCode = ok ? 200 : 401;
      response.end(JSON.stringify(ok ? { token: SESSION, expires_at: new Date(Date.now() + 8 * 3600e3).toISOString(), account: owner } : { detail: 'Invalid email or password' }));
    });
  }
  // Enquiries: the real validation is covered by the backend integration tests; this fake stale-checks one price and records the last body.
  const enquiry = { reference: 'ES-MOCK42', currency: 'PKR', total: 9000, created_at: '2026-07-01T00:00:00Z', items: [{ product: 'Classic Wool Shawl', color: 'Brown', size: 'Free Size', quantity: 2, unit_price: 4500 }] };
  if (request.url === '/v1/enquiries' && request.method === 'POST') {
    let body = '';
    request.on('data', (chunk) => { body += chunk; });
    return request.on('end', () => {
      globalThis.lastEnquiry = JSON.parse(body);
      const stale = globalThis.lastEnquiry.items.some((item) => item.unit_price === 1);
      response.statusCode = stale ? 409 : 201;
      response.end(JSON.stringify(stale ? { detail: { code: 'cart_stale', issues: [{ reason: 'price_changed' }] } } : enquiry));
    });
  }
  // M3-S3 fakes: a scripted assistant stream and an execute endpoint that confirms, replays by key and rejects a stale price.
  if (request.url === '/__actions') return response.end(JSON.stringify(actionLog));
  if (request.url === '/v1/assistant/stream' && request.method === 'POST') {
    let raw = '';
    request.on('data', (chunk) => { raw += chunk; });
    return request.on('end', () => {
      const req = JSON.parse(raw);
      const price = /stale/i.test(req.message) ? 3400 : 3500;
      const params = { product_id: AP, variant_id: AV, quantity: 1, expected_revision: 1, expected_unit_price: price, currency: 'PKR' };
      const decision = (key) => ({ outcome: 'validated', reason: 'ok', executed: false, replayed: false, idempotency_key: key });
      const proposal = (n, action_type, p) => ['proposal', { action_type, idempotency_key: idem(req.idempotency_key, n), session_id: req.session_id, decision: decision(idem(req.idempotency_key, n)), params: p }];
      response.setHeader('content-type', 'text/event-stream');
      response.end(sse([
        ['start', { protocol: 1, session_id: req.session_id, idempotency_key: req.idempotency_key, context: req.context }],
        ['text', { delta: 'Here is a shawl. ' }], ['product', { product_id: AP, name: 'Pashmina Shawl', revision: 1, price: 3500, currency: 'PKR', slug: assistantProduct.slug, image: 'https://placehold.co/600x800/d8c0a8/2f241f?text=Pashmina', color: 'Ivory' }],
        proposal(1, 'add_to_cart', params), proposal(2, 'start_whatsapp_enquiry', { items: [params] }), ['done', { events: 5 }],
      ]));
    });
  }
  if (request.url === '/v1/assistant/actions/execute' && request.method === 'POST') {
    let raw = '';
    request.on('data', (chunk) => { raw += chunk; });
    return request.on('end', () => {
      const req = JSON.parse(raw);
      const entry = { ...req, executed: false };
      actionLog.requests.push(entry);
      const rows = req.params.items ?? [req.params];
      const reject = (reason) => { response.statusCode = 409; response.end(JSON.stringify({ detail: { status: 'rejected', reason } })); };
      if (req.confirmed !== true) { response.statusCode = 422; return response.end('{}'); }
      const key = `${req.session_id}:${req.idempotency_key}`;
      if (done.has(key)) return response.end(JSON.stringify({ status: 'executed', action_type: req.action_type, replayed: true, result: done.get(key) }));
      if (rows.some((r) => r.expected_unit_price !== 3500)) return reject('stale_price');
      actionLog.executions += 1;
      entry.executed = true;
      const items = rows.map((r) => ({ product_id: r.product_id, variant_id: r.variant_id, quantity: r.quantity, slug: assistantProduct.slug }));
      const result = req.action_type === 'start_whatsapp_enquiry' ? { reference: 'ES-GOLD42', items, total: 3500, currency: 'PKR' } : { items };
      done.set(key, result);
      response.end(JSON.stringify({ status: 'executed', action_type: req.action_type, replayed: false, result }));
    });
  }
  if (request.url === '/__last-enquiry') return response.end(JSON.stringify(globalThis.lastEnquiry ?? null));
  if (request.url?.startsWith('/v1/admin/enquiries') && request.headers['x-admin-session'] === SESSION) {
    return response.end(JSON.stringify(request.url.toUpperCase().includes('REFERENCE=ES-NOPE22') ? [] : [enquiry]));
  }
  if (request.url?.startsWith('/v1/admin/auth/') || request.url?.startsWith('/products/admin')) {
    if (request.headers['x-admin-session'] !== SESSION) {
      response.statusCode = 401;
      return response.end(JSON.stringify({ detail: 'Invalid administrative credentials' }));
    }
    if (request.url === '/v1/admin/auth/me') return response.end(JSON.stringify({ account: owner, role: 'owner', legacy: false }));
    if (request.url === '/v1/admin/auth/logout') return response.end(JSON.stringify({ ok: true }));
  }
  if (request.url === '/health/' || request.url === '/ready/') return response.end(JSON.stringify({ status: 'ready' }));
  if (request.url === '/products/slug/unavailable-product') {
    response.statusCode = 503;
    return response.end(JSON.stringify({ detail: 'Service unavailable' }));
  }
  if (request.url?.startsWith('/products/slug/')) {
    const product = [...products, assistantProduct].find((item) => item.slug === decodeURIComponent(request.url.split('/').pop() || ''));
    response.statusCode = product ? 200 : 404;
    return response.end(JSON.stringify(product || { detail: 'Product not found' }));
  }
  if (request.url?.startsWith('/products/')) return response.end(JSON.stringify({ items: products, next_cursor: null }));
  response.statusCode = 404;
  response.end(JSON.stringify({ detail: 'Not found' }));
}).listen(4100, '127.0.0.1');
