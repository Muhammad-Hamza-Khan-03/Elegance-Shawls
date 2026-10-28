import type { ReactNode } from 'react';

// Renders the small Markdown subset the ingestion pipeline produces (## / ### headings, "- " bullets,
// **bold**, *italic*, blank-line paragraphs). It builds React elements only: raw HTML is never
// interpreted and links are never created, so untrusted source text cannot inject markup.
export type MarkdownBlock =
  | { type: 'heading'; level: 2 | 3; text: string }
  | { type: 'list'; items: string[] }
  | { type: 'paragraph'; lines: string[] };

export const parseMarkdown = (source: string): MarkdownBlock[] => {
  const blocks: MarkdownBlock[] = [];
  for (const chunk of source.replace(/\r/g, '').split(/\n{2,}/)) {
    let paragraph: string[] = [];
    let list: string[] = [];
    const flush = () => {
      if (paragraph.length) blocks.push({ type: 'paragraph', lines: paragraph });
      if (list.length) blocks.push({ type: 'list', items: list });
      paragraph = [];
      list = [];
    };
    for (const raw of chunk.split('\n')) {
      const line = raw.trim();
      if (!line) continue;
      const heading = /^(#{2,3})\s+(.+)$/.exec(line);
      if (heading) {
        flush();
        blocks.push({ type: 'heading', level: heading[1].length === 2 ? 2 : 3, text: heading[2] });
      } else if (line.startsWith('- ')) {
        if (paragraph.length) flush();
        list.push(line.slice(2).trim());
      } else {
        if (list.length) flush();
        paragraph.push(line);
      }
    }
    flush();
  }
  return blocks;
};

const INLINE = /\*\*([^*]+)\*\*|\*([^*]+)\*/g;

export const renderInline = (text: string): ReactNode[] => {
  const nodes: ReactNode[] = [];
  let last = 0;
  for (const match of text.matchAll(INLINE)) {
    if (match.index > last) nodes.push(text.slice(last, match.index));
    nodes.push(match[1] !== undefined ? <strong key={match.index}>{match[1]}</strong> : <em key={match.index}>{match[2]}</em>);
    last = match.index + match[0].length;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
};

export const MarkdownText = ({ text, className = '' }: { text: string; className?: string }) => (
  <div className={`space-y-3 text-sm leading-6 text-[#3b302a] ${className}`} data-testid="markdown">
    {parseMarkdown(text).map((block, index) => {
      if (block.type === 'heading') {
        return block.level === 2 ? (
          <h4 key={index} className="pt-2 text-base font-semibold text-[#2f241f]">{renderInline(block.text)}</h4>
        ) : (
          <h5 key={index} className="pt-1 text-sm font-semibold uppercase tracking-wide text-[#9a6b3f]">{renderInline(block.text)}</h5>
        );
      }
      if (block.type === 'list') {
        return (
          <ul key={index} className="list-disc space-y-1 pl-5 marker:text-[#c9a577]">
            {block.items.map((item, i) => <li key={i}>{renderInline(item)}</li>)}
          </ul>
        );
      }
      return (
        <p key={index}>
          {block.lines.map((line, i) => <span key={i}>{i > 0 ? <br /> : null}{renderInline(line)}</span>)}
        </p>
      );
    })}
  </div>
);
