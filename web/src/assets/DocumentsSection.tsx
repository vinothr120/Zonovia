import { useRef, useState } from "react";
import type { ChangeEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, Trash2, Upload } from "lucide-react";
import { api, downloadFile } from "../core/apiClient";
import { apiErrorMessage, EmptyState, ErrorState, LoadingState } from "../core/ui/StateViews";
import { useToast } from "../core/ui/ToastContext";
import type { AssetDocument } from "./types";

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function DocumentsSection({ assetId, canManage }: { assetId: string; canManage: boolean }) {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const queryKey = ["asset-documents", assetId];
  const fileInputRef = useRef<HTMLInputElement>(null);

  const documentsQuery = useQuery({
    queryKey,
    queryFn: () => api.get<AssetDocument[]>(`/assets/${assetId}/documents`),
  });

  const [documentType, setDocumentType] = useState("");
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);

  const uploadDocument = useMutation({
    mutationFn: (file: File) => {
      const formData = new FormData();
      formData.append("upload", file);
      if (documentType.trim()) formData.append("document_type", documentType.trim());
      return api.post<AssetDocument>(`/assets/${assetId}/documents`, formData);
    },
    onSuccess: () => {
      setDocumentType("");
      setUploadError(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
      void queryClient.invalidateQueries({ queryKey });
      showToast("Document uploaded.", "success");
    },
    onError: (err) => setUploadError(apiErrorMessage(err, "Unable to upload document.")),
  });

  const deleteDocument = useMutation({
    mutationFn: (documentId: string) => api.delete(`/assets/${assetId}/documents/${documentId}`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey });
      showToast("Document deleted.", "success");
    },
    onError: (err) => showToast(apiErrorMessage(err, "Unable to delete document."), "error"),
  });

  function handleFileChange(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploadError(null);
    uploadDocument.mutate(file);
  }

  async function handleDownload(doc: AssetDocument) {
    setDownloadingId(doc.id);
    try {
      await downloadFile(`/assets/${assetId}/documents/${doc.id}/content`, {});
    } catch (err) {
      showToast(apiErrorMessage(err, "Unable to download document."), "error");
    } finally {
      setDownloadingId(null);
    }
  }

  function handleDelete(doc: AssetDocument) {
    if (window.confirm(`Delete "${doc.original_filename}"? This can't be undone.`)) {
      deleteDocument.mutate(doc.id);
    }
  }

  return (
    <div className="bg-white rounded-lg border border-slate-200 p-4">
      <h2 className="text-sm font-medium text-slate-700 mb-3">Documents</h2>

      {documentsQuery.isLoading && <LoadingState />}
      {documentsQuery.isError && (
        <ErrorState message={apiErrorMessage(documentsQuery.error, "Unable to load documents.")} onRetry={() => void documentsQuery.refetch()} />
      )}

      {documentsQuery.data && (
        <ul className="divide-y divide-slate-100 mb-3">
          {documentsQuery.data.map((doc) => (
            <li key={doc.id} className="py-2 flex items-center justify-between gap-3 text-sm">
              <div className="min-w-0">
                <p className="text-slate-900 truncate">{doc.original_filename}</p>
                <p className="text-xs text-slate-400">
                  {doc.document_type ? `${doc.document_type} · ` : ""}
                  {formatSize(doc.size_bytes)} · {new Date(doc.created_at).toLocaleDateString()}
                </p>
              </div>
              <div className="flex gap-1 shrink-0">
                <button
                  type="button"
                  aria-label={`Download ${doc.original_filename}`}
                  disabled={downloadingId === doc.id}
                  onClick={() => void handleDownload(doc)}
                  className="p-1.5 rounded-md text-slate-500 hover:bg-slate-100 hover:text-slate-700 disabled:opacity-60"
                >
                  <Download className="w-4 h-4" />
                </button>
                {canManage && (
                  <button
                    type="button"
                    aria-label={`Delete ${doc.original_filename}`}
                    disabled={deleteDocument.isPending}
                    onClick={() => handleDelete(doc)}
                    className="p-1.5 rounded-md text-slate-400 hover:bg-red-50 hover:text-red-600"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                )}
              </div>
            </li>
          ))}
          {documentsQuery.data.length === 0 && <EmptyState message="No documents yet." />}
        </ul>
      )}

      {canManage && (
        <div className="border-t border-slate-100 pt-3 space-y-2">
          {uploadError && <div className="text-red-600 text-xs">{uploadError}</div>}
          <div className="flex flex-wrap gap-2 items-center">
            <input
              value={documentType}
              onChange={(e) => setDocumentType(e.target.value)}
              placeholder="Document type (optional)"
              className="rounded-md border border-slate-300 px-2 py-1.5 text-sm min-w-[10rem]"
            />
            <label className="inline-flex items-center gap-1.5 text-sm bg-slate-800 text-white rounded-md px-3 py-1.5 cursor-pointer hover:bg-slate-900 has-[:disabled]:opacity-60 has-[:disabled]:cursor-not-allowed">
              <Upload className="w-4 h-4" />
              {uploadDocument.isPending ? "Uploading…" : "Upload file"}
              <input ref={fileInputRef} type="file" onChange={handleFileChange} disabled={uploadDocument.isPending} className="hidden" />
            </label>
          </div>
        </div>
      )}
    </div>
  );
}
