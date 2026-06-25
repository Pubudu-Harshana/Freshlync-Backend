const cloudinary = require('cloudinary').v2;
const { CloudinaryStorage } = require('multer-storage-cloudinary');
const multer = require('multer');

cloudinary.config({
  cloud_name: process.env.CLOUDINARY_CLOUD_NAME,
  api_key:    process.env.CLOUDINARY_API_KEY,
  api_secret: process.env.CLOUDINARY_API_SECRET,
});

// Storage for product images
const productStorage = new CloudinaryStorage({
  cloudinary,
  params: {
    folder: 'freshlync/products',
    allowed_formats: ['jpg', 'jpeg', 'png', 'webp'],
    transformation: [{ width: 800, height: 800, crop: 'limit', quality: 'auto' }],
  },
});

// Storage for avatar/profile images
const avatarStorage = new CloudinaryStorage({
  cloudinary,
  params: {
    folder: 'freshlync/avatars',
    allowed_formats: ['jpg', 'jpeg', 'png', 'webp'],
    transformation: [{ width: 400, height: 400, crop: 'fill', gravity: 'face', quality: 'auto' }],
  },
});

// Storage for business verification documents (PDFs allowed)
// Use a params function so we can set resource_type per file:
//   - PDFs → resource_type: 'raw' with explicit public delivery type
//   - Images → resource_type: 'image'
const docStorage = new CloudinaryStorage({
  cloudinary,
  params: async (req, file) => {
    const isPdf = file.mimetype === 'application/pdf';
    // Sanitize filename and keep the original extension so the Cloudinary URL
    // ends in .pdf — without this, raw files get a bare public_id with no extension
    // and browsers cannot determine the file type.
    const safeName = file.originalname.replace(/\s/g, '_').replace(/[^a-zA-Z0-9._-]/g, '');
    return {
      folder: 'freshlync/documents',
      resource_type: isPdf ? 'raw' : 'image',
      type: 'upload',           // explicit public upload (not authenticated)
      access_mode: 'public',    // ensure publicly accessible URL
      public_id: `${Date.now()}-${safeName}`, // preserves .pdf extension in URL
      allowed_formats: isPdf ? ['pdf'] : ['jpg', 'jpeg', 'png', 'webp'],
    };
  },
});

const uploadProduct = multer({
  storage: productStorage,
  limits: { fileSize: 5 * 1024 * 1024 },
  fileFilter: (req, file, cb) => {
    const allowed = ['image/jpeg', 'image/jpg', 'image/png', 'image/webp'];
    if (allowed.includes(file.mimetype)) cb(null, true);
    else cb(new Error('Only JPG, JPEG, PNG, and WebP image files are allowed.'), false);
  },
});

const uploadAvatar = multer({
  storage: avatarStorage,
  limits: { fileSize: 10 * 1024 * 1024 },
});

const uploadDoc = multer({
  storage: docStorage,
  limits: { fileSize: 10 * 1024 * 1024 },
});

module.exports = { cloudinary, uploadProduct, uploadAvatar, uploadDoc };
