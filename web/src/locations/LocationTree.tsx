import { useMemo } from "react";
import { MapPin, Pencil, Plus, Trash2 } from "lucide-react";
import { EmptyState } from "../core/ui/StateViews";
import type { AssetLocation } from "./types";

interface LocationTreeProps {
  locations: AssetLocation[];
  canManage: boolean;
  onAddChild: (parentId: string) => void;
  onEdit: (location: AssetLocation) => void;
  onDelete: (location: AssetLocation) => void;
}

/** Recursive tree rendered from the already-fully-resident flat location list (see
 * useAssetLocations) — all nodes expanded by default since there's no lazy-load benefit when
 * the whole tree is already in memory. */
export function LocationTree({ locations, canManage, onAddChild, onEdit, onDelete }: LocationTreeProps) {
  const byParent = useMemo(() => {
    const grouped = new Map<string | null, AssetLocation[]>();
    for (const loc of locations) {
      const key = loc.parent_location_id;
      const siblings = grouped.get(key) ?? [];
      siblings.push(loc);
      grouped.set(key, siblings);
    }
    for (const siblings of grouped.values()) {
      siblings.sort((a, b) => a.sort_order - b.sort_order || a.name.localeCompare(b.name));
    }
    return grouped;
  }, [locations]);

  const roots = byParent.get(null) ?? [];
  if (roots.length === 0) return <EmptyState message="No locations yet." />;

  return (
    <ul className="space-y-0.5">
      {roots.map((root) => (
        <LocationNode key={root.id} location={root} byParent={byParent} depth={0} canManage={canManage} onAddChild={onAddChild} onEdit={onEdit} onDelete={onDelete} />
      ))}
    </ul>
  );
}

function LocationNode({
  location,
  byParent,
  depth,
  canManage,
  onAddChild,
  onEdit,
  onDelete,
}: {
  location: AssetLocation;
  byParent: Map<string | null, AssetLocation[]>;
  depth: number;
  canManage: boolean;
  onAddChild: (parentId: string) => void;
  onEdit: (location: AssetLocation) => void;
  onDelete: (location: AssetLocation) => void;
}) {
  const children = byParent.get(location.id) ?? [];

  return (
    <li>
      <div className="flex items-center gap-2 py-1.5 px-2 rounded-md hover:bg-slate-50 group" style={{ paddingLeft: `${depth * 1.25 + 0.5}rem` }}>
        <MapPin className="w-4 h-4 text-slate-400 shrink-0" />
        <span className="text-sm text-slate-900">{location.name}</span>
        {location.location_type && <span className="text-xs text-slate-400">({location.location_type})</span>}
        {canManage && (
          <div className="ml-auto flex gap-1 opacity-0 group-hover:opacity-100 focus-within:opacity-100 shrink-0">
            <button type="button" aria-label={`Add child location under ${location.name}`} title="Add child" onClick={() => onAddChild(location.id)} className="p-1 rounded-md text-slate-500 hover:bg-slate-200 hover:text-slate-700">
              <Plus className="w-3.5 h-3.5" />
            </button>
            <button type="button" aria-label={`Edit ${location.name}`} onClick={() => onEdit(location)} className="p-1 rounded-md text-slate-500 hover:bg-slate-200 hover:text-slate-700">
              <Pencil className="w-3.5 h-3.5" />
            </button>
            <button type="button" aria-label={`Delete ${location.name}`} onClick={() => onDelete(location)} className="p-1 rounded-md text-slate-500 hover:bg-red-50 hover:text-red-600">
              <Trash2 className="w-3.5 h-3.5" />
            </button>
          </div>
        )}
      </div>
      {children.length > 0 && (
        <ul>
          {children.map((child) => (
            <LocationNode key={child.id} location={child} byParent={byParent} depth={depth + 1} canManage={canManage} onAddChild={onAddChild} onEdit={onEdit} onDelete={onDelete} />
          ))}
        </ul>
      )}
    </li>
  );
}
