'use client';

import { useEffect, useMemo, useState } from 'react';
import { Archive, Check, Edit3, Loader2, Plus, RefreshCcw, Search, Settings2, Sparkles, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { formatCurrency } from '@/lib/whatsapp';

const productStatuses = ['active', 'draft', 'out_of_stock', 'archived'] as const;
const productCategories = ['shawls', 'stoles'] as const;

type ProductStatus = (typeof productStatuses)[number];
type ProductCategory = (typeof productCategories)[number];
type AdminVariant = {
  _id?: string;
  id?: string;
  name: string;
  color?: string | null;
  size: string;
  image_url: string;
  price: number;
  currency: string;
  stock: number;
  stock_status?: string;
  description?: string | null;
};

type AdminProduct = {
  _id?: string;
  id?: string;
  name: string;
  slug: string;
  cover_image_url: string;
  images: string[];
  main_description?: string | null;
  category: ProductCategory;
  price?: number | null;
  currency: string;
  material?: string | null;
  sizing?: string | null;
  weight?: string | null;
  item_number?: string | null;
  status: ProductStatus;
  is_active?: boolean;
  variants: AdminVariant[];
  created_at?: string;
  updated_at?: string;
};

type ProductFormVariant = {
  uiId: string;
  backendId?: string;
  name: string;
  color: string;
  size: string;
  image_url: string;
  price: string;
  currency: string;
  stock: string;
  stock_status: string;
  description: string;
};

type ProductFormState = {
  name: string;
  slug: string;
  cover_image_url: string;
  images: string;
  main_description: string;
  category: ProductCategory;
  price: string;
  currency: string;
  material: string;
  sizing: string;
  weight: string;
  item_number: string;
  status: ProductStatus;
  variants: ProductFormVariant[];
};

type StatusFilter = ProductStatus | 'all';

type ApiListResponse = {
  items?: AdminProduct[];
  next_cursor?: string | null;
  detail?: string;
};

type ApiProductResponse = AdminProduct & { detail?: string };

const emptyVariant = (): ProductFormVariant => ({
  uiId: globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`,
  name: '',
  color: '',
  size: 'Free Size',
  image_url: '',
  price: '',
  currency: 'PKR',
  stock: '0',
  stock_status: 'In stock',
  description: '',
});

const emptyForm = (): ProductFormState => ({
  name: '',
  slug: '',
  cover_image_url: '',
  images: '',
  main_description: '',
  category: 'shawls',
  price: '',
  currency: 'PKR',
  material: '',
  sizing: '',
  weight: '',
  item_number: '',
  status: 'active',
  variants: [emptyVariant()],
});

const getProductId = (product: AdminProduct) => product._id || product.id || '';
const getVariantId = (variant: AdminVariant) => variant._id || variant.id || '';

const splitLines = (value: string) =>
  value
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);

const clampInteger = (value: string, fallback = 0) => {
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : fallback;
};

const toForm = (product?: AdminProduct | null): ProductFormState => {
  if (!product) return emptyForm();

  return {
    name: product.name || '',
    slug: product.slug || '',
    cover_image_url: product.cover_image_url || '',
    images: (product.images || []).join('\n'),
    main_description: product.main_description || '',
    category: product.category || 'shawls',
    price: product.price === null || product.price === undefined ? '' : String(product.price),
    currency: product.currency || 'PKR',
    material: product.material || '',
    sizing: product.sizing || '',
    weight: product.weight || '',
    item_number: product.item_number || '',
    status: product.status || 'active',
    variants: (product.variants || []).map((variant) => ({
      uiId: getVariantId(variant) || `${Date.now()}-${Math.random()}`,
      backendId: getVariantId(variant),
      name: variant.name || '',
      color: variant.color || '',
      size: variant.size || 'Free Size',
      image_url: variant.image_url || '',
      price: String(variant.price ?? 0),
      currency: variant.currency || product.currency || 'PKR',
      stock: String(variant.stock ?? 0),
      stock_status: variant.stock_status || 'In stock',
      description: variant.description || '',
    })),
  };
};

const toPayload = (form: ProductFormState) => {
  const images = splitLines(form.images);
  if (form.cover_image_url.trim() && !images.includes(form.cover_image_url.trim())) {
    images.unshift(form.cover_image_url.trim());
  }

  return {
    name: form.name.trim(),
    slug: form.slug.trim().toLowerCase(),
    cover_image_url: form.cover_image_url.trim(),
    images,
    main_description: form.main_description.trim() || undefined,
    category: form.category,
    price: form.price.trim() === '' ? undefined : Number(form.price),
    currency: form.currency.trim().toUpperCase() || 'PKR',
    material: form.material.trim() || undefined,
    sizing: form.sizing.trim() || undefined,
    weight: form.weight.trim() || undefined,
    item_number: form.item_number.trim() || undefined,
    status: form.status,
    variants: form.variants.map((variant) => ({
      name: variant.name.trim(),
      color: variant.color.trim() || undefined,
      size: variant.size.trim() || 'Free Size',
      image_url: variant.image_url.trim(),
      price: Number(variant.price),
      currency: variant.currency.trim().toUpperCase() || 'PKR',
      stock: clampInteger(variant.stock),
      stock_status: variant.stock_status.trim() || 'In stock',
      description: variant.description.trim() || undefined,
    })),
  };
};

const statusLabel: Record<ProductStatus, string> = {
  active: 'Live',
  draft: 'Draft',
  out_of_stock: 'Out of stock',
  archived: 'Archived',
};

const statusClasses: Record<ProductStatus, string> = {
  active: 'bg-emerald-100 text-emerald-800',
  draft: 'bg-amber-100 text-amber-900',
  out_of_stock: 'bg-rose-100 text-rose-800',
  archived: 'bg-slate-200 text-slate-800',
};

const actionLabel = (status: ProductStatus) => {
  if (status === 'active') return 'Unpublish';
  if (status === 'draft') return 'Publish';
  if (status === 'out_of_stock') return 'Mark active';
  return 'Restore';
};

const normalizeError = (value: unknown) => {
  if (value instanceof Error) return value.message;
  return 'Something went wrong while saving the product.';
};

const requestJson = async <T,>(url: string, init?: RequestInit): Promise<T> => {
  const response = await fetch(url, {
    headers: { 'content-type': 'application/json', ...(init?.headers || {}) },
    cache: 'no-store',
    ...init,
  });

  const payload = (await response.json().catch(() => null)) as T & { detail?: string } | null;
  if (!response.ok) {
    throw new Error(payload?.detail || 'The admin API request failed.');
  }
  return payload as T;
};

export function AdminProductManager() {
  const [products, setProducts] = useState<AdminProduct[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [form, setForm] = useState<ProductFormState>(() => emptyForm());
  const [query, setQuery] = useState('');
  const [categoryFilter, setCategoryFilter] = useState<ProductCategory | 'all'>('all');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const loadProducts = async (preserveId?: string | null) => {
    setLoading(true);
    setError('');
    try {
      const data = await requestJson<ApiListResponse>('/api/admin/products?limit=100');
      const items = data.items || [];
      setProducts(items);

      if (preserveId) {
        const refreshed = items.find((product) => getProductId(product) === preserveId);
        if (refreshed) {
          setForm(toForm(refreshed));
          setSelectedId(preserveId);
        }
      }
    } catch (err) {
      setError(normalizeError(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadProducts();
  }, []);

  const filteredProducts = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return [...products]
      .filter((product) => {
        const matchesQuery = !needle
          || [
            product.name,
            product.slug,
            product.material,
            product.sizing,
            product.weight,
            product.item_number,
            product.variants.map((variant) => [variant.name, variant.color, variant.size].filter(Boolean).join(' ')).join(' '),
          ].join(' ').toLowerCase().includes(needle);
        const matchesCategory = categoryFilter === 'all' || product.category === categoryFilter;
        const matchesStatus = statusFilter === 'all' || product.status === statusFilter;
        return matchesQuery && matchesCategory && matchesStatus;
      })
      .sort((a, b) => (b.updated_at || '').localeCompare(a.updated_at || ''));
  }, [products, query, categoryFilter, statusFilter]);

  const selectedProduct = products.find((product) => getProductId(product) === selectedId) || null;
  const summary = useMemo(() => {
    const active = products.filter((product) => product.status === 'active').length;
    const draft = products.filter((product) => product.status === 'draft').length;
    const lowStock = products.filter((product) => product.variants.some((variant) => variant.stock < 2)).length;
    return { total: products.length, active, draft, lowStock };
  }, [products]);

  const selectProduct = (product: AdminProduct) => {
    const id = getProductId(product);
    setSelectedId(id);
    setForm(toForm(product));
    setNotice(`Editing ${product.name}.`);
  };

  const startNewProduct = () => {
    setSelectedId(null);
    setForm(emptyForm());
    setNotice('Creating a new product.');
  };

  const updateVariant = (uiId: string, field: keyof ProductFormVariant, value: string) => {
    setForm((current) => ({
      ...current,
      variants: current.variants.map((variant) => (variant.uiId === uiId ? { ...variant, [field]: value } : variant)),
    }));
  };

  const addVariant = () => {
    setForm((current) => ({ ...current, variants: [...current.variants, emptyVariant()] }));
  };

  const removeVariant = (uiId: string) => {
    setForm((current) => ({
      ...current,
      variants: current.variants.length > 1 ? current.variants.filter((variant) => variant.uiId !== uiId) : current.variants,
    }));
  };

  const validateForm = () => {
    if (!form.name.trim()) return 'Product name is required.';
    if (!form.slug.trim()) return 'Product slug is required.';
    if (!form.cover_image_url.trim()) return 'A cover image URL is required.';
    if (!form.variants.length) return 'At least one variant is required.';

    for (const variant of form.variants) {
      if (!variant.name.trim()) return 'Every variant needs a name.';
      if (!variant.image_url.trim()) return 'Every variant needs an image URL.';
      if (variant.price.trim() === '') return 'Every variant needs a price.';
      if (!Number.isFinite(Number(variant.price))) return 'Variant prices must be numeric.';
      if (!Number.isFinite(Number(variant.stock))) return 'Variant stock must be numeric.';
    }

    return null;
  };

  const saveProduct = async () => {
    const validationError = validateForm();
    if (validationError) {
      setError(validationError);
      return;
    }

    setSaving(true);
    setError('');
    setNotice('');

    try {
      const payload = toPayload(form);
      const isEditing = Boolean(selectedId);
      const endpoint = isEditing ? `/api/admin/products/${selectedId}` : '/api/admin/products';
      const method = isEditing ? 'PUT' : 'POST';
      const saved = await requestJson<ApiProductResponse>(endpoint, {
        method,
        body: JSON.stringify(payload),
      });

      const savedId = getProductId(saved);
      setNotice(`${saved.name} ${isEditing ? 'updated' : 'created'} successfully.`);
      await loadProducts(savedId);
      setSelectedId(savedId);
      setForm(toForm(saved));
    } catch (err) {
      setError(normalizeError(err));
    } finally {
      setSaving(false);
    }
  };

  const updateStatus = async (product: AdminProduct, nextStatus: ProductStatus) => {
    const productId = getProductId(product);
    setError('');
    setNotice('');

    try {
      if (nextStatus === 'archived') {
        const updated = await requestJson<ApiProductResponse>(`/api/admin/products/${productId}`, {
          method: 'DELETE',
        });
        setNotice(`${updated.name} archived.`);
        await loadProducts(selectedId === productId ? null : selectedId);
        if (selectedId === productId) {
          setSelectedId(null);
          setForm(emptyForm());
        }
        return;
      }

      const updated = await requestJson<ApiProductResponse>(`/api/admin/products/${productId}/status`, {
        method: 'PATCH',
        body: JSON.stringify({ status: nextStatus }),
      });

      setNotice(`${updated.name} moved to ${statusLabel[nextStatus].toLowerCase()}.`);
      await loadProducts(productId);
    } catch (err) {
      setError(normalizeError(err));
    }
  };

  const updateStock = async (product: AdminProduct, variant: AdminVariant, stock: string) => {
    const productId = getProductId(product);
    const variantId = getVariantId(variant);
    if (!variantId) return;

    setError('');
    setNotice('');

    try {
      const updated = await requestJson<ApiProductResponse>(`/api/admin/products/${productId}/stock`, {
        method: 'PATCH',
        body: JSON.stringify({ variant_id: variantId, stock: clampInteger(stock) }),
      });
      setNotice(`${updated.name} stock updated.`);
      await loadProducts(productId);
    } catch (err) {
      setError(normalizeError(err));
    }
  };

  const selectedKey = selectedProduct ? getProductId(selectedProduct) : 'new';
  const selectedSummary = selectedProduct
    ? `${selectedProduct.status.replace(/_/g, ' ')} · ${selectedProduct.variants.length} variant${selectedProduct.variants.length === 1 ? '' : 's'}`
    : 'Start a new product from scratch.';

  return (
    <main id="main-content" className="space-y-8">
      <section className="rounded-[2rem] border border-[#e7dac8] bg-white p-8 shadow-sm">
        <div className="flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
          <div className="max-w-3xl space-y-4">
            <p className="text-xs font-bold uppercase tracking-[0.3em] text-[#9a6b3f]">Products</p>
            <h1 className="font-heading text-4xl font-semibold tracking-tight">Product management workspace</h1>
            <p className="leading-7 text-[#6f625a]">
              Manage the catalogue, edit product details, publish or archive items, and update stock directly from the admin shell.
            </p>
          </div>
          <div className="flex flex-wrap gap-3">
            <Button type="button" variant="outline" className="rounded-full border-[#d8c8b4] bg-transparent px-5" onClick={startNewProduct}>
              <Plus className="h-4 w-4" />
              New product
            </Button>
            <Button type="button" variant="outline" className="rounded-full border-[#d8c8b4] bg-transparent px-5" onClick={() => loadProducts(selectedId)}>
              <RefreshCcw className="h-4 w-4" />
              Refresh
            </Button>
          </div>
        </div>

        <div className="mt-8 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <article className="rounded-3xl bg-[#fbf7f0] p-5">
            <p className="text-sm text-[#6f625a]">Total products</p>
            <p className="mt-2 text-3xl font-semibold">{summary.total}</p>
          </article>
          <article className="rounded-3xl bg-[#fbf7f0] p-5">
            <p className="text-sm text-[#6f625a]">Published</p>
            <p className="mt-2 text-3xl font-semibold">{summary.active}</p>
          </article>
          <article className="rounded-3xl bg-[#fbf7f0] p-5">
            <p className="text-sm text-[#6f625a]">Drafts</p>
            <p className="mt-2 text-3xl font-semibold">{summary.draft}</p>
          </article>
          <article className="rounded-3xl bg-[#fbf7f0] p-5">
            <p className="text-sm text-[#6f625a]">Low stock products</p>
            <p className="mt-2 text-3xl font-semibold">{summary.lowStock}</p>
          </article>
        </div>
      </section>

      <section className="grid gap-6 xl:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)]">
        <div className="space-y-4 rounded-[2rem] border border-[#e7dac8] bg-white p-6 shadow-sm">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <p className="text-xs font-bold uppercase tracking-[0.28em] text-[#9a6b3f]">Catalogue list</p>
              <h2 className="font-heading mt-2 text-2xl font-semibold">Existing products</h2>
              <p className="mt-2 text-sm text-[#6f625a]">Select a product to edit, republish, adjust stock, or archive.</p>
            </div>
            <div className="text-sm text-[#6f625a]">Showing {filteredProducts.length} of {products.length}</div>
          </div>

          <div className="grid gap-3 lg:grid-cols-3">
            <label className="rounded-2xl border border-[#e7dac8] bg-[#fbf7f0] p-4 text-sm">
              <span className="mb-2 flex items-center gap-2 font-semibold text-[#2f241f]"><Search className="h-4 w-4" /> Search</span>
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search by name, slug, material, item #"
                className="w-full bg-transparent text-[#2f241f] outline-none placeholder:text-[#8f8074]"
              />
            </label>
            <label className="rounded-2xl border border-[#e7dac8] bg-[#fbf7f0] p-4 text-sm">
              <span className="mb-2 flex items-center gap-2 font-semibold text-[#2f241f]"><Settings2 className="h-4 w-4" /> Category</span>
              <select
                value={categoryFilter}
                onChange={(event) => setCategoryFilter(event.target.value as ProductCategory | 'all')}
                className="w-full bg-transparent text-[#2f241f] outline-none"
              >
                <option value="all">All categories</option>
                {productCategories.map((category) => (
                  <option key={category} value={category}>{category}</option>
                ))}
              </select>
            </label>
            <label className="rounded-2xl border border-[#e7dac8] bg-[#fbf7f0] p-4 text-sm">
              <span className="mb-2 flex items-center gap-2 font-semibold text-[#2f241f]"><Sparkles className="h-4 w-4" /> Status</span>
              <select
                value={statusFilter}
                onChange={(event) => setStatusFilter(event.target.value as StatusFilter)}
                className="w-full bg-transparent text-[#2f241f] outline-none"
              >
                <option value="all">All statuses</option>
                {productStatuses.map((status) => (
                  <option key={status} value={status}>{statusLabel[status]}</option>
                ))}
              </select>
            </label>
          </div>

          {loading ? (
            <div role="status" aria-live="polite" className="rounded-3xl border border-dashed border-[#e7dac8] p-10 text-center text-[#6f625a]">
              <Loader2 className="mx-auto h-6 w-6 animate-spin" />
              Loading products…
            </div>
          ) : error ? (
            <div role="alert" className="rounded-3xl border border-red-200 bg-red-50 p-6 text-red-800">
              <p className="font-semibold">Unable to load product management data.</p>
              <p className="mt-2 text-sm">{error}</p>
            </div>
          ) : filteredProducts.length === 0 ? (
            <div className="rounded-3xl border border-dashed border-[#e7dac8] bg-[#fbf7f0] p-10 text-center text-[#6f625a]">
              <p className="text-lg font-semibold text-[#2f241f]">No products match the current filters.</p>
              <p className="mt-2 text-sm">Create a new item or broaden the search to continue.</p>
            </div>
          ) : (
            <div className="space-y-4">
              {filteredProducts.map((product) => {
                const productId = getProductId(product);
                const isSelected = productId === selectedId;
                const totalStock = product.variants.reduce((sum, variant) => sum + Number(variant.stock || 0), 0);

                return (
                  <article
                    key={productId}
                    className={`rounded-[1.75rem] border p-5 transition ${isSelected ? 'border-[#2f241f] bg-[#fbf7f0]' : 'border-[#e7dac8] bg-white'}`}
                  >
                    <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                      <div className="space-y-2">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className={`rounded-full px-3 py-1 text-xs font-semibold ${statusClasses[product.status]}`}>
                            {statusLabel[product.status]}
                          </span>
                          <span className="text-xs uppercase tracking-[0.24em] text-[#9a6b3f]">{product.category}</span>
                        </div>
                        <h3 className="text-2xl font-semibold text-[#2f241f]">{product.name}</h3>
                        <p className="text-sm text-[#6f625a]">{product.slug} · {product.item_number || 'No item number'} · {product.currency} {product.price?.toLocaleString() ?? 'price auto-derived'}</p>
                        <p className="text-sm text-[#6f625a]">{product.variants.length} variant{product.variants.length === 1 ? '' : 's'} · {totalStock} total stock</p>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        <Button type="button" variant="outline" className="rounded-full border-[#d8c8b4] bg-transparent px-4" onClick={() => selectProduct(product)}>
                          <Edit3 className="h-4 w-4" />
                          Edit
                        </Button>
                        {product.status !== 'active' && (
                          <Button type="button" variant="outline" className="rounded-full border-[#d8c8b4] bg-transparent px-4" onClick={() => updateStatus(product, 'active')}>
                            <Check className="h-4 w-4" />
                            Publish
                          </Button>
                        )}
                        {product.status === 'active' && (
                          <Button type="button" variant="outline" className="rounded-full border-[#d8c8b4] bg-transparent px-4" onClick={() => updateStatus(product, 'draft')}>
                            <Sparkles className="h-4 w-4" />
                            Unpublish
                          </Button>
                        )}
                        {product.status !== 'archived' && (
                          <Button type="button" variant="destructive" className="rounded-full px-4" onClick={() => updateStatus(product, 'archived')}>
                            <Archive className="h-4 w-4" />
                            Archive
                          </Button>
                        )}
                      </div>
                    </div>

                    <div className="mt-5 grid gap-3 md:grid-cols-2">
                      {product.variants.slice(0, 4).map((variant) => (
                        <button
                          key={getVariantId(variant) || variant.name}
                          type="button"
                          onClick={() => selectProduct(product)}
                          className="rounded-2xl border border-[#e7dac8] bg-white p-4 text-left text-sm text-[#6f625a] transition hover:border-[#c8b39b]"
                        >
                          <p className="font-semibold text-[#2f241f]">{variant.name}</p>
                          <p className="mt-1">{[variant.color, variant.size].filter(Boolean).join(' · ') || 'Variant details pending'}</p>
                          <p className="mt-1">{formatCurrency(variant.price, variant.currency)} · {variant.stock} in stock</p>
                          <p className="mt-1 text-xs uppercase tracking-[0.22em] text-[#9a6b3f]">Edit stock in the form to the right</p>
                        </button>
                      ))}
                    </div>
                  </article>
                );
              })}
            </div>
          )}
        </div>

        <div className="space-y-4 rounded-[2rem] border border-[#e7dac8] bg-white p-6 shadow-sm">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <p className="text-xs font-bold uppercase tracking-[0.28em] text-[#9a6b3f]">Create and edit</p>
              <h2 className="font-heading mt-2 text-2xl font-semibold">{selectedProduct ? `Editing ${selectedProduct.name}` : 'New product draft'}</h2>
              <p className="mt-2 text-sm text-[#6f625a]">{selectedSummary}</p>
            </div>
            <Button type="button" variant="outline" className="rounded-full border-[#d8c8b4] bg-transparent px-4" onClick={startNewProduct}>
              <Plus className="h-4 w-4" />
              Clear form
            </Button>
          </div>

          {notice ? (
            <p role="status" className="rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-900">
              {notice}
            </p>
          ) : null}

          <div className="grid gap-4 md:grid-cols-2">
            <label className="space-y-2 text-sm font-medium">
              <span>Product name</span>
              <input value={form.name} onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))} className="w-full rounded-2xl border border-[#d8c8b4] bg-white px-4 py-3" placeholder="Classic Pashmina" />
            </label>
            <label className="space-y-2 text-sm font-medium">
              <span>Slug</span>
              <input value={form.slug} onChange={(event) => setForm((current) => ({ ...current, slug: event.target.value }))} className="w-full rounded-2xl border border-[#d8c8b4] bg-white px-4 py-3" placeholder="classic-pashmina" />
            </label>
            <label className="space-y-2 text-sm font-medium">
              <span>Cover image URL</span>
              <input value={form.cover_image_url} onChange={(event) => setForm((current) => ({ ...current, cover_image_url: event.target.value }))} className="w-full rounded-2xl border border-[#d8c8b4] bg-white px-4 py-3" placeholder="https://…" />
            </label>
            <label className="space-y-2 text-sm font-medium">
              <span>Category</span>
              <select value={form.category} onChange={(event) => setForm((current) => ({ ...current, category: event.target.value as ProductCategory }))} className="w-full rounded-2xl border border-[#d8c8b4] bg-white px-4 py-3">
                {productCategories.map((category) => (
                  <option key={category} value={category}>{category}</option>
                ))}
              </select>
            </label>
            <label className="space-y-2 text-sm font-medium">
              <span>Base price</span>
              <input type="number" min={0} value={form.price} onChange={(event) => setForm((current) => ({ ...current, price: event.target.value }))} className="w-full rounded-2xl border border-[#d8c8b4] bg-white px-4 py-3" placeholder="Optional, derived from variants" />
            </label>
            <label className="space-y-2 text-sm font-medium">
              <span>Currency</span>
              <input value={form.currency} onChange={(event) => setForm((current) => ({ ...current, currency: event.target.value }))} className="w-full rounded-2xl border border-[#d8c8b4] bg-white px-4 py-3" placeholder="PKR" />
            </label>
            <label className="space-y-2 text-sm font-medium md:col-span-2">
              <span>Images, one per line</span>
              <textarea value={form.images} onChange={(event) => setForm((current) => ({ ...current, images: event.target.value }))} rows={4} className="w-full rounded-2xl border border-[#d8c8b4] bg-white px-4 py-3" placeholder="Additional gallery image URLs" />
            </label>
            <label className="space-y-2 text-sm font-medium md:col-span-2">
              <span>Main description</span>
              <textarea value={form.main_description} onChange={(event) => setForm((current) => ({ ...current, main_description: event.target.value }))} rows={4} className="w-full rounded-2xl border border-[#d8c8b4] bg-white px-4 py-3" placeholder="Product copy shown on the storefront" />
            </label>
            <label className="space-y-2 text-sm font-medium">
              <span>Material</span>
              <input value={form.material} onChange={(event) => setForm((current) => ({ ...current, material: event.target.value }))} className="w-full rounded-2xl border border-[#d8c8b4] bg-white px-4 py-3" />
            </label>
            <label className="space-y-2 text-sm font-medium">
              <span>Sizing</span>
              <input value={form.sizing} onChange={(event) => setForm((current) => ({ ...current, sizing: event.target.value }))} className="w-full rounded-2xl border border-[#d8c8b4] bg-white px-4 py-3" />
            </label>
            <label className="space-y-2 text-sm font-medium">
              <span>Weight</span>
              <input value={form.weight} onChange={(event) => setForm((current) => ({ ...current, weight: event.target.value }))} className="w-full rounded-2xl border border-[#d8c8b4] bg-white px-4 py-3" />
            </label>
            <label className="space-y-2 text-sm font-medium">
              <span>Item number</span>
              <input value={form.item_number} onChange={(event) => setForm((current) => ({ ...current, item_number: event.target.value }))} className="w-full rounded-2xl border border-[#d8c8b4] bg-white px-4 py-3" />
            </label>
            <label className="space-y-2 text-sm font-medium">
              <span>Status</span>
              <select value={form.status} onChange={(event) => setForm((current) => ({ ...current, status: event.target.value as ProductStatus }))} className="w-full rounded-2xl border border-[#d8c8b4] bg-white px-4 py-3">
                {productStatuses.map((status) => (
                  <option key={status} value={status}>{statusLabel[status]}</option>
                ))}
              </select>
            </label>
          </div>

          <div className="space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h3 className="text-lg font-semibold text-[#2f241f]">Variants</h3>
                <p className="text-sm text-[#6f625a]">Each variant matches the backend contract and exposes stock editing inputs.</p>
              </div>
              <Button type="button" variant="outline" className="rounded-full border-[#d8c8b4] bg-transparent px-4" onClick={addVariant}>
                <Plus className="h-4 w-4" />
                Add variant
              </Button>
            </div>

            <div className="space-y-4">
              {form.variants.map((variant, index) => (
                <section key={variant.uiId} className="rounded-[1.5rem] border border-[#e7dac8] bg-[#fbf7f0] p-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="font-semibold text-[#2f241f]">Variant {index + 1}</p>
                    <Button type="button" variant="outline" className="rounded-full border-[#d8c8b4] bg-transparent px-3" onClick={() => removeVariant(variant.uiId)} disabled={form.variants.length === 1}>
                      <Trash2 className="h-4 w-4" />
                      Remove
                    </Button>
                  </div>

                  <div className="mt-4 grid gap-3 md:grid-cols-2">
                    <label className="space-y-2 text-sm">
                      <span>Name</span>
                      <input value={variant.name} onChange={(event) => updateVariant(variant.uiId, 'name', event.target.value)} className="w-full rounded-2xl border border-[#d8c8b4] bg-white px-4 py-3" placeholder="Burgundy" />
                    </label>
                    <label className="space-y-2 text-sm">
                      <span>Color</span>
                      <input value={variant.color} onChange={(event) => updateVariant(variant.uiId, 'color', event.target.value)} className="w-full rounded-2xl border border-[#d8c8b4] bg-white px-4 py-3" placeholder="Burgundy" />
                    </label>
                    <label className="space-y-2 text-sm">
                      <span>Size</span>
                      <input value={variant.size} onChange={(event) => updateVariant(variant.uiId, 'size', event.target.value)} className="w-full rounded-2xl border border-[#d8c8b4] bg-white px-4 py-3" placeholder="Free Size" />
                    </label>
                    <label className="space-y-2 text-sm">
                      <span>Image URL</span>
                      <input value={variant.image_url} onChange={(event) => updateVariant(variant.uiId, 'image_url', event.target.value)} className="w-full rounded-2xl border border-[#d8c8b4] bg-white px-4 py-3" placeholder="https://…" />
                    </label>
                    <label className="space-y-2 text-sm">
                      <span>Price</span>
                      <input type="number" min={0} value={variant.price} onChange={(event) => updateVariant(variant.uiId, 'price', event.target.value)} className="w-full rounded-2xl border border-[#d8c8b4] bg-white px-4 py-3" />
                    </label>
                    <label className="space-y-2 text-sm">
                      <span>Currency</span>
                      <input value={variant.currency} onChange={(event) => updateVariant(variant.uiId, 'currency', event.target.value)} className="w-full rounded-2xl border border-[#d8c8b4] bg-white px-4 py-3" />
                    </label>
                    <label className="space-y-2 text-sm">
                      <span>Stock</span>
                      <input type="number" min={0} value={variant.stock} onChange={(event) => updateVariant(variant.uiId, 'stock', event.target.value)} className="w-full rounded-2xl border border-[#d8c8b4] bg-white px-4 py-3" />
                    </label>
                    <label className="space-y-2 text-sm">
                      <span>Stock status</span>
                      <input value={variant.stock_status} onChange={(event) => updateVariant(variant.uiId, 'stock_status', event.target.value)} className="w-full rounded-2xl border border-[#d8c8b4] bg-white px-4 py-3" placeholder="In stock" />
                    </label>
                    <label className="space-y-2 text-sm md:col-span-2">
                      <span>Description</span>
                      <textarea value={variant.description} onChange={(event) => updateVariant(variant.uiId, 'description', event.target.value)} rows={3} className="w-full rounded-2xl border border-[#d8c8b4] bg-white px-4 py-3" />
                    </label>
                  </div>
                </section>
              ))}
            </div>
          </div>

          {error ? (
            <p role="alert" className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
              {error}
            </p>
          ) : null}

          <div className="flex flex-wrap gap-3 pt-2">
            <Button type="button" className="rounded-full bg-[#2f241f] px-6" onClick={saveProduct} disabled={saving}>
              {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
              {selectedKey === 'new' ? 'Create product' : 'Save product'}
            </Button>
            {selectedProduct ? (
              <>
                {selectedProduct.status !== 'active' ? (
                  <Button type="button" variant="outline" className="rounded-full border-[#d8c8b4] bg-transparent px-4" onClick={() => updateStatus(selectedProduct, 'active')}>
                    <Check className="h-4 w-4" />
                    Publish
                  </Button>
                ) : (
                  <Button type="button" variant="outline" className="rounded-full border-[#d8c8b4] bg-transparent px-4" onClick={() => updateStatus(selectedProduct, 'draft')}>
                    <Sparkles className="h-4 w-4" />
                    Unpublish
                  </Button>
                )}
                <Button type="button" variant="destructive" className="rounded-full px-4" onClick={() => updateStatus(selectedProduct, 'archived')}>
                  <Archive className="h-4 w-4" />
                  Archive
                </Button>
              </>
            ) : null}
          </div>
        </div>
      </section>
    </main>
  );
}
