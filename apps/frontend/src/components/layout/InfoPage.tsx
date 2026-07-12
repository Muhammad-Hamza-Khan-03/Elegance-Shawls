import { ReactNode } from 'react';

export function InfoPage({ eyebrow, title, intro, children }: { eyebrow: string; title: string; intro: string; children: ReactNode }) {
  return <main id="main-content" className="min-h-[70vh] bg-[#fbf7f0] px-6 py-16 text-[#2f241f] sm:py-20">
    <article className="mx-auto max-w-3xl"><p className="text-xs font-bold uppercase tracking-[0.3em] text-[#9a6b3f]">{eyebrow}</p><h1 className="font-heading mt-4 text-4xl font-semibold sm:text-5xl">{title}</h1><p className="mt-5 text-lg leading-8 text-[#6f625a]">{intro}</p><div className="mt-12 space-y-9 [&_h2]:font-heading [&_h2]:text-2xl [&_h2]:font-semibold [&_p]:mt-3 [&_p]:leading-7 [&_p]:text-[#6f625a] [&_ul]:mt-3 [&_ul]:list-disc [&_ul]:space-y-2 [&_ul]:pl-6 [&_ul]:leading-7 [&_ul]:text-[#6f625a]">{children}</div></article>
  </main>;
}
