// Hand-written to mirror backend/app/tracking/schemas.py (gateways/devices) and
// backend/app/track_rfid/schemas.py (tags/read-events) exactly — no codegen in this project.

export interface DeviceGateway {
  id: string;
  name: string;
  location_id: string | null;
  status: string;
  api_key_last4: string;
  last_seen_at: string | null;
  created_at: string;
}

export interface DeviceGatewayCreateInput {
  name: string;
  location_id?: string;
}

// The ONLY response shape that ever carries the raw api_key — see
// DeviceGatewayService.create_gateway's docstring (tracking/service.py:117-119): never logged,
// never audited, never retrievable again after this one response. Every later read (GET, list)
// returns DeviceGateway alone, which has api_key_last4 only.
export interface DeviceGatewayCreateResponse {
  gateway: DeviceGateway;
  api_key: string;
}

// device_type is free text server-side (String(50), default "RFID_READER") — no fixed
// allow-list, unlike tag_type below.
export interface Device {
  id: string;
  gateway_id: string | null;
  device_type: string;
  vendor: string | null;
  model: string | null;
  serial_number: string | null;
  status: string;
  last_seen_at: string | null;
  created_at: string;
}

export interface DeviceCreateInput {
  device_type?: string;
  vendor?: string;
  model?: string;
  serial_number?: string;
}

// Mirrors app.track_rfid.models._TAG_TYPES exactly.
export type TagType = "passive" | "active";

export const TAG_TYPES: TagType[] = ["passive", "active"];

// epc is merged in by the router from the linked AssetIdentifier at read time, not a column on
// RfidTag itself — see app/track_rfid/router.py's _tag_read_dict.
export interface RfidTag {
  id: string;
  asset_identifier_id: string;
  asset_id: string;
  tag_type: TagType;
  last_device_id: string | null;
  last_rssi: number | null;
  last_read_at: string | null;
  created_at: string;
  epc: string;
}

export interface RfidTagCreateInput {
  asset_id: string;
  epc: string;
  tag_type: TagType;
}

export interface RfidReadEvent {
  id: string;
  read_at: string;
  gateway_id: string;
  device_id: string;
  tag_epc: string;
  rssi: number | null;
  asset_id: string | null;
  tracking_event_id: string | null;
}

// GET /rfid/read-events' real server-side filters — confirmed directly against
// RfidReadEventRepository.list_filtered (track_rfid/repository.py:35-55): resolved, device_id,
// tag_epc, offset, limit. There is NO date-range param anywhere in the backend — read_at is
// only ever used for ordering (list_filtered's base query), never as a filter — so ReadEventsPage
// does not expose a date-range control (see its module docstring for the full explanation).
export interface ReadEventFilters {
  resolved?: boolean;
  device_id?: string;
  tag_epc?: string;
  offset?: number;
  limit?: number;
  // Index signature so this is assignable to api.get's params type.
  [key: string]: string | number | boolean | undefined;
}
