import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { CategoryFilter } from './product/ProductBrowser';
import { AdminProductManager } from './admin/ProductManagement';
import { Navbar } from './layout/Navbar';
import { Footer } from './layout/Footer';
import { CartProvider } from './cart/CartProvider';

const optionsOf = (html: string, selectId?: string) => {
  const scope = selectId ? html.slice(html.indexOf(`id="${selectId}"`)) : html;
  return [...scope.slice(0, scope.indexOf('</select>')).matchAll(/<option value="([^"]*)"[^>]*>([^<]*)<\/option>/g)].map((m) => [m[1], m[2]]);
};

describe('Scarves category presentation', () => {
  it('offers Scarves in the catalogue filter beside Shawls and Stoles', () => {
    const html = renderToStaticMarkup(<CategoryFilter value="all" onChange={() => {}} />);
    expect(optionsOf(html, 'category')).toEqual([
      ['all', 'All products'], ['shawls', 'Shawls'], ['stoles', 'Stoles'], ['scarves', 'Scarves'],
    ]);
  });

  it('links to the scarves catalogue from the navbar and footer', () => {
    expect(renderToStaticMarkup(<CartProvider><Navbar /></CartProvider>)).toContain('/products?category=scarves');
    expect(renderToStaticMarkup(<Footer />)).toContain('/products?category=scarves');
  });

  it('offers Scarves in the admin category options', () => {
    const html = renderToStaticMarkup(<AdminProductManager />);
    expect(html).toContain('<option value="scarves">Scarves</option>');
    expect(html).toContain('<option value="shawls">Shawls</option>');
    expect(html).toContain('<option value="stoles">Stoles</option>');
  });
});
