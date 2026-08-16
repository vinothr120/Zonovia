import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

import '../auth/auth_provider.dart';
import '../core/api_client.dart';
import '../core/models.dart';
import '../shared/widgets.dart';

/// New screen, no sibling (SchoolAssist/CMS) precedent — structurally mirrors
/// web/src/tracking/ScanPage.tsx: a permission gate on 'tracking.scan', then a
/// camera view + manual-entry fallback, resolving to an asset card and recent
/// tracking-events list. Error strings for 404/422/403 are copied verbatim from
/// ScanPage.tsx's errorMessage() branches so both clients read identically.
const List<BarcodeFormat> _possibleFormats = [
  BarcodeFormat.qrCode,
  BarcodeFormat.code128,
  BarcodeFormat.ean13,
  BarcodeFormat.upcA,
  BarcodeFormat.code39,
];

String _identifierTypeFor(BarcodeFormat format) => format == BarcodeFormat.qrCode ? 'QR' : 'BARCODE';

/// Mirrors ScanPage.tsx's errorMessage(err).
String _errorMessage(Object err) {
  if (err is ApiException) {
    if (err.status == 404) return 'No asset found for that code.';
    if (err.status == 422) return err.message.isNotEmpty ? err.message : "That code isn't a supported identifier.";
    if (err.status == 403) {
      return err.message.isNotEmpty ? err.message : "You don't have permission to record this scan.";
    }
    return err.message.isNotEmpty ? err.message : 'Something went wrong. Please try again.';
  }
  return 'Something went wrong. Please try again.';
}

class ScanScreen extends StatelessWidget {
  const ScanScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final me = AuthProvider.instance.me;
    final canScan = me?.permissions.contains('tracking.scan') ?? false;
    return Scaffold(
      appBar: AppBar(
        title: const Text('Scan an asset'),
        actions: [
          IconButton(
            icon: const Icon(Icons.logout),
            tooltip: 'Sign out',
            onPressed: () => AuthProvider.instance.logout(),
          ),
        ],
      ),
      body: SafeArea(
        child: canScan ? const _Scanner() : const _ReadOnlyNotice(),
      ),
    );
  }
}

class _ReadOnlyNotice extends StatelessWidget {
  const _ReadOnlyNotice();

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.qr_code_scanner, size: 40, color: Colors.grey.shade400),
            const SizedBox(height: 12),
            const Text(
              "Scanning isn't enabled for your account",
              textAlign: TextAlign.center,
              style: TextStyle(fontWeight: FontWeight.w600),
            ),
            const SizedBox(height: 8),
            Text(
              'You can view tracking history but don\'t have permission to scan assets. '
              'Contact a tenant admin if you believe this is a mistake.',
              textAlign: TextAlign.center,
              style: TextStyle(color: Colors.grey.shade600),
            ),
          ],
        ),
      ),
    );
  }
}

enum _Phase { idle, scanning, resolved }

class _Scanner extends StatefulWidget {
  const _Scanner();

  @override
  State<_Scanner> createState() => _ScannerState();
}

class _ScannerState extends State<_Scanner> {
  final _controller = MobileScannerController(formats: _possibleFormats, autoStart: false);
  final _manualValueController = TextEditingController();
  final _noteController = TextEditingController();

  _Phase _phase = _Phase.idle;
  bool _processing = false;
  bool _submitting = false;
  String _manualType = 'QR';
  String? _cameraError;
  String? _scanError;

  ScanResponse? _result;
  List<TrackingEventRead>? _events;
  bool _eventsLoading = false;
  bool _eventsError = false;

  @override
  void dispose() {
    _controller.dispose();
    _manualValueController.dispose();
    _noteController.dispose();
    super.dispose();
  }

  Future<void> _startCamera() async {
    setState(() {
      _cameraError = null;
      _scanError = null;
      _result = null;
      _phase = _Phase.scanning;
    });
    try {
      await _controller.start();
    } catch (err) {
      setState(() {
        _phase = _Phase.idle;
        _cameraError = "Couldn't access the camera. Check permissions and try again.";
      });
    }
  }

  Future<void> _stopCamera() async {
    try {
      await _controller.stop();
    } catch (_) {
      // best-effort — camera may already be stopped
    }
  }

  void _handleStopCamera() {
    _stopCamera();
    setState(() => _phase = _Phase.idle);
  }

