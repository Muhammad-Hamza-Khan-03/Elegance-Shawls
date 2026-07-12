import http from 'node:http';

const products = [
  { _id: 'p1', name: 'Classic Wool Shawl', slug: 'classic-wool-shawl', main_description: 'A warm brown wool shawl.', cover_image_url: 'https://placehold.co/600x800/6f4e37/ffffff?text=Classic+Shawl', images: [], category: 'shawls', price: 4500, currency: 'PKR', material: 'Wool', sizing: 'Free Size', item_number: 'ES-001', status: 'active', created_at: '2026-06-01T00:00:00Z', updated_at: '2026-06-01T00:00:00Z', variants: [{ _id: 'v1', color: 'Brown', size: 'Free Size', image_url: 'https://placehold.co/600x800/6f4e37/ffffff?text=Brown', price: 4500, stock: 3, stock_status: 'In stock' }, { _id: 'v2', color: 'Black', size: 'Free Size', image_url: 'https://placehold.co/600x800/111111/ffffff?text=Black', price: 4800, stock: 0, stock_status: 'Out of stock' }] },
  { _id: 'p2', name: 'Light Silk Stole', slug: 'light-silk-stole', main_description: 'A light silk stole.', cover_image_url: 'https://placehold.co/600x800/d8c0a8/2f241f?text=Silk+Stole', images: [], category: 'stoles', price: 2800, currency: 'PKR', status: 'active', created_at: '2026-07-01T00:00:00Z', updated_at: '2026-07-01T00:00:00Z', variants: [{ _id: 'v3', color: 'Beige', size: 'Free Size', image_url: 'https://placehold.co/600x800/d8c0a8/2f241f?text=Beige', price: 2800, stock: 5, stock_status: 'In stock' }] },
];

http.createServer((request, response) => {
  response.setHeader('Access-Control-Allow-Origin', '*');
  response.setHeader('Content-Type', 'application/json');
  if (request.url === '/health/' || request.url === '/ready/') return response.end(JSON.stringify({ status: 'ready' }));
  if (request.url?.startsWith('/products/slug/')) {
    const product = products.find((item) => item.slug === decodeURIComponent(request.url.split('/').pop() || ''));
    response.statusCode = product ? 200 : 404;
    return response.end(JSON.stringify(product || { detail: 'Product not found' }));
  }
  if (request.url?.startsWith('/products/')) return response.end(JSON.stringify({ items: products, next_cursor: null }));
  response.statusCode = 404;
  response.end(JSON.stringify({ detail: 'Not found' }));
}).listen(4100, '127.0.0.1');
