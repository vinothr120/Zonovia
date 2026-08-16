# Zonovia Mobile (`mobile/`)

Native Flutter app, at `mobile/zonovia_mobile/`. This is **Phase 5 Stage 1**: the app shell, auth,
and **online-only** QR/barcode scanning — parity with what's already working on `web/`.

## What this stage is not

No offline storage, no local database (`drift`/SQLite), no operation-log sync engine, no conflict
resolution. The architecture blueprint (§15, ADR-005) already commits to that design; it is a
deliberate, separate follow-up stage, not built here. Every scan in this build requires a live
connection to the backend — there is no offline queue.

## How this project came to exist

No Flutter/Dart SDK was available in the environment that built this stage. Rather than generate a
project blind, the native scaffolding (`android/`, `ios/`, `.metadata`, `analysis_options.yaml`,
`pubspec.yaml`, `.gitignore`, `test/widget_test.dart`) was copied from the already-working,
previously-shipped `SchoolAssist` Flutter app and renamed (package/bundle identifiers, app name,
launcher label). The `lib/` Dart source is new, hand-written against the same conventions that
scaffolding's sibling apps use: a hand-written `http`-package API client with manual 401-refresh,
`flutter_secure_storage` for tokens, no state-management package (plain `ChangeNotifier` +
`ListenableBuilder`/`setState`), manual-`fromJson` models with no codegen.

**This code has never been compiled.** It was statically reviewed line-by-line — braces balanced,
imports resolved, every renamed identifier checked, every model field cross-checked against the
backend's Pydantic schemas — but nobody has run `flutter pub get`, `flutter analyze`, `flutter run`,
or a Gradle/Xcode build against it yet. Treat the first real toolchain pass as a normal, expected
step of picking this up, not a sign something is wrong.

## Why no state-management package

The sibling apps this was ported from use plain `ChangeNotifier` + `ListenableBuilder`/`setState` —
no `provider`, `riverpod`, `bloc`, or similar. The app is small enough (one auth provider, one
screen) that a state-management package would be pure overhead. Don't add one preemptively; if a
real need shows up as the app grows, that's the point to reconsider, not before.

## Prerequisites

- Flutter SDK, stable channel, matching the version pinned in `zonovia_mobile/.metadata`
- Android SDK (for Android builds/emulator)
- Xcode (for iOS builds/simulator, macOS only)

## Running it

```bash
cd zonovia_mobile
flutter pub get
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000/api/v1
```

`10.0.2.2` is the Android emulator's alias for the host machine's `localhost` — that's the default
baked into `lib/core/api_client.dart` if you don't pass `--dart-define`. iOS simulators can reach
the host directly via `localhost`. To run against a real device on the same network, use the host
machine's LAN IP instead, e.g. `--dart-define=API_BASE_URL=http://192.168.1.x:8000/api/v1`.

## Demo login

Tenant `acme-demo`, matching `backend/app/seed.py` and the web app's default. Use any seeded user's
email/password from that tenant.

## Cannot be verified without a real Flutter toolchain run

Stated plainly, not glossed over: whether the Dart actually compiles (null-safety correctness);
whether `flutter pub get` resolves the dependency graph without conflicts (in particular whether
`mobile_scanner`'s minimum Android `minSdk` requirement is compatible with whatever
`flutter.minSdkVersion` resolves to — if not, Gradle will fail loudly and clearly at first build);
whether the Gradle/iOS builds actually succeed; and actual runtime behavior (camera permission
dialog, decode-to-backend round-trip, token-refresh-on-401 against a live server).
