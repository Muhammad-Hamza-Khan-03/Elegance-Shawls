import { APP_CONFIG } from '@/config/app.config';

export interface CloudinaryUploadResponse {
  secure_url: string;
  public_id: string;
  width: number;
  height: number;
  format: string;
  bytes: number;
}

export interface CloudinaryUploadOptions {
  folder?: string;
  transformation?: {
    width?: number;
    height?: number;
    crop?: string;
    quality?: string | number;
    format?: string;
  };
}

/**
 * Upload image to Cloudinary
 * @param file - File object or image URL
 * @param options - Upload options
 * @returns Promise with Cloudinary response
 */
export const uploadToCloudinary = async (
  file: File | string,
  options: CloudinaryUploadOptions = {}
): Promise<CloudinaryUploadResponse> => {
  const { cloudinaryCloudName, cloudinaryApiKey } = APP_CONFIG;

  if (!cloudinaryCloudName || !cloudinaryApiKey) {
    throw new Error('Cloudinary credentials are not configured. Please check your environment variables.');
  }

  // Validate file
  if (typeof file === 'string') {
    // If it's already a URL, validate it
    try {
      new URL(file);
      // If it's a valid URL, return it as-is (assuming it's already uploaded)
      return {
        secure_url: file,
        public_id: '',
        width: 0,
        height: 0,
        format: '',
        bytes: 0,
      };
    } catch {
      throw new Error('Invalid image URL provided');
    }
  }

  // Validate file type
  if (!file.type.startsWith('image/')) {
    throw new Error('File must be an image');
  }

  // Validate file size (max 10MB)
  const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10MB
  if (file.size > MAX_FILE_SIZE) {
    throw new Error('Image size must be less than 10MB');
  }

  // Create form data
  const formData = new FormData();
  formData.append('file', file);
  formData.append('upload_preset', APP_CONFIG.cloudinaryUploadPreset || 'ml_default');
  formData.append('api_key', cloudinaryApiKey);

  if (options.folder) {
    formData.append('folder', options.folder);
  }

  // Add transformations if provided
  // if (options.transformation) {
  //   const transformations: string[] = [];
  //   if (options.transformation.width) {
  //     transformations.push(`w_${options.transformation.width}`);
  //   }
  //   if (options.transformation.height) {
  //     transformations.push(`h_${options.transformation.height}`);
  //   }
  //   if (options.transformation.crop) {
  //     transformations.push(`c_${options.transformation.crop}`);
  //   }
  //   if (options.transformation.quality) {
  //     transformations.push(`q_${options.transformation.quality}`);
  //   }
  //   if (options.transformation.format) {
  //     transformations.push(`f_${options.transformation.format}`);
  //   }
  //   if (transformations.length > 0) {
  //     formData.append('transformation', transformations.join(','));
  //   }
  // }

  try {
    const response = await fetch(
      `https://api.cloudinary.com/v1_1/${cloudinaryCloudName}/image/upload`,
      {
        method: 'POST',
        body: formData,
      }
    );

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(
        errorData.error?.message || `Upload failed with status ${response.status}`
      );
    }

    const data = await response.json();

    if (!data.secure_url) {
      throw new Error('Invalid response from Cloudinary');
    }

    return {
      secure_url: data.secure_url,
      public_id: data.public_id,
      width: data.width || 0,
      height: data.height || 0,
      format: data.format || '',
      bytes: data.bytes || 0,
    };
  } catch (error) {
    if (error instanceof Error) {
      throw error;
    }
    throw new Error('Failed to upload image to Cloudinary');
  }
};

/**
 * Upload multiple images to Cloudinary
 * @param files - Array of File objects or image URLs
 * @param options - Upload options
 * @returns Promise with array of Cloudinary responses
 */
export const uploadMultipleToCloudinary = async (
  files: (File | string)[],
  options: CloudinaryUploadOptions = {}
): Promise<CloudinaryUploadResponse[]> => {
  try {
    const uploadPromises = files.map((file) => uploadToCloudinary(file, options));
    return await Promise.all(uploadPromises);
  } catch (error) {
    if (error instanceof Error) {
      throw error;
    }
    throw new Error('Failed to upload images to Cloudinary');
  }
};

/**
 * Validate if a string is a valid image URL
 */
export const isValidImageUrl = (url: string): boolean => {
  try {
    const urlObj = new URL(url);
    return ['http:', 'https:'].includes(urlObj.protocol);
  } catch {
    return false;
  }
};

/**
 * Validate file before upload
 */
export const validateImageFile = (file: File): { valid: boolean; error?: string } => {
  // Check file type
  if (!file.type.startsWith('image/')) {
    return { valid: false, error: 'File must be an image' };
  }

  // Check file size (max 10MB)
  const MAX_FILE_SIZE = 10 * 1024 * 1024;
  if (file.size > MAX_FILE_SIZE) {
    return { valid: false, error: 'Image size must be less than 10MB' };
  }

  // Check allowed formats
  const allowedFormats = ['image/jpeg', 'image/jpg', 'image/png', 'image/webp', 'image/gif'];
  if (!allowedFormats.includes(file.type)) {
    return { valid: false, error: 'Image format not supported. Use JPEG, PNG, WebP, or GIF' };
  }

  return { valid: true };
};

