import { ChevronLeft, ChevronRight } from "lucide-react";

/** Simple page-number pager for server-paginated lists. `total`/`pageSize` come straight off
 * the envelope's `meta` (see apiRequestWithMeta) — callers compute pageCount themselves so this
 * component stays a dumb view. */
export function Pagination({
  page,
  pageSize,
  total,
  onPageChange,
}: {
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
}) {
  const pageCount = Math.max(1, Math.ceil(total / pageSize));
  if (pageCount <= 1) return null;

  const rangeStart = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const rangeEnd = Math.min(page * pageSize, total);

  return (
    <div className="flex items-center justify-between gap-3 text-sm text-slate-500 py-2">
      <span>
        Showing {rangeStart}–{rangeEnd} of {total}
      </span>
      <div className="flex items-center gap-1">
        <button
          type="button"
          onClick={() => onPageChange(page - 1)}
          disabled={page <= 1}
          aria-label="Previous page"
          className="inline-flex items-center rounded-md border border-slate-300 p-1.5 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-slate-50"
        >
          <ChevronLeft className="w-4 h-4" />
        </button>
        <span className="px-2 text-slate-700">
          Page {page} of {pageCount}
        </span>
        <button
          type="button"
          onClick={() => onPageChange(page + 1)}
          disabled={page >= pageCount}
          aria-label="Next page"
          className="inline-flex items-center rounded-md border border-slate-300 p-1.5 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-slate-50"
        >
          <ChevronRight className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
