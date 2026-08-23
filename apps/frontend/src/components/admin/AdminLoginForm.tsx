'use client';

import { FormEvent, useMemo, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Button } from '@/components/ui/button';

export const AdminLoginForm = () => {
  const router = useRouter();
  const searchParams = useSearchParams();
  const nextPath = useMemo(() => searchParams.get('next') || '/admin/dashboard', [searchParams]);
  const [adminKey, setAdminKey] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setLoading(true);
    setError('');

    try {
      const response = await fetch('/api/admin/session', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key: adminKey }),
      });

      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.detail || 'Unable to sign in.');
      }

      router.replace(nextPath);
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to sign in.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={onSubmit} className="space-y-4">
      <div>
        <label htmlFor="admin-key" className="mb-2 block text-sm font-medium text-[#4b3a31]">
          Admin key
        </label>
        <input
          id="admin-key"
          type="password"
          autoComplete="current-password"
          value={adminKey}
          onChange={(event) => setAdminKey(event.target.value)}
          className="w-full rounded-2xl border border-[#d8c8b4] bg-white px-4 py-3 text-sm shadow-sm outline-none transition focus:border-[#9a6b3f] focus:ring-2 focus:ring-[#d8b994]/60"
          placeholder="Enter the shared admin key"
          required
        />
      </div>

      {error ? (
        <p className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700" role="alert">
          {error}
        </p>
      ) : null}

      <Button type="submit" className="w-full rounded-2xl bg-[#2f241f] py-6 text-sm font-semibold text-white hover:bg-[#4a382f]" disabled={loading}>
        {loading ? 'Signing in…' : 'Sign in'}
      </Button>
    </form>
  );
};
