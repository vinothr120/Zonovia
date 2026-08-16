import 'package:flutter/material.dart';

import 'auth/auth_provider.dart';
import 'shared/root_screen.dart';

/// Matches web/src/index.css's --accent (#4f46e5) so the two clients read as
/// the same product. No role-based theming at this stage (Zonovia has no
/// role-routed home screen yet, unlike the SchoolAssist sibling this was
/// ported from) — a single fixed seed color.
const Color _seedColor = Color(0xFF4F46E5);

void main() {
  runApp(const ZonoviaApp());
}

class ZonoviaApp extends StatelessWidget {
  const ZonoviaApp({super.key});

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: AuthProvider.instance,
      builder: (context, _) {
        return MaterialApp(
          title: 'Zonovia',
          theme: ThemeData(colorScheme: ColorScheme.fromSeed(seedColor: _seedColor), useMaterial3: true),
          home: const RootScreen(),
        );
      },
    );
  }
}
