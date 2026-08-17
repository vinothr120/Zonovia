import { useCallback, useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { BarcodeFormat, DecodeHintType, NotFoundException } from "@zxing/library";
import { BrowserMultiFormatReader } from "@zxing/browser";
import type { IScannerControls } from "@zxing/browser";
import { Camera, CircleCheck, ScanLine, Video } from "lucide-react";
import { useAuth } from "../auth/AuthContext";
import { api, ApiError } from "../core/apiClient";
import type { IdentifierType, ScanRequest, ScanResponse, TrackingEvent } from "./types";
import { IDENTIFIER_TYPES } from "./types";

/** QR + the common 1D formats called out in the plan. Narrowing the search space with
 * DecodeHintType.POSSIBLE_FORMATS both speeds up decoding and avoids false positives. */
const POSSIBLE_FORMATS = [
  BarcodeFormat.QR_CODE,
  BarcodeFormat.CODE_128,
  BarcodeFormat.EAN_13,
  BarcodeFormat.UPC_A,
  BarcodeFormat.CODE_39,
];

function formatToIdentifierType(format: BarcodeFormat): IdentifierType {
  return format === BarcodeFormat.QR_CODE ? "QR" : "BARCODE";
}

function errorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 404) return "No asset found for that code.";
    if (err.status === 422) return err.message || "That code isn't a supported identifier.";
    if (err.status === 403) return err.message || "You don't have permission to record this scan.";
    return err.message || "Something went wrong. Please try again.";
  }
  return "Something went wrong. Please try again.";
}

export function ScanPage() {
  const { me } = useAuth();
  const canScan = me?.permissions.includes("tracking.scan") ?? false;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">Scan an asset</h1>
        <p className="text-sm text-slate-500 mt-1">Point the camera at a QR code or barcode, or enter a code manually.</p>
      </div>
      {canScan ? <Scanner /> : <ReadOnlyNotice />}
    </div>
  );
}

function ReadOnlyNotice() {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-6 text-center">
      <ScanLine className="w-8 h-8 mx-auto text-slate-300 mb-3" />
      <h2 className="text-slate-900 font-semibold mb-1">Scanning isn't enabled for your account</h2>
      <p className="text-sm text-slate-500">
        You can view tracking history but don't have permission to scan assets. Contact a tenant admin if you
        believe this is a mistake.
      </p>
    </div>
  );
}

type Phase = "idle" | "scanning" | "resolved";

