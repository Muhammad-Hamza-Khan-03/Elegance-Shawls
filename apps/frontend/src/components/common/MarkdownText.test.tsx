import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { MarkdownText, renderInline } from './MarkdownText';
import { parseMarkdown } from '@/lib/markdown';

describe('parseMarkdown', () => {
  it('splits headings, paragraphs and bullet lists', () => {
    expect(parseMarkdown('## Title\n\nOne\nTwo\n\n- a\n- b\n\n### Small\n\nEnd')).toEqual([
      { type: 'heading', level: 2, text: 'Title' },
      { type: 'paragraph', lines: ['One', 'Two'] },
      { type: 'list', items: ['a', 'b'] },
      { type: 'heading', level: 3, text: 'Small' },
      { type: 'paragraph', lines: ['End'] },
    ]);
  });

  it('keeps a list that follows a paragraph in the same chunk, and handles empty input', () => {
    expect(parseMarkdown('Intro\n- a\n- b')).toEqual([
      { type: 'paragraph', lines: ['Intro'] },
      { type: 'list', items: ['a', 'b'] },
    ]);
    expect(parseMarkdown('')).toEqual([]);
    expect(parseMarkdown('   \n\n  ')).toEqual([]);
  });

  it('treats plain, glued legacy descriptions as a single paragraph', () => {
    expect(parseMarkdown('WrapComplete your wardrobe')).toEqual([{ type: 'paragraph', lines: ['WrapComplete your wardrobe'] }]);
  });
});

describe('inline rendering', () => {
  it('renders bold and italic only', () => {
    expect(renderToStaticMarkup(<p>{renderInline('a **b** and *c* d')}</p>)).toBe('<p>a <strong>b</strong> and <em>c</em> d</p>');
  });

  it('escapes everything else', () => {
    const html = renderToStaticMarkup(<MarkdownText text={'<b onclick=x>hi</b> & [link](http://x)'} />);
    expect(html).toContain('&lt;b onclick=x&gt;hi&lt;/b&gt; &amp; [link](http://x)');
    expect(html).not.toContain('<a ');
  });
});
