// The small Markdown subset the ingestion pipeline produces (## / ### headings, "- " bullets,
// **bold**, *italic*, blank-line paragraphs). Parsing only: rendering builds React elements elsewhere.
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

const stripInline = (text: string) => text.replace(/\*\*([^*]+)\*\*/g, '$1').replace(/\*([^*]+)\*/g, '$1');

/** Plain text for meta descriptions and structured data: no markers, single spaces. */
export const markdownToPlainText = (source: string): string =>
  parseMarkdown(source)
    .map((block) => stripInline(block.type === 'heading' ? block.text : block.type === 'list' ? block.items.join('. ') : block.lines.join(' ')))
    .join(' ')
    .replace(/\s+/g, ' ')
    .trim();

/** First real paragraph (headings and lists skipped), for a short teaser. */
export const firstParagraph = (source: string): string => {
  const block = parseMarkdown(source).find((b) => b.type === 'paragraph');
  return block && block.type === 'paragraph' ? stripInline(block.lines.join(' ')) : '';
};
