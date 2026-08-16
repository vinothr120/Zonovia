// Hand-written to mirror backend/app/asset_core/schemas.py's Asset*/AssetIdentifier*/
// AssetDocumentRead models exactly — no codegen in this project.

export interface Asset {
  id: string;
  name: string;
  asset_type_id: string;
  current_location_id: string | null;
  current_custodian_id: string | null;
  current_lifecycle_state_id: string | null;
  vendor_id: string | null;
  purchase_date: string | null;
  purchase_price: string | null;
  purchase_order_ref: string | null;
  created_at: string;
}

export interface AssetCreateInput {
  name: string;
  asset_type_id: string;
  current_location_id?: string | null;
  current_custodian_id?: string | null;
  vendor_id?: string | null;
  purchase_date?: string | null;
  purchase_price?: string | null;
  purchase_order_ref?: string | null;
}

// current_custodian_id is deliberately absent — AssetUpdate doesn't support editing it, and
// custodian assignment is Flow-actions work, deferred this increment (see AssetFormPage).
export interface AssetUpdateInput {
  name?: string;
  asset_type_id?: string;
  vendor_id?: string | null;
  purchase_date?: string | null;
  purchase_price?: string | null;
  purchase_order_ref?: string | null;
}

// Mirrors app.asset_core.service._IDENTIFIER_TYPES exactly (RFID_EPC added Phase 6).
export type IdentifierType = "QR" | "BARCODE" | "SERIAL" | "RFID_EPC";

export const IDENTIFIER_TYPES: IdentifierType[] = ["QR", "BARCODE", "SERIAL", "RFID_EPC"];

export interface AssetIdentifier {
  id: string;
  asset_id: string;
  identifier_type: string;
  value: string;
  is_primary: boolean;
  created_at: string;
}

export interface AssetIdentifierInput {
  identifier_type: IdentifierType;
  value: string;
  is_primary?: boolean;
}

export interface AssetDocument {
  id: string;
  asset_id: string;
  document_type: string | null;
  storage_provider: string;
  original_filename: string;
  content_type: string;
  size_bytes: number;
  checksum: string;
  uploaded_by: string | null;
  created_at: string;
}
