import { useMemo } from "react";
import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../core/apiClient";
import type {
  Device,
  DeviceCreateInput,
  DeviceGateway,
  DeviceGatewayCreateInput,
  DeviceGatewayCreateResponse,
  ReadEventFilters,
  RfidReadEvent,
  RfidTag,
  RfidTagCreateInput,
} from "./types";

const REFERENCE_STALE_TIME = 5 * 60 * 1000;

// -- device gateways ------------------------------------------------------------------------

// retry:false — GET /tracking/gateways requires tracking.manage_gateways with no separate
// *.view tier (see seed.py's comment on the Tenant Admin bundle), so a 403 here means
// "not a Tenant Admin," an expected steady state for Member/Viewer, not a transient failure
// worth react-query's default 3 retries — matters most for useDevicesLookup below, which calls
// this from surfaces Member/Viewer can actually reach.
export function useGateways() {
  return useQuery({
    queryKey: ["rfid-gateways"],
    queryFn: () => api.get<DeviceGateway[]>("/tracking/gateways"),
    retry: false,
  });
}

function useGatewayListInvalidation() {
  const queryClient = useQueryClient();
  return () => void queryClient.invalidateQueries({ queryKey: ["rfid-gateways"] });
}

export function useCreateGateway() {
  const invalidate = useGatewayListInvalidation();
  return useMutation({
    mutationFn: (body: DeviceGatewayCreateInput) => api.post<DeviceGatewayCreateResponse>("/tracking/gateways", body),
    onSuccess: invalidate,
  });
}

export function useRevokeGateway() {
  const invalidate = useGatewayListInvalidation();
  return useMutation({
    mutationFn: (gatewayId: string) => api.post<DeviceGateway>(`/tracking/gateways/${gatewayId}/revoke`),
    onSuccess: invalidate,
  });
}

// -- devices ----------------------------------------------------------------------------------

export function useGatewayDevices(gatewayId: string | undefined) {
  return useQuery({
    queryKey: ["rfid-gateway-devices", gatewayId],
    queryFn: () => api.get<Device[]>(`/tracking/gateways/${gatewayId}/devices`),
    enabled: !!gatewayId,
    retry: false,
  });
}

export function useRegisterDevice(gatewayId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: DeviceCreateInput) => api.post<Device>(`/tracking/gateways/${gatewayId}/devices`, body),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["rfid-gateway-devices", gatewayId] }),
  });
}

/** Resolves device names for ReadEventsPage's filter + result rows. There's no flat
 * list-all-devices endpoint or get-device-by-id endpoint — a Device only exists nested under
 * its DeviceGateway (GET /tracking/gateways/{id}/devices) — so this assembles the lookup map
 * itself: list gateways, then list devices per gateway, reusing the exact
 * ["rfid-gateways"]/["rfid-gateway-devices", id] query keys GatewaysListPage's inline expand
 * uses, so the two surfaces share one cache. Both calls require tracking.manage_gateways/
 * manage_devices (Tenant-Admin-only, see seed.py) — for Member/Viewer they 403 and are excluded
 * from the map, same "unknown, not a failure" posture as inventory/hooks.ts's
 * useAssetsLookup, so ReadEventsPage degrades to showing the raw device id rather than
 * breaking (see deviceLabel below). */
export function useDevicesLookup() {
  const gatewaysQuery = useGateways();
  const gateways = gatewaysQuery.data ?? [];

  const deviceResults = useQueries({
    queries: gateways.map((g) => ({
      queryKey: ["rfid-gateway-devices", g.id],
      queryFn: () => api.get<Device[]>(`/tracking/gateways/${g.id}/devices`),
      staleTime: REFERENCE_STALE_TIME,
      retry: false,
    })),
  });

  const map = useMemo(() => {
    const m = new Map<string, Device>();
    for (const r of deviceResults) {
      for (const d of r.data ?? []) m.set(d.id, d);
    }
    return m;
  }, [deviceResults]);

  return { map };
}

/** Resolved vendor/model (or device_type if neither is set) if present in the lookup map;
 * otherwise (still loading, or the lookup 403'd for a non-Tenant-Admin) a neutral fallback with
 * a truncated id — same convention as inventory/hooks.ts's assetLabel. */
export function deviceLabel(deviceId: string, map: Map<string, Device>): string {
  const d = map.get(deviceId);
  if (!d) return `Device (${deviceId.slice(0, 8)}…)`;
  return [d.vendor, d.model].filter(Boolean).join(" ") || d.device_type;
}

// -- rfid tags --------------------------------------------------------------------------------

/** retry:false — a 404 here means "no tag registered for this asset yet," a real and expected
 * state AssetRfidTagSection renders a register form for, same convention as
 * maintenance/hooks.ts's useWarranty. */
export function useAssetTag(assetId: string | undefined) {
  return useQuery({
    queryKey: ["rfid-tags", assetId],
    queryFn: () => api.get<RfidTag>(`/rfid/tags/${assetId}`),
    enabled: !!assetId,
    retry: false,
  });
}

export interface TagListFilters {
  offset?: number;
  limit?: number;
  [key: string]: number | undefined;
}

// GET /rfid/tags returns a plain array (no `total`, same as GET /inventory/cycles) — fixed at
// the default offset=0/limit=20 unless the caller overrides, a real backend limitation
// RfidTagsListPage surfaces rather than papering over, same convention as
// inventory/CyclesListPage.
export function useTags(filters: TagListFilters) {
  return useQuery({
    queryKey: ["rfid-tags", "list", filters],
    queryFn: () => api.get<RfidTag[]>("/rfid/tags", filters),
  });
}

/** Shared by both registration entry points (AssetRfidTagSection, RfidTagsListPage's
 * AssetPicker-driven form) — invalidates both the per-asset query and the tenant-wide list via
 * one prefix match on ["rfid-tags"], same convention as maintenance/hooks.ts's
 * useTicketListInvalidation. */
export function useRegisterTag() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: RfidTagCreateInput) => api.post<RfidTag>("/rfid/tags", body),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["rfid-tags"] }),
  });
}

// -- read events --------------------------------------------------------------------------------

// No `total` in the response either (confirmed against RfidReadEventRepository.list_filtered) —
// ReadEventsPage's pager is Prev/Next only, disabling Next once a page comes back shorter than
// the requested limit, since there's no count to know a further page exists ahead of time.
export function useReadEvents(filters: ReadEventFilters) {
  return useQuery({
    queryKey: ["rfid-read-events", filters],
    queryFn: () => api.get<RfidReadEvent[]>("/rfid/read-events", filters),
  });
}
