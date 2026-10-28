import Link from 'next/link';

// The backend refuses to activate an ingested product outside the staged review workflow.
export const isStagedWorkflowError = (message: string) => /staged review workflow/i.test(message);

// A failed action (save, publish, archive) must never look like the list failed to load.
export const ActionErrorBanner = ({ message }: { message: string }) => {
  if (!message) return null;
  const staged = isStagedWorkflowError(message);
  return (
    <div role="alert" className="mb-4 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800" data-testid="action-error">
      {staged ? (
        <>
          <p className="font-semibold">This product came from ingestion, so it can&apos;t be published from here.</p>
          <p className="mt-1">
            Approve it, then use <strong>Publish</strong> in{' '}
            <Link href="/admin/staging" className="font-semibold underline underline-offset-2">Staged products</Link>
            {' '}(choose the Approved filter). That keeps the review record and the live product in step.
          </p>
        </>
      ) : (
        <p>{message}</p>
      )}
    </div>
  );
};