function Scanner() {
  const videoRef = useRef<HTMLVideoElement>(null);
  const readerRef = useRef<BrowserMultiFormatReader | null>(null);
  const controlsRef = useRef<IScannerControls | null>(null);
  const processingRef = useRef(false);

  const [phase, setPhase] = useState<Phase>("idle");
  const [cameraError, setCameraError] = useState<string | null>(null);
  const [manualType, setManualType] = useState<IdentifierType>("QR");
  const [manualValue, setManualValue] = useState("");
  const [note, setNote] = useState("");
  const [result, setResult] = useState<ScanResponse | null>(null);
  const [scanError, setScanError] = useState<string | null>(null);

  const scanMutation = useMutation({
    mutationFn: (body: ScanRequest) => api.post<ScanResponse>("/tracking/scan", body),
    onSuccess: (data) => {
      setResult(data);
      setScanError(null);
      setPhase("resolved");
    },
    onError: (err: unknown) => {
      setScanError(errorMessage(err));
    },
  });

  const eventsQuery = useQuery({
    queryKey: ["tracking-events", result?.asset.id],
    queryFn: () => api.get<TrackingEvent[]>(`/assets/${result!.asset.id}/tracking-events`),
    enabled: phase === "resolved" && !!result?.asset.id,
  });

  const stopCamera = useCallback(() => {
    controlsRef.current?.stop();
    controlsRef.current = null;
  }, []);

  useEffect(() => {
    // Release the camera stream on unmount / route change.
    return () => stopCamera();
  }, [stopCamera]);

  const submitScan = useCallback(
    (body: ScanRequest) => {
      setScanError(null);
      scanMutation.mutate(body);
    },
    [scanMutation],
  );

  const handleDecoded = useCallback(
    (rawValue: string, format: BarcodeFormat) => {
      // The continuous scan loop can fire a decode on more than one frame in flight before
      // stop() takes effect — guard against submitting the same read twice.
      if (processingRef.current) return;
      processingRef.current = true;
      stopCamera();
      setPhase("idle");
      submitScan({ identifier_type: formatToIdentifierType(format), value: rawValue, note: note.trim() || undefined });
      // Reset the guard on the next tick; a fresh scan session only starts once the user
      // presses "Start camera" again, by which point this no longer matters.
      setTimeout(() => {
        processingRef.current = false;
      }, 0);
    },
    [note, stopCamera, submitScan],
  );

  const startCamera = useCallback(async () => {
    setCameraError(null);
    setScanError(null);
    setResult(null);
    setPhase("scanning");
    if (!readerRef.current) {
      const hints = new Map<DecodeHintType, unknown>();
      hints.set(DecodeHintType.POSSIBLE_FORMATS, POSSIBLE_FORMATS);
      readerRef.current = new BrowserMultiFormatReader(hints);
    }
    if (!videoRef.current) {
      setPhase("idle");
      return;
    }
    try {
      const controls = await readerRef.current.decodeFromVideoDevice(undefined, videoRef.current, (decodeResult, err) => {
        if (decodeResult) {
          handleDecoded(decodeResult.getText(), decodeResult.getBarcodeFormat());
        } else if (err && !(err instanceof NotFoundException)) {
          // NotFoundException fires on every frame with no code in view — expected noise
          // during continuous scanning, not a real error. Anything else is worth a log.
          console.debug("zxing decode error", err);
        }
      });
      controlsRef.current = controls;
    } catch (err) {
      setPhase("idle");
      setCameraError(err instanceof Error ? err.message : "Couldn't access the camera. Check permissions and try again.");
    }
  }, [handleDecoded]);

  function handleStopCamera() {
    stopCamera();
    setPhase("idle");
  }

  function handleManualSubmit(e: FormEvent) {
    e.preventDefault();
    const value = manualValue.trim();
    if (!value) return;
    stopCamera();
    setPhase("idle");
    submitScan({ identifier_type: manualType, value, note: note.trim() || undefined });
  }

  function handleScanAgain() {
    setResult(null);
    setScanError(null);
    setManualValue("");
    setPhase("idle");
  }

  if (phase === "resolved" && result) {
    return <ResolvedView result={result} events={eventsQuery.data} eventsLoading={eventsQuery.isLoading} eventsError={eventsQuery.isError} onScanAgain={handleScanAgain} />;
  }

  return (
    <div className="space-y-4">
      {scanError && (
        <div className="rounded-md bg-red-50 border border-red-200 text-red-700 text-sm px-3 py-2">{scanError}</div>
      )}

      <div className="rounded-xl border border-slate-200 bg-white p-4">
        <div className="aspect-video w-full rounded-lg bg-slate-900 overflow-hidden relative flex items-center justify-center">
          <video ref={videoRef} className="w-full h-full object-cover" muted playsInline autoPlay />
          {phase !== "scanning" && (
            <div className="absolute inset-0 flex items-center justify-center">
              <Video className="w-10 h-10 text-slate-600" />
            </div>
          )}
        </div>
        {cameraError && <p className="text-sm text-red-600 mt-2">{cameraError}</p>}
        <div className="mt-3 flex justify-center">
          {phase === "scanning" ? (
            <button
              type="button"
              onClick={handleStopCamera}
              className="inline-flex items-center gap-2 rounded-md border border-slate-300 text-slate-700 text-sm font-medium px-4 py-2 hover:bg-slate-50 transition-colors"
            >
              Stop camera
            </button>
          ) : (
            <button
              type="button"
              onClick={() => void startCamera()}
              disabled={scanMutation.isPending}
              className="inline-flex items-center gap-2 rounded-md bg-[var(--accent)] text-white text-sm font-medium px-4 py-2 hover:bg-[var(--accent-dark)] disabled:opacity-60 disabled:cursor-not-allowed transition-colors"
            >
              <Camera className="w-4 h-4" />
              Start camera
            </button>
          )}
        </div>
      </div>

      <div className="rounded-xl border border-slate-200 bg-white p-4">
        <h2 className="text-sm font-medium text-slate-700 mb-3">Or enter a code manually</h2>
        <form onSubmit={handleManualSubmit} className="space-y-3">
          <div className="flex gap-2">
            <select
              value={manualType}
              onChange={(e) => setManualType(e.target.value as IdentifierType)}
              className="rounded-md border border-slate-300 px-2 py-2 text-sm bg-white"
            >
              {IDENTIFIER_TYPES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
            <input
              type="text"
              value={manualValue}
              onChange={(e) => setManualValue(e.target.value)}
              placeholder="Enter identifier value"
              className="flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[var(--accent)] focus:border-[var(--accent)]"
            />
          </div>
          <input
            type="text"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Note (optional)"
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[var(--accent)] focus:border-[var(--accent)]"
          />
          <button
            type="submit"
            disabled={scanMutation.isPending || !manualValue.trim()}
            className="w-full rounded-md bg-slate-800 text-white text-sm font-medium py-2 hover:bg-slate-900 disabled:opacity-60 disabled:cursor-not-allowed transition-colors"
          >
            {scanMutation.isPending ? "Submitting…" : "Submit code"}
          </button>
        </form>
      </div>
    </div>
  );
}

function ResolvedView({
  result,
  events,
  eventsLoading,
  eventsError,
  onScanAgain,
}: {
  result: ScanResponse;
  events: TrackingEvent[] | undefined;
  eventsLoading: boolean;
  eventsError: boolean;
  onScanAgain: () => void;
}) {
  const { asset, tracking_event: trackingEvent } = result;
  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4 flex items-start gap-3">
        <CircleCheck className="w-5 h-5 text-emerald-600 shrink-0 mt-0.5" />
        <div className="min-w-0">
          <p className="text-sm font-medium text-emerald-900">Scan recorded</p>
          <p className="text-sm text-emerald-700">
            {asset.name} · recorded {new Date(trackingEvent.occurred_at).toLocaleString()}
          </p>
        </div>
      </div>

      <div className="rounded-xl border border-slate-200 bg-white p-4">
        <h2 className="text-sm font-medium text-slate-500 mb-3">Asset</h2>
        <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
          <dt className="text-slate-500">Name</dt>
          <dd className="text-slate-900 font-medium">{asset.name}</dd>
          <dt className="text-slate-500">Asset ID</dt>
          <dd className="text-slate-900 font-mono text-xs break-all">{asset.id}</dd>
          <dt className="text-slate-500">Location</dt>
          <dd className="text-slate-900">{asset.current_location_id ?? "—"}</dd>
          <dt className="text-slate-500">Lifecycle state</dt>
          <dd className="text-slate-900">{asset.current_lifecycle_state_id ?? "—"}</dd>
          <dt className="text-slate-500">Custodian</dt>
          <dd className="text-slate-900">{asset.current_custodian_id ?? "—"}</dd>
        </dl>
      </div>

      <div className="rounded-xl border border-slate-200 bg-white p-4">
        <h2 className="text-sm font-medium text-slate-500 mb-3">Recent tracking events</h2>
        {eventsLoading && <p className="text-sm text-slate-400">Loading history…</p>}
        {eventsError && <p className="text-sm text-red-600">Couldn't load tracking history.</p>}
        {!eventsLoading && !eventsError && (!events || events.length === 0) && (
          <p className="text-sm text-slate-400">No prior tracking events for this asset.</p>
        )}
        {events && events.length > 0 && (
          <ul className="divide-y divide-slate-100">
            {events.map((event) => (
              <li key={event.id} className="py-2 text-sm flex items-center justify-between gap-3">
                <span className="text-slate-700">
                  {event.event_type} <span className="text-slate-400">via {event.provider_type}</span>
                </span>
                <span className="text-slate-400 text-xs shrink-0">{new Date(event.occurred_at).toLocaleString()}</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      <button
        type="button"
        onClick={onScanAgain}
        className="w-full rounded-md bg-[var(--accent)] text-white text-sm font-medium py-2 hover:bg-[var(--accent-dark)] transition-colors"
      >
        Scan again
      </button>
    </div>
  );
}
