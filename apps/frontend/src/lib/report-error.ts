// Privacy-safe error hook (issue #146). No-op until a reporter is installed; no provider is chosen here.
// Only the error name and Next's opaque digest are reported: never the message, URL query or stack,
// which can contain personal data.
type Report = { name: string; digest?: string; route: string };
type Reporter = (report: Report) => void;

let reporter: Reporter | null = null;

export function setErrorReporter(next: Reporter | null) {
  reporter = next;
}

export function reportError(error: Error & { digest?: string }, route: string) {
  try {
    reporter?.({ name: error.name, digest: error.digest, route });
  } catch {
    // a broken reporter must never break the error screen
  }
}
