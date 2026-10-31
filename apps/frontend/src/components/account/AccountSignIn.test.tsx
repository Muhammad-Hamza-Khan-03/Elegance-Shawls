import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { AccountSignIn } from './AccountSignIn';

describe('AccountSignIn', () => {
  it('says sign-in is not set up when no Google client id is configured, and loads nothing external', () => {
    const html = renderToStaticMarkup(<AccountSignIn />);
    expect(html).toContain('not set up');
    expect(html).not.toContain('google');
  });
});