  void _handleDetect(BarcodeCapture capture) {
    // The continuous scan loop can fire a detect on more than one frame in
    // flight before stop() takes effect — guard against a double submit.
    if (_processing) return;
    final barcode = capture.barcodes.isNotEmpty ? capture.barcodes.first : null;
    final rawValue = barcode?.rawValue;
    if (barcode == null || rawValue == null) return;
    _processing = true;
    _stopCamera();
    setState(() => _phase = _Phase.idle);
    _submitScan(_identifierTypeFor(barcode.format), rawValue);
    _processing = false;
  }

  Future<void> _submitScan(String identifierType, String value) async {
    setState(() {
      _scanError = null;
      _submitting = true;
    });
    try {
      final note = _noteController.text.trim();
      final data = await api.post<Map<String, dynamic>>('/tracking/scan', {
        'identifier_type': identifierType,
        'value': value,
        if (note.isNotEmpty) 'note': note,
      });
      final result = ScanResponse.fromJson(data);
      setState(() {
        _result = result;
        _scanError = null;
        _phase = _Phase.resolved;
        _submitting = false;
      });
      _loadEvents(result.asset.id);
    } catch (err) {
      setState(() {
        _scanError = _errorMessage(err);
        _submitting = false;
      });
    }
  }

  Future<void> _loadEvents(String assetId) async {
    setState(() {
      _eventsLoading = true;
      _eventsError = false;
    });
    try {
      final data = await api.get<List<dynamic>>('/assets/$assetId/tracking-events');
      setState(() {
        _events = data.map((e) => TrackingEventRead.fromJson(e as Map<String, dynamic>)).toList();
        _eventsLoading = false;
      });
    } catch (_) {
      // GET /assets/{id}/tracking-events needs 'tracking.view', a different
      // permission from 'tracking.scan' on the scan endpoint — the web UI
      // doesn't pre-check this either, it just lets the query fail into an
      // error state.
      setState(() {
        _eventsError = true;
        _eventsLoading = false;
      });
    }
  }

  void _handleManualSubmit() {
    final value = _manualValueController.text.trim();
    if (value.isEmpty) return;
    _stopCamera();
    setState(() => _phase = _Phase.idle);
    _submitScan(_manualType, value);
  }

  void _handleScanAgain() {
    setState(() {
      _result = null;
      _scanError = null;
      _manualValueController.clear();
      _events = null;
      _eventsError = false;
      _phase = _Phase.idle;
    });
  }

