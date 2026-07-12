import { ImageResponse } from 'next/og';

export const alt = 'Elegance Shawls — shawls and stoles in Pakistan';
export const size = { width: 1200, height: 630 };
export const contentType = 'image/png';

export default function OpenGraphImage() {
  return new ImageResponse(
    <div style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#2f241f', color: '#fbf7f0', position: 'relative' }}>
      <div style={{ position: 'absolute', width: 430, height: 430, borderRadius: 999, right: -80, top: -130, border: '70px solid rgba(201,154,103,.22)' }} />
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', textAlign: 'center' }}>
        <div style={{ color: '#d8b994', fontSize: 26, letterSpacing: 10, textTransform: 'uppercase' }}>Elegance Shawls</div>
        <div style={{ marginTop: 28, fontFamily: 'serif', fontSize: 78, maxWidth: 900, lineHeight: 1.05 }}>The finishing layer for every occasion.</div>
        <div style={{ marginTop: 28, fontSize: 26, color: 'rgba(255,255,255,.68)' }}>Shawls · Stoles · Pakistan</div>
      </div>
    </div>,
    size,
  );
}
