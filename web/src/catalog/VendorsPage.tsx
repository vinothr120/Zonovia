import { useState } from "react";
import type { FormEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Pencil, Trash2 } from "lucide-react";
import { useAuth } from "../auth/AuthContext";
import { api } from "../core/apiClient";
import { apiErrorMessage, EmptyState, ErrorState, LoadingState } from "../core/ui/StateViews";
import { useToast } from "../core/ui/ToastContext";
import { useVendors } from "./hooks";
import type { Vendor, VendorInput } from "./types";

export function VendorsPage() {
  const { me } = useAuth();
  const canManage = me?.permissions.includes("asset_catalog.manage") ?? false;
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const vendorsQuery = useVendors();

  const [name, setName] = useState("");
  const [contactName, setContactName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [createError, setCreateError] = useState<string | null>(null);

  const createVendor = useMutation({
    mutationFn: (body: VendorInput) => api.post<Vendor>("/vendors", body),
    onSuccess: () => {
      setName("");
      setContactName("");
      setEmail("");
      setPhone("");
      setCreateError(null);
      void queryClient.invalidateQueries({ queryKey: ["vendors"] });
      showToast("Vendor created.", "success");
    },
    onError: (err) => setCreateError(apiErrorMessage(err, "Unable to create vendor.")),
  });

  function handleCreate(e: FormEvent) {
    e.preventDefault();
    setCreateError(null);
    createVendor.mutate({
      name: name.trim(),
      contact_name: contactName.trim() || undefined,
      email: email.trim() || undefined,
      phone: phone.trim() || undefined,
    });
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">Vendors</h1>
        <p className="text-sm text-slate-500 mt-1">Suppliers assets can be purchased from.</p>
      </div>

      {canManage && (
        <form onSubmit={handleCreate} className="bg-white rounded-lg border border-slate-200 p-4 space-y-3 max-w-2xl">
          <h2 className="text-sm font-medium text-slate-700">Add vendor</h2>
          {createError && <div className="rounded-md bg-red-50 border border-red-200 text-red-700 text-xs px-3 py-2">{createError}</div>}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <input required placeholder="Name" value={name} onChange={(e) => setName(e.target.value)} className="rounded-md border border-slate-300 px-3 py-2 text-sm" />
            <input placeholder="Contact name" value={contactName} onChange={(e) => setContactName(e.target.value)} className="rounded-md border border-slate-300 px-3 py-2 text-sm" />
            <input placeholder="Email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} className="rounded-md border border-slate-300 px-3 py-2 text-sm" />
            <input placeholder="Phone" value={phone} onChange={(e) => setPhone(e.target.value)} className="rounded-md border border-slate-300 px-3 py-2 text-sm" />
          </div>
          <button
            type="submit"
            disabled={createVendor.isPending}
            className="rounded-md bg-[var(--accent)] text-white text-sm font-medium px-4 py-2 hover:bg-[var(--accent-dark)] disabled:opacity-60"
          >
            {createVendor.isPending ? "Adding…" : "Add vendor"}
          </button>
        </form>
      )}

      {vendorsQuery.isLoading && <LoadingState />}
      {vendorsQuery.isError && (
        <ErrorState message={apiErrorMessage(vendorsQuery.error, "Unable to load vendors.")} onRetry={() => void vendorsQuery.refetch()} />
      )}

      {vendorsQuery.data && (
        <div className="bg-white rounded-lg border border-slate-200 overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-slate-500 border-b border-slate-200 bg-slate-50">
                <th className="px-4 py-2 font-medium">Name</th>
                <th className="px-4 py-2 font-medium">Contact</th>
                <th className="px-4 py-2 font-medium">Email</th>
                <th className="px-4 py-2 font-medium">Phone</th>
                {canManage && <th className="px-4 py-2 font-medium"></th>}
              </tr>
            </thead>
            <tbody>
              {vendorsQuery.data.map((v) => (
                <VendorRow key={v.id} vendor={v} canManage={canManage} />
              ))}
              {vendorsQuery.data.length === 0 && (
                <tr>
                  <td colSpan={canManage ? 5 : 4}>
                    <EmptyState message="No vendors yet." />
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function VendorRow({ vendor, canManage }: { vendor: Vendor; canManage: boolean }) {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(vendor.name);
  const [contactName, setContactName] = useState(vendor.contact_name ?? "");
  const [email, setEmail] = useState(vendor.email ?? "");
  const [phone, setPhone] = useState(vendor.phone ?? "");
  const [error, setError] = useState<string | null>(null);

  const updateVendor = useMutation({
    mutationFn: (body: VendorInput) => api.patch<Vendor>(`/vendors/${vendor.id}`, body),
    onSuccess: () => {
      setEditing(false);
      setError(null);
      void queryClient.invalidateQueries({ queryKey: ["vendors"] });
      showToast("Vendor updated.", "success");
    },
    onError: (err) => setError(apiErrorMessage(err, "Unable to update vendor.")),
  });

  const deleteVendor = useMutation({
    mutationFn: () => api.delete(`/vendors/${vendor.id}`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["vendors"] });
      showToast("Vendor deleted.", "success");
    },
    onError: (err) => showToast(apiErrorMessage(err, "Unable to delete vendor."), "error"),
  });

  function handleDelete() {
    if (window.confirm(`Delete vendor "${vendor.name}"? This can't be undone.`)) {
      deleteVendor.mutate();
    }
  }

  if (editing) {
    return (
      <tr className="border-b border-slate-100 last:border-0 align-top">
        <td className="px-4 py-2" colSpan={5}>
          <div className="flex flex-col sm:flex-row gap-2 items-start sm:items-center flex-wrap">
            {error && <div className="text-red-600 text-xs w-full">{error}</div>}
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Name" className="rounded-md border border-slate-300 px-2 py-1 text-sm" />
            <input value={contactName} onChange={(e) => setContactName(e.target.value)} placeholder="Contact" className="rounded-md border border-slate-300 px-2 py-1 text-sm" />
            <input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Email" className="rounded-md border border-slate-300 px-2 py-1 text-sm" />
            <input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="Phone" className="rounded-md border border-slate-300 px-2 py-1 text-sm" />
            <div className="flex gap-2 shrink-0">
              <button
                type="button"
                disabled={updateVendor.isPending}
                onClick={() =>
                  updateVendor.mutate({
                    name: name.trim(),
                    contact_name: contactName.trim() || undefined,
                    email: email.trim() || undefined,
                    phone: phone.trim() || undefined,
                  })
                }
                className="text-xs bg-[var(--accent)] text-white rounded-md px-2 py-1 disabled:opacity-60"
              >
                {updateVendor.isPending ? "Saving…" : "Save"}
              </button>
              <button type="button" onClick={() => setEditing(false)} className="text-xs text-slate-500">
                Cancel
              </button>
            </div>
          </div>
        </td>
      </tr>
    );
  }

  return (
    <tr className="border-b border-slate-100 last:border-0">
      <td className="px-4 py-2 text-slate-900">{vendor.name}</td>
      <td className="px-4 py-2 text-slate-500">{vendor.contact_name || "—"}</td>
      <td className="px-4 py-2 text-slate-500">{vendor.email || "—"}</td>
      <td className="px-4 py-2 text-slate-500">{vendor.phone || "—"}</td>
      {canManage && (
        <td className="px-4 py-2">
          <div className="flex gap-1 justify-end">
            <button type="button" aria-label="Edit vendor" onClick={() => setEditing(true)} className="p-1.5 rounded-md text-slate-500 hover:bg-slate-100 hover:text-slate-700">
              <Pencil className="w-4 h-4" />
            </button>
            <button type="button" aria-label="Delete vendor" onClick={handleDelete} className="p-1.5 rounded-md text-slate-500 hover:bg-red-50 hover:text-red-600">
              <Trash2 className="w-4 h-4" />
            </button>
          </div>
        </td>
      )}
    </tr>
  );
}