  @override
  Widget build(BuildContext context) {
    if (_phase == _Phase.resolved && _result != null) {
      return _ResolvedView(
        result: _result!,
        events: _events,
        eventsLoading: _eventsLoading,
        eventsError: _eventsError,
        onScanAgain: _handleScanAgain,
      );
    }

    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (_scanError != null) ...[
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: Colors.red.shade50,
                border: Border.all(color: Colors.red.shade200),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Text(_scanError!, style: TextStyle(color: Colors.red.shade700)),
            ),
            const SizedBox(height: 12),
          ],
          Container(
            decoration: BoxDecoration(
              border: Border.all(color: Colors.grey.shade300),
              borderRadius: BorderRadius.circular(12),
            ),
            padding: const EdgeInsets.all(12),
            child: Column(
              children: [
                AspectRatio(
                  aspectRatio: 16 / 9,
                  child: ClipRRect(
                    borderRadius: BorderRadius.circular(8),
                    child: Container(
                      color: Colors.black,
                      child: _phase == _Phase.scanning
                          ? MobileScanner(
                              controller: _controller,
                              onDetect: _handleDetect,
                              errorBuilder: (context, error) {
                                WidgetsBinding.instance.addPostFrameCallback((_) {
                                  if (mounted) {
                                    setState(() {
                                      _phase = _Phase.idle;
                                      _cameraError =
                                          "Couldn't access the camera. Check permissions and try again.";
                                    });
                                  }
                                });
                                return const SizedBox.shrink();
                              },
                            )
                          : Center(
                              child: Icon(Icons.videocam_outlined, size: 40, color: Colors.grey.shade600),
                            ),
                    ),
                  ),
                ),
                if (_cameraError != null) ...[
                  const SizedBox(height: 8),
                  Text(_cameraError!, style: TextStyle(color: Colors.red.shade600, fontSize: 13)),
                ],
                const SizedBox(height: 12),
                if (_phase == _Phase.scanning)
                  OutlinedButton(onPressed: _handleStopCamera, child: const Text('Stop camera'))
                else
                  FilledButton.icon(
                    onPressed: _submitting ? null : _startCamera,
                    icon: const Icon(Icons.camera_alt_outlined, size: 18),
                    label: const Text('Start camera'),
                  ),
              ],
            ),
          ),
          const SizedBox(height: 16),
          Container(
            decoration: BoxDecoration(
              border: Border.all(color: Colors.grey.shade300),
              borderRadius: BorderRadius.circular(12),
            ),
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Or enter a code manually', style: Theme.of(context).textTheme.titleSmall),
                const SizedBox(height: 12),
                Row(
                  children: [
                    DropdownButton<String>(
                      value: _manualType,
                      items: const [
                        DropdownMenuItem(value: 'QR', child: Text('QR')),
                        DropdownMenuItem(value: 'BARCODE', child: Text('Barcode')),
                      ],
                      onChanged: (v) => setState(() => _manualType = v ?? 'QR'),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: TextField(
                        controller: _manualValueController,
                        decoration: const InputDecoration(
                          labelText: 'Identifier value',
                          border: OutlineInputBorder(),
                        ),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: _noteController,
                  decoration: const InputDecoration(labelText: 'Note (optional)', border: OutlineInputBorder()),
                ),
                const SizedBox(height: 16),
                FilledButton(
                  onPressed: _submitting ? null : _handleManualSubmit,
                  child: Text(_submitting ? 'Submitting…' : 'Submit code'),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _ResolvedView extends StatelessWidget {
  final ScanResponse result;
  final List<TrackingEventRead>? events;
  final bool eventsLoading;
  final bool eventsError;
  final VoidCallback onScanAgain;

  const _ResolvedView({
    required this.result,
    required this.events,
    required this.eventsLoading,
    required this.eventsError,
    required this.onScanAgain,
  });

  @override
  Widget build(BuildContext context) {
    final asset = result.asset;
    final trackingEvent = result.trackingEvent;
    final dateFormat = DateFormat.yMMMd().add_jm();

    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: Colors.green.shade50,
              border: Border.all(color: Colors.green.shade200),
              borderRadius: BorderRadius.circular(8),
            ),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Icon(Icons.check_circle, color: Colors.green.shade600, size: 20),
                const SizedBox(width: 8),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('Scan recorded', style: TextStyle(fontWeight: FontWeight.w600, color: Colors.green.shade900)),
                      Text(
                        '${asset.name} · recorded ${dateFormat.format(trackingEvent.occurredAt.toLocal())}',
                        style: TextStyle(color: Colors.green.shade700),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
          Container(
            decoration: BoxDecoration(
              border: Border.all(color: Colors.grey.shade300),
              borderRadius: BorderRadius.circular(12),
            ),
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Asset', style: Theme.of(context).textTheme.titleSmall),
                const SizedBox(height: 8),
                _kv('Name', asset.name),
                _kv('Asset ID', asset.id),
                _kv('Location', asset.currentLocationId ?? '—'),
                _kv('Lifecycle state', asset.currentLifecycleStateId ?? '—'),
                _kv('Custodian', asset.currentCustodianId ?? '—'),
              ],
            ),
          ),
          const SizedBox(height: 16),
          Container(
            decoration: BoxDecoration(
              border: Border.all(color: Colors.grey.shade300),
              borderRadius: BorderRadius.circular(12),
            ),
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Recent tracking events', style: Theme.of(context).textTheme.titleSmall),
                const SizedBox(height: 8),
                if (eventsLoading) const LoadingState(label: 'Loading history…'),
                if (eventsError) const ErrorState(message: "Couldn't load tracking history."),
                if (!eventsLoading && !eventsError && (events == null || events!.isEmpty))
                  const EmptyState(message: 'No prior tracking events for this asset.'),
                if (events != null && events!.isNotEmpty)
                  ...events!.map(
                    (event) => Padding(
                      padding: const EdgeInsets.symmetric(vertical: 8),
                      child: Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          Expanded(
                            child: Text.rich(
                              TextSpan(
                                children: [
                                  TextSpan(text: event.eventType),
                                  TextSpan(
                                    text: ' via ${event.providerType}',
                                    style: TextStyle(color: Colors.grey.shade500),
                                  ),
                                ],
                              ),
                            ),
                          ),
                          Text(
                            dateFormat.format(event.occurredAt.toLocal()),
                            style: TextStyle(color: Colors.grey.shade500, fontSize: 12),
                          ),
                        ],
                      ),
                    ),
                  ),
              ],
            ),
          ),
          const SizedBox(height: 16),
          FilledButton(onPressed: onScanAgain, child: const Text('Scan again')),
        ],
      ),
    );
  }

  Widget _kv(String label, String value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(width: 120, child: Text(label, style: TextStyle(color: Colors.grey.shade600))),
          Expanded(child: Text(value)),
        ],
      ),
    );
  }
}
