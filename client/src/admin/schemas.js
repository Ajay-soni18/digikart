/* Field schemas that drive the admin forms for each resource. */

const comingSoon = { name: "is_coming_soon", label: "Mark as Coming Soon", type: "toggle" };
const published = {
  name: "is_published",
  label: "Published (visible to buyers)",
  type: "toggle",
  hint: "Turn off to hide completely.",
};
const order = { name: "order", label: "Display order", type: "number", hint: "Lower shows first." };

export const SCHEMAS = {
  categories: [
    { name: "name", label: "Category name", type: "text", required: true },
    {
      name: "parent",
      label: "Parent category",
      type: "number",
      hint: "The #id of the parent, shown beside each category in the list. Leave blank for a top-level category. Categories are navigation only — they never carry a price.",
    },
    { name: "description", label: "Description", type: "textarea" },
    { name: "image", label: "Cover image", type: "file" },
    order,
    comingSoon,
    published,
  ],

  products: [
    { name: "category", label: "Category ID", type: "number", required: true },
    { name: "title", label: "Product title", type: "text", required: true },
    { name: "description", label: "Description", type: "textarea" },
    { name: "thumbnail", label: "Thumbnail", type: "file" },
    {
      name: "youtube_url",
      label: "YouTube video (optional)",
      type: "text",
      hint: "Shown free to everyone as the hook. The attached files are what's paid for.",
    },
    {
      name: "is_free",
      label: "Free for anyone signed in",
      type: "toggle",
      hint: "A free product can't also carry a price.",
    },
    {
      name: "price",
      label: "Price (₹)",
      type: "price",
      showIf: (v) => !v.is_free,
      hint: "Leave at 0 to sell this only inside a bundle.",
    },
    order,
    comingSoon,
    published,
  ],

  "product-files": [
    { name: "product", label: "Product ID", type: "number", required: true },
    { name: "title", label: "File name shown to buyers", type: "text", required: true },
    {
      name: "delivery",
      label: "How buyers receive it",
      type: "select",
      options: [
        { value: "download", label: "Direct download (any file type)" },
        { value: "protected", label: "Protected viewer — watermarked, no download (PDF only)" },
      ],
      hint: "The protected viewer only supports PDFs.",
    },
    {
      name: "file_type",
      label: "File type",
      type: "select",
      options: [
        { value: "pdf", label: "PDF" },
        { value: "image", label: "Image" },
        { value: "audio", label: "Audio" },
        { value: "video", label: "Video" },
        { value: "archive", label: "Archive (zip/rar)" },
        { value: "document", label: "Document" },
        { value: "other", label: "Other" },
      ],
    },
    order,
    published,
  ],

  bundles: [
    { name: "title", label: "Bundle title", type: "text", required: true },
    {
      name: "category",
      label: "Category ID (optional)",
      type: "number",
      hint: "Where the bundle is listed. Leave blank to keep it unlisted but still purchasable by anyone who already owns it.",
    },
    { name: "description", label: "Description", type: "textarea" },
    { name: "thumbnail", label: "Thumbnail", type: "file" },
    {
      name: "pricing",
      label: "How is it priced?",
      type: "select",
      options: [
        { value: "sum", label: "Sum of everything it contains" },
        { value: "custom", label: "A custom price" },
      ],
      hint: "A product reachable through several nested bundles is only counted once.",
    },
    {
      name: "custom_price",
      label: "Custom price (₹)",
      type: "price",
      showIf: (v) => v.pricing === "custom",
    },
    order,
    comingSoon,
    published,
  ],

  "bundle-items": [
    { name: "bundle", label: "Bundle ID", type: "number", required: true },
    {
      name: "item_type",
      label: "What are you adding?",
      type: "select",
      options: [
        { value: "product", label: "A product" },
        { value: "bundle", label: "Another bundle (nested)" },
      ],
    },
    {
      name: "item_id",
      label: "Its ID",
      type: "number",
      required: true,
      hint: "The #id shown beside each product or bundle in the lists.",
    },
    order,
  ],
};
