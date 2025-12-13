"use client"
import { useState, useEffect, useRef } from 'react';
import { useRouter, useParams } from 'next/navigation';
import { ChevronLeft, Plus, X, Upload, Loader2 } from 'lucide-react';
import { AdminLayout } from '@/components/admin/adminLayout';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useToast } from '@/hooks/use-toast';
import { api, BackendProduct } from '@/lib/api';
import { uploadToCloudinary, validateImageFile, isValidImageUrl } from '@/lib/cloudinary';

interface VariantFormData {
  color: string;
  size: string;
  stock: number;
  price?: number;
  image_url?: string;
}

const AdminProductFormPage = () => {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { toast } = useToast();
  const isEditing = id && id !== 'new';
  const fileInputRef = useRef<HTMLInputElement>(null);
  const variantFileInputRefs = useRef<{ [key: number]: HTMLInputElement | null }>({});

  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);

  const [formData, setFormData] = useState({
    name: '',
    description: '',
    category: 'shawl' as 'shawl' | 'stole',
    price: '',
    stock: '',
    image_url: '',
  });

  const [variants, setVariants] = useState<VariantFormData[]>([
    { color: '', size: '', stock: 0 },
  ]);

  useEffect(() => {
    if (isEditing) {
      fetchProduct();
    }
  }, [id]);

  const fetchProduct = async () => {
    setLoading(true);
    try {
      const product = await api.getProductById(id!);
      if (product) {
        // Map backend product to form data
        setFormData({
          name: product.name || '',
          description: product.description || '',
          category: (product.category === 'stole' ? 'stole' : 'shawl') as 'shawl' | 'stole',
          price: product.price || '0',
          stock: String(product.stock || 0),
          // Use first variant's image_url or empty string
          image_url: product.variants?.[0]?.image_url || '',
        });

        // Map variants - if no variants, create one empty variant
        if (product.variants && product.variants.length > 0) {
          setVariants(
            product.variants.map((v) => ({
              color: v.color || '',
              size: v.size || '',
              stock: v.stock || 0,
              price: v.price ? parseFloat(v.price) : undefined,
              image_url: v.image_url || '',
            }))
          );
        } else {
          setVariants([{ color: '', size: '', stock: 0 }]);
        }
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to fetch product.';
      toast({
        title: 'Error',
        description: errorMessage,
      });
    } finally {
      setLoading(false);
    }
  };

  const handleImageUpload = async (file: File | null, variantIndex?: number) => {
    if (!file) return;

    // Validate file
    const validation = validateImageFile(file);
    if (!validation.valid) {
      toast({
        title: 'Invalid Image',
        description: validation.error,
      });
      return;
    }

    setUploading(true);
    try {
      const result = await uploadToCloudinary(file, {
        folder: 'elegance-shawls/products',
        transformation: {
          quality: 'auto',
          format: 'auto',
        },
      });

      if (variantIndex !== undefined) {
        // Update variant image
        const updated = [...variants];
        updated[variantIndex] = { ...updated[variantIndex], image_url: result.secure_url };
        setVariants(updated);
      } else {
        // Update main product image
        setFormData({ ...formData, image_url: result.secure_url });
      }

      toast({
        title: 'Image uploaded',
        description: 'Image has been uploaded successfully.',
      });
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to upload image.';
      toast({
        title: 'Upload failed',
        description: errorMessage,
      });
    } finally {
      setUploading(false);
    }
  };

  const handleImageUrlChange = (url: string, variantIndex?: number) => {
    if (!url.trim()) {
      if (variantIndex !== undefined) {
        const updated = [...variants];
        updated[variantIndex] = { ...updated[variantIndex], image_url: '' };
        setVariants(updated);
      } else {
        setFormData({ ...formData, image_url: '' });
      }
      return;
    }

    // Validate URL format
    if (!isValidImageUrl(url)) {
      toast({
        title: 'Invalid URL',
        description: 'Please enter a valid image URL.',
      });
      return;
    }

    if (variantIndex !== undefined) {
      const updated = [...variants];
      updated[variantIndex] = { ...updated[variantIndex], image_url: url };
      setVariants(updated);
    } else {
      setFormData({ ...formData, image_url: url });
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    // Validation
    if (!formData.name.trim()) {
      toast({
        title: 'Validation Error',
        description: 'Product name is required.',
      });
      return;
    }

    if (!formData.description.trim()) {
      toast({
        title: 'Validation Error',
        description: 'Product description is required.',
      });
      return;
    }

    const price = parseFloat(formData.price);
    if (isNaN(price) || price < 0) {
      toast({
        title: 'Validation Error',
        description: 'Please enter a valid price.',
      });
      return;
    }

    const stock = parseInt(formData.stock, 10);
    if (isNaN(stock) || stock < 0) {
      toast({
        title: 'Validation Error',
        description: 'Please enter a valid stock quantity.',
      });
      return;
    }

    // Validate variants
    const validVariants = variants.filter(
      (v) => v.color.trim() && v.size.trim() && v.stock >= 0
    );

    if (validVariants.length === 0) {
      toast({
        title: 'Validation Error',
        description: 'At least one valid variant is required.',
      });
      return;
    }

    setSaving(true);

    try {
      // Prepare product data matching backend API structure
      const productData = {
        name: formData.name.trim(),
        description: formData.description.trim(),
        category: formData.category,
        price: price,
        stock: stock,
        image_url: formData.image_url.trim() || undefined,
        variants: validVariants.map((v) => ({
          color: v.color.trim(),
          size: v.size.trim(),
          stock: v.stock,
          price: v.price,
          image_url: v.image_url?.trim() || undefined,
        })),
      };

      if (isEditing) {
        await api.updateProduct(id!, productData);
        toast({
          title: 'Product updated',
          description: 'The product has been updated successfully.',
        });
      } else {
        await api.createProduct(productData);
        toast({
          title: 'Product created',
          description: 'The product has been created successfully.',
        });
      }

      router.push('/admin/products');
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to save product.';
      toast({
        title: 'Error',
        description: errorMessage,
      });
    } finally {
      setSaving(false);
    }
  };

  const addVariant = () => {
    setVariants([...variants, { color: '', size: '', stock: 0 }]);
  };

  const removeVariant = (index: number) => {
    if (variants.length > 1) {
      setVariants(variants.filter((_, i) => i !== index));
    }
  };

  const updateVariant = (index: number, field: keyof VariantFormData, value: string | number) => {
    const updated = [...variants];
    updated[index] = { ...updated[index], [field]: value };
    setVariants(updated);
  };

  if (loading) {
    return (
      <AdminLayout>
        <div className="flex items-center justify-center h-96">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
        </div>
      </AdminLayout>
    );
  }

  return (
    <AdminLayout>
      <div className="max-w-3xl">
        <button
          onClick={() => router.push('/admin/products')}
          className="flex items-center text-sm text-muted-foreground hover:text-primary mb-6 transition-colors"
        >
          <ChevronLeft className="h-4 w-4 mr-1" />
          Back to Products
        </button>

        <h1 className="font-heading text-2xl md:text-3xl font-bold mb-6">
          {isEditing ? 'Edit Product' : 'Add Product'}
        </h1>

        <form onSubmit={handleSubmit} className="space-y-6">
          {/* Basic Info */}
          <div className="bg-card rounded-lg p-6 shadow-soft space-y-4">
            <h2 className="font-heading text-lg font-semibold">Basic Information</h2>

            <div className="space-y-2">
              <Label htmlFor="name">Product Name *</Label>
              <Input
                id="name"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                placeholder="Kashmir Pashmina Shawl"
                required
                minLength={2}
                maxLength={255}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="description">Description *</Label>
              <Textarea
                id="description"
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                placeholder="Product description..."
                rows={4}
                required
              />
            </div>

            <div className="grid md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="category">Category *</Label>
                <Select
                  value={formData.category}
                  onValueChange={(value) =>
                    setFormData({ ...formData, category: value as 'shawl' | 'stole' })
                  }
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="shawl">Shawl</SelectItem>
                    <SelectItem value="stole">Stole</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label htmlFor="price">Price (₹) *</Label>
                <Input
                  id="price"
                  type="number"
                  step="0.01"
                  min="0"
                  value={formData.price}
                  onChange={(e) => setFormData({ ...formData, price: e.target.value })}
                  placeholder="12500"
                  required
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="stock">Total Stock *</Label>
              <Input
                id="stock"
                type="number"
                min="0"
                value={formData.stock}
                onChange={(e) => setFormData({ ...formData, stock: e.target.value })}
                placeholder="50"
                required
              />
            </div>
          </div>

          {/* Main Product Image */}
          <div className="bg-card rounded-lg p-6 shadow-soft space-y-4">
            <h2 className="font-heading text-lg font-semibold">Product Image</h2>
            <p className="text-sm text-muted-foreground">
              Upload an image or enter a Cloudinary/image URL
            </p>

            <div className="space-y-4">
              <div className="flex gap-2">
                <Input
                  type="file"
                  ref={fileInputRef}
                  accept="image/*"
                  className="hidden"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) handleImageUpload(file);
                  }}
                />
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={uploading}
                >
                  {uploading ? (
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  ) : (
                    <Upload className="h-4 w-4 mr-2" />
                  )}
                  Upload Image
                </Button>
              </div>

              <div className="space-y-2">
                <Label htmlFor="image_url">Image URL</Label>
                <div className="flex gap-2">
                  <Input
                    id="image_url"
                    type="url"
                    value={formData.image_url}
                    onChange={(e) => handleImageUrlChange(e.target.value)}
                    placeholder="https://res.cloudinary.com/your-cloud/image/upload/..."
                  />
                  {formData.image_url && (
                    <img
                      src={formData.image_url}
                      alt="Preview"
                      className="w-16 h-16 rounded object-cover border"
                      onError={(e) => {
                        e.currentTarget.style.display = 'none';
                        toast({
                          title: 'Image Error',
                          description: 'Failed to load image. Please check the URL.',
                        });
                      }}
                    />
                  )}
                </div>
              </div>
            </div>
          </div>

          {/* Variants */}
          <div className="bg-card rounded-lg p-6 shadow-soft space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="font-heading text-lg font-semibold">Variants</h2>
              <Button type="button" variant="outline" size="sm" onClick={addVariant}>
                <Plus className="h-4 w-4 mr-1" />
                Add Variant
              </Button>
            </div>

            <p className="text-sm text-muted-foreground">
              Add product variants with different colors, sizes, and stock levels
            </p>

            {variants.map((variant, index) => (
              <div key={index} className="border rounded-lg p-4 space-y-4">
                <div className="flex items-center justify-between mb-2">
                  <h3 className="font-medium text-sm">Variant {index + 1}</h3>
                  {variants.length > 1 && (
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      onClick={() => removeVariant(index)}
                    >
                      <X className="h-4 w-4" />
                    </Button>
                  )}
                </div>

                <div className="grid md:grid-cols-3 gap-3">
                  <div className="space-y-2">
                    <Label>Color *</Label>
                    <Input
                      value={variant.color}
                      onChange={(e) => updateVariant(index, 'color', e.target.value)}
                      placeholder="Red"
                      required
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>Size *</Label>
                    <Input
                      value={variant.size}
                      onChange={(e) => updateVariant(index, 'size', e.target.value)}
                      placeholder="Large"
                      required
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>Stock *</Label>
                    <Input
                      type="number"
                      min="0"
                      value={variant.stock}
                      onChange={(e) => updateVariant(index, 'stock', parseInt(e.target.value, 10) || 0)}
                      placeholder="10"
                      required
                    />
                  </div>
                </div>

                <div className="grid md:grid-cols-2 gap-3">
                  <div className="space-y-2">
                    <Label>Price (₹) - Optional</Label>
                    <Input
                      type="number"
                      step="0.01"
                      min="0"
                      value={variant.price ?? ''}
                      onChange={(e) => {
                        const value = e.target.value;
                        if (value) {
                          const numValue = parseFloat(value);
                          if (!isNaN(numValue)) {
                            updateVariant(index, 'price', numValue);
                          }
                        } else {
                          const updated = [...variants];
                          updated[index] = { ...updated[index] };
                          delete updated[index].price;
                          setVariants(updated);
                        }
                      }}
                      placeholder="Variant specific price"
                    />
                  </div>
                </div>

                <div className="space-y-2">
                  <Label>Variant Image URL - Optional</Label>
                  <div className="flex gap-2">
                    <Input
                      type="file"
                      ref={(el) => {
                        variantFileInputRefs.current[index] = el;
                      }}
                      accept="image/*"
                      className="hidden"
                      onChange={(e) => {
                        const file = e.target.files?.[0];
                        if (file) handleImageUpload(file, index);
                      }}
                    />
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => variantFileInputRefs.current[index]?.click()}
                      disabled={uploading}
                    >
                      {uploading ? (
                        <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                      ) : (
                        <Upload className="h-4 w-4 mr-2" />
                      )}
                      Upload
                    </Button>
                    <Input
                      type="url"
                      value={variant.image_url || ''}
                      onChange={(e) => handleImageUrlChange(e.target.value, index)}
                      placeholder="Variant image URL"
                      className="flex-1"
                    />
                    {variant.image_url && (
                      <img
                        src={variant.image_url}
                        alt="Variant preview"
                        className="w-12 h-12 rounded object-cover border"
                        onError={(e) => {
                          e.currentTarget.style.display = 'none';
                        }}
                      />
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>

          {/* Submit */}
          <div className="flex gap-4">
            <Button type="submit" disabled={saving || uploading}>
              {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {isEditing ? 'Update Product' : 'Create Product'}
            </Button>
            <Button
              type="button"
              variant="outline"
              onClick={() => router.push('/admin/products')}
              disabled={saving || uploading}
            >
              Cancel
            </Button>
          </div>
        </form>
      </div>
    </AdminLayout>
  );
};

export default AdminProductFormPage;
