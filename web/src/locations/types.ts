// Hand-written to mirror backend/app/asset_core/schemas.py's AssetLocation* models exactly.

export interface AssetLocation {
  id: string;
  name: string;
  parent_location_id: string | null;
  location_type: string | null;
  sort_order: number;
  created_at: string;
}

export interface AssetLocationInput {
  name: string;
  parent_location_id?: string | null;
  location_type?: string | null;
  sort_order?: number;
}
