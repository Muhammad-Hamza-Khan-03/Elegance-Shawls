// Shared UI rules for the storefront shopping assistant.

// Off unless switched on; NEXT_PUBLIC_ values are non-secret and inlined at build time.
export const isAssistantEnabled = (flag = process.env.NEXT_PUBLIC_ASSISTANT_ENABLED) => flag === '1' || flag === 'true';

// Never on admin or cart/checkout routes.
export const isAssistantRoute = (pathname: string | null) =>
  Boolean(pathname) && !/^\/(admin|cart)(\/|$)/.test(pathname as string);

export const SUGGESTED_PROMPTS = ['Show me shawls', 'Light stoles for summer', 'Black shawl under 5000'];
