import { describe, expect, it } from 'vitest';
import { dedupeImages, imageIdentity } from './images';
import { firstParagraph, markdownToPlainText } from './markdown';
import { mapBackendProduct } from './api';

const BASE = 'https://scarvesaustralia.com.au/cdn/shop/files/';
const REAL = [
  'x-classic-1226720646.jpg', 'x-classic-1226720646_1800x1800.jpg',
  'x-classic-1227475036.png', 'x-classic-1227475036_1800x1800.png',
  'x-35721929752629.heic', 'x-35721929752629_1800x1800.heic', 'x-35721929785397.heic',
  'x-35721929850933.heic?v=1742615705&width=1200', 'x-35721929785397.heic?v=1773731095&width=1200',
  'x-classic-1227475036.png?v=1773736535&width=1200', 'x-35721929752629.heic?v=1773731095&width=1200',
  'x-classic-1226720646.jpg?v=1773731095&width=1200',
].map((name) => BASE + name);

describe('dedupeImages', () => {
  it('collapses every size of one picture (the 12 URLs of the real product are 5 pictures)', () => {
    const kept = dedupeImages(REAL);
    expect(kept).toHaveLength(5);
    expect(kept[0]).toBe(`${BASE}x-classic-1226720646.jpg`);
    expect(kept[1]).toBe(`${BASE}x-classic-1227475036.png`);
  });

  it('prefers the unresized original over a resized copy listed earlier, and keeps first-seen order', () => {
    expect(dedupeImages([`${BASE}a_1800x1800.jpg`, `${BASE}b.jpg`, `${BASE}a.jpg?width=1200`, `${BASE}a.jpg`])).toEqual([`${BASE}a.jpg`, `${BASE}b.jpg`]);
    expect(dedupeImages([`${BASE}a_1800x1800.jpg`])).toEqual([`${BASE}a_1800x1800.jpg`]);
  });

  it('never merges different pictures or names that only look like sizes', () => {
    expect(dedupeImages([`${BASE}front.jpg`, `${BASE}back.jpg`, `${BASE}photo-1800x1800.jpg`, `${BASE}scarf_large_cream.jpg`])).toHaveLength(4);
    expect(imageIdentity(`${BASE}front_1x1.png`)).toBe('front.png');
  });

  it('ignores empty entries and handles relative or odd URLs', () => {
    expect(dedupeImages(['', `${BASE}a.jpg`, '/img/a_100x100.jpg', 'not a url_200x200.png'])).toEqual([`${BASE}a.jpg`, 'not a url_200x200.png']);
  });

  it('is applied when a backend product is mapped, including variant images', () => {
    const product = mapBackendProduct({
      _id: 'p', slug: 's', name: 'Cream', images: REAL, cover_image_url: REAL[1],
      variants: [{ _id: 'v', color: 'Cream', price: 100, image_url: REAL[0] }],
    } as Parameters<typeof mapBackendProduct>[0]);
    expect(product.images).toHaveLength(5);
  });
});

describe('markdown helpers for metadata and teasers', () => {
  const md = '## Title here\n\nIntro with **bold** words.\n\n- one\n- two\n\n### Why?\n\nBecause *reasons*.';

  it('produces plain text without markers for meta descriptions and structured data', () => {
    expect(markdownToPlainText(md)).toBe('Title here Intro with bold words. one. two Why? Because reasons.');
    expect(markdownToPlainText('')).toBe('');
    expect(markdownToPlainText(md)).not.toMatch(/[#*]/);
  });

  it('picks the first real paragraph as a teaser, never a heading or list', () => {
    expect(firstParagraph(md)).toBe('Intro with bold words.');
    expect(firstParagraph('## Only a heading')).toBe('');
    expect(firstParagraph('- a\n- b')).toBe('');
  });
});
