import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { ActionErrorBanner, isStagedWorkflowError } from './ActionErrorBanner';

describe('ActionErrorBanner', () => {
  it('renders nothing without an error', () => {
    expect(renderToStaticMarkup(<ActionErrorBanner message="" />)).toBe('');
  });

  it('explains the ingestion rule and links to the staged review page', () => {
    const html = renderToStaticMarkup(<ActionErrorBanner message="Ingested products must be published through the staged review workflow" />);
    expect(html).toContain('came from ingestion');
    expect(html).toContain('href="/admin/staging"');
    expect(html).toContain('role="alert"');
    expect(html).not.toContain('Unable to load');
  });

  it('shows other action errors as they are, as an action error and not a load failure', () => {
    const html = renderToStaticMarkup(<ActionErrorBanner message="Product slug already exists" />);
    expect(html).toContain('Product slug already exists');
    expect(html).not.toContain('Unable to load');
    expect(html).not.toContain('/admin/staging');
  });

  it('recognises only the staged-workflow message', () => {
    expect(isStagedWorkflowError('Ingested products must be published through the staged review workflow')).toBe(true);
    expect(isStagedWorkflowError('Product not found')).toBe(false);
  });
});
