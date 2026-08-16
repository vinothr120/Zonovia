// Hand-written to mirror backend/app/asset_core/schemas.py exactly — no codegen in this project.

export interface AssetCategory {
  id: string;
  name: string;
  description: string | null;
  created_at: string;
}

export interface AssetCategoryInput {
  name: string;
  description?: string | null;
}

export interface AssetType {
  id: string;
  category_id: string;
  name: string;
  description: string | null;
  created_at: string;
}

export interface AssetTypeInput {
  category_id: string;
  name: string;
  description?: string | null;
}

export interface Vendor {
  id: string;
  name: string;
  contact_name: string | null;
  email: string | null;
  phone: string | null;
  address: string | null;
  created_at: string;
}

export interface VendorInput {
  name: string;
  contact_name?: string | null;
  email?: string | null;
  phone?: string | null;
  address?: string | null;
}
