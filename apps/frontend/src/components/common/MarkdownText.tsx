import type { ReactNode } from 'react';
import { parseMarkdown } from '@/lib/markdown';

// Renders the small Markdown subset the ingestion pipeline produces. It builds React elements only:
// raw HTML is never interpreted and links are never created, so untrusted source text cannot inject markup.
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

const SIZES = {
  sm: { root: 'space-y-3 text-sm leading-6', h2: 'pt-2 text-base font-semibold', h3: 'pt-1 text-sm font-semibold text-[#9a6b3f]' },
  md: { root: 'space-y-4 text-base leading-8', h2: 'pt-4 font-heading text-2xl font-semibold', h3: 'pt-2 text-base font-semibold text-[#9a6b3f]' },
} as const;

export const MarkdownText = ({ text, className = '', size = 'sm' }: { text: string; className?: string; size?: keyof typeof SIZES }) => (
  <div className={`${SIZES[size].root} text-[#3b302a] ${className}`} data-testid="markdown">
    {parseMarkdown(text).map((block, index) => {
      if (block.type === 'heading') {
        return block.level === 2 ? (
          <h4 key={index} className={`${SIZES[size].h2} text-[#2f241f]`}>{renderInline(block.text)}</h4>
        ) : (
          <h5 key={index} className={SIZES[size].h3}>{renderInline(block.text)}</h5>
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
