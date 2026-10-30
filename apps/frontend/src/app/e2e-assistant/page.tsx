import { notFound } from 'next/navigation';
import { AssistantChat } from '@/components/assistant/AssistantChat';

// Test-only mount point for the Playwright assistant spec; 404s unless the harness sets E2E_ASSISTANT=1.
export default function Page() {
  if (process.env.E2E_ASSISTANT !== '1') notFound();
  return <main className="p-6"><AssistantChat /></main>;
}
