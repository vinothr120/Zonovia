// Hand-written to mirror backend/app/maintenance/schemas.py's Maintenance*/Warranty*/
// ServiceSchedule*/ScheduleDueReport models exactly — no codegen in this project.

// Guard-clause-validated fixed workflow — mirrors app.maintenance.models._TICKET_STATUSES.
export type TicketStatus = "open" | "in_progress" | "completed" | "cancelled";

// Mirrors app.maintenance.models._TICKET_PRIORITIES exactly.
export type TicketPriority = "low" | "medium" | "high" | "urgent";

export const TICKET_PRIORITIES: TicketPriority[] = ["low", "medium", "high", "urgent"];

export interface MaintenanceTicket {
  id: string;
  asset_id: string;
  service_schedule_id: string | null;
  title: string;
  description: string | null;
  status: TicketStatus;
  priority: TicketPriority | null;
  reported_by: string | null;
  assigned_to: string | null;
  resolved_at: string | null;
  resolution_note: string | null;
  cost: string | null;
  created_at: string;
}

export interface MaintenanceTicketCreateInput {
  asset_id: string;
  service_schedule_id?: string | null;
  title: string;
  description?: string | null;
  priority?: TicketPriority | null;
  assigned_to?: string | null;
  cost?: string | null;
}

export interface MaintenanceTicketUpdateInput {
  title?: string;
  description?: string | null;
  priority?: TicketPriority | null;
  assigned_to?: string | null;
  cost?: string | null;
}

export interface TicketCancelInput {
  note?: string | null;
}

export interface TicketCompleteInput {
  resolution_note?: string | null;
}

// is_expired/days_remaining are computed server-side at read time (never stored) — render
// exactly what the API returns, never recompute client-side.
export interface Warranty {
  id: string;
  asset_id: string;
  vendor_id: string | null;
  warranty_type: string | null;
  start_date: string;
  end_date: string;
  terms: string | null;
  is_expired: boolean;
  days_remaining: number;
  updated_at: string;
}

export interface WarrantyUpsertInput {
  vendor_id?: string | null;
  warranty_type?: string | null;
  start_date: string;
  end_date: string;
  terms?: string | null;
}

// next_due_at/is_overdue are computed server-side at read time (never stored) — same
// "computed, not stored" convention as Warranty above.
export interface ServiceSchedule {
  id: string;
  asset_id: string;
  name: string;
  interval_days: number;
  last_serviced_at: string | null;
  next_due_at: string;
  is_overdue: boolean;
  created_at: string;
}

export interface ServiceScheduleCreateInput {
  asset_id: string;
  name: string;
  interval_days: number;
}

export interface ServiceScheduleUpdateInput {
  name?: string;
  interval_days?: number;
}

// serviced_at omitted (not sent as null/empty) lets the backend apply its own "defaults to
// today" rule — see AssetScheduleSection's record-service mini-form.
export interface RecordServiceInput {
  serviced_at?: string;
}

// GET /maintenance/schedules/report — server-sorted (next_due_at asc within each bucket), no
// client sort needed.
export interface ScheduleDueReport {
  overdue: ServiceSchedule[];
  upcoming: ServiceSchedule[];
}
