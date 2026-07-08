export default function Home() {
  return (
    <main className="min-h-screen bg-[#fbf7f0] text-[#2f241f]">
      <section className="mx-auto flex min-h-screen w-full max-w-6xl flex-col items-center justify-center gap-10 px-6 py-20 text-center">
        <div className="space-y-5">
          <p className="text-sm font-semibold uppercase tracking-[0.35em] text-[#9a6b3f]">
            Elegance Shawls
          </p>
          <h1 className="max-w-4xl text-4xl font-semibold tracking-tight sm:text-6xl">
            Timeless shawls and stoles for everyday elegance.
          </h1>
          <p className="mx-auto max-w-2xl text-lg leading-8 text-[#6f625a]">
            Discover refined winter essentials crafted for comfort, modest styling,
            and graceful gifting across Pakistan.
          </p>
        </div>

        <div className="grid w-full gap-4 sm:grid-cols-3">
          {[
            "Premium shawl collection",
            "Elegant colors and soft textures",
            "Easy ordering through WhatsApp",
          ].map((item) => (
            <div
              key={item}
              className="rounded-3xl border border-[#e7dac8] bg-white/70 p-6 shadow-sm"
            >
              <p className="font-medium">{item}</p>
            </div>
          ))}
        </div>

        <a
          href="/products"
          className="rounded-full bg-[#2f241f] px-8 py-4 text-sm font-semibold text-white transition hover:bg-[#4a382f]"
        >
          Browse Collection
        </a>
      </section>
    </main>
  );
}
