'use client';

import { useState } from 'react';
import Image, { type ImageProps } from 'next/image';

/** next/image that degrades to a branded tile when the source is missing or fails to load. */
export function SafeImage({ src, alt, ...props }: Omit<ImageProps, 'src'> & { src?: string | null }) {
  const [failedSrc, setFailedSrc] = useState<string | null>(null);
  if (!src || failedSrc === src) {
    return (
      <div role={alt ? 'img' : undefined} aria-label={alt || undefined} aria-hidden={alt ? undefined : true} className="absolute inset-0 flex items-center justify-center bg-gradient-to-br from-[#efe5d5] to-[#e2d0b8]">
        <span className="font-heading text-sm tracking-[0.2em] text-[#9a6b3f]/70">ELEGANCE</span>
      </div>
    );
  }
  return <Image {...props} src={src} alt={alt} onError={() => setFailedSrc(src)} />;
}
