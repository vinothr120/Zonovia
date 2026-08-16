import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../core/apiClient";
import type {
  MaintenanceTicket,
  MaintenanceTicketCreateInput,
  MaintenanceTicketUpdateInput,
  RecordServiceInput,
  ScheduleDueReport,
  ServiceSchedule,
  ServiceScheduleCreateInput,
  ServiceScheduleUpdateInput,
  TicketCancelInput,
  TicketCompleteInput,
  TicketStatus,
  Warranty,
  WarrantyUpsertInput,
} from "./types";

// Reused, not redeclared — asset-name resolution for ticket lists and the schedules-due report
// is the exact same "batch of ["assets", id] queries over the shared cache" shape ReportSection
// already established for inventory.
export { assetLabel, useAssetsLookup } from "../inventory/hooks";

// -- tickets ------------------------------------------------------------------------------------

export interface TicketFilters {
  status?: TicketStatus;
  asset_id?: string;
  assigned_to?: string;
  lifecycle_state_key?: string;
  // Index signature so this is assignable to api.get's params type — every field above is
  // already string | undefined, so this widens nothing in practice.
  [key: string]: string | undefined;
}

// GET /maintenance/tickets has real server-side filters (unlike GET /assets) — no client-filter
// workaround needed. No server-side ordering though, so callers sort client-side.
export function useTickets(filters: TicketFilters) {
  return useQuery({
    queryKey: ["maintenance-tickets", filters],
    queryFn: () => api.get<MaintenanceTicket[]>("/maintenance/tickets", filters),
  });
}

export function useTicket(ticketId: string | undefined) {
  return useQuery({
    queryKey: ["maintenance-tickets", ticketId],
    queryFn: () => api.get<MaintenanceTicket>(`/maintenance/tickets/${ticketId}`),
    enabled: !!ticketId,
  });
}

/** Shared by create/update/start/complete/cancel — every one of them changes a ticket's row,
 * which both any filtered list and the detail query key are prefixed by, so a single
 * invalidateQueries call (react-query prefix-matches everything under ["maintenance-tickets"])
 * covers both — same convention as inventory/hooks.ts's useCycleListInvalidation. */
function useTicketListInvalidation() {
  const queryClient = useQueryClient();
  return () => void queryClient.invalidateQueries({ queryKey: ["maintenance-tickets"] });
}

export function useCreateTicket() {
  const invalidate = useTicketListInvalidation();
  return useMutation({
    mutationFn: (body: MaintenanceTicketCreateInput) => api.post<MaintenanceTicket>("/maintenance/tickets", body),
    onSuccess: invalidate,
  });
}

export function useUpdateTicket(ticketId: string) {
  const invalidate = useTicketListInvalidation();
  return useMutation({
    mutationFn: (body: MaintenanceTicketUpdateInput) => api.patch<MaintenanceTicket>(`/maintenance/tickets/${ticketId}`, body),
    onSuccess: invalidate,
  });
}

export function useStartTicket(ticketId: string) {
  const invalidate = useTicketListInvalidation();
  return useMutation({
    mutationFn: () => api.post<MaintenanceTicket>(`/maintenance/tickets/${ticketId}/start`),
    onSuccess: invalidate,
  });
}

export function useCompleteTicket(ticketId: string) {
  const invalidate = useTicketListInvalidation();
  return useMutation({
    mutationFn: (body: TicketCompleteInput) => api.post<MaintenanceTicket>(`/maintenance/tickets/${ticketId}/complete`, body),
    onSuccess: invalidate,
  });
}

export function useCancelTicket(ticketId: string) {
  const invalidate = useTicketListInvalidation();
  return useMutation({
    mutationFn: (body: TicketCancelInput) => api.post<MaintenanceTicket>(`/maintenance/tickets/${ticketId}/cancel`, body),
    onSuccess: invalidate,
  });
}

// -- warranty -----------------------------------------------------------------------------------

/** retry:false — a 404 here means "no warranty yet", a real and expected state the caller
 * (AssetWarrantySection) renders a create form for, not a transient failure worth react-query's
 * default 3 retries. */
export function useWarranty(assetId: string | undefined) {
  return useQuery({
    queryKey: ["maintenance-warranty", assetId],
    queryFn: () => api.get<Warranty>(`/assets/${assetId}/warranty`),
    enabled: !!assetId,
    retry: false,
  });
}

export function useUpsertWarranty(assetId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: WarrantyUpsertInput) => api.put<Warranty>(`/assets/${assetId}/warranty`, body),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["maintenance-warranty", assetId] }),
  });
}

// -- service schedules ----------------------------------------------------------------------------

// No server-side ordering on the per-asset schedule list — client-sorted by name, a UI
// compensating behavior (see AssetScheduleSection).
export function useSchedules(assetId: string | undefined) {
  return useQuery({
    queryKey: ["maintenance-schedules", assetId],
    queryFn: () => api.get<ServiceSchedule[]>("/maintenance/schedules", { asset_id: assetId }),
    enabled: !!assetId,
  });
}

function useScheduleListInvalidation(assetId: string) {
  const queryClient = useQueryClient();
  return () => void queryClient.invalidateQueries({ queryKey: ["maintenance-schedules", assetId] });
}

export function useCreateSchedule(assetId: string) {
  const invalidate = useScheduleListInvalidation(assetId);
  return useMutation({
    mutationFn: (body: ServiceScheduleCreateInput) => api.post<ServiceSchedule>("/maintenance/schedules", body),
    onSuccess: invalidate,
  });
}

export function useUpdateSchedule(assetId: string, scheduleId: string) {
  const invalidate = useScheduleListInvalidation(assetId);
  return useMutation({
    mutationFn: (body: ServiceScheduleUpdateInput) => api.patch<ServiceSchedule>(`/maintenance/schedules/${scheduleId}`, body),
    onSuccess: invalidate,
  });
}

export function useDeleteSchedule(assetId: string) {
  const invalidate = useScheduleListInvalidation(assetId);
  return useMutation({
    mutationFn: (scheduleId: string) => api.delete(`/maintenance/schedules/${scheduleId}`),
    onSuccess: invalidate,
  });
}

export function useRecordService(assetId: string, scheduleId: string) {
  const invalidate = useScheduleListInvalidation(assetId);
  return useMutation({
    mutationFn: (body: RecordServiceInput) => api.post<ServiceSchedule>(`/maintenance/schedules/${scheduleId}/record-service`, body),
    onSuccess: invalidate,
  });
}

// The only tenant-wide view onto schedules — server-sorted (next_due_at asc within each
// bucket), no client sort needed.
export function useScheduleDueReport() {
  return useQuery({
    queryKey: ["maintenance-schedules-due-report"],
    queryFn: () => api.get<ScheduleDueReport>("/maintenance/schedules/report"),
  });
}
