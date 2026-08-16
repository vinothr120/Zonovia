import 'package:flutter/material.dart';

import '../auth/auth_provider.dart';
import '../auth/login_screen.dart';
import '../tracking/scan_screen.dart';

class RootScreen extends StatefulWidget {
  const RootScreen({super.key});

  @override
  State<RootScreen> createState() => _RootScreenState();
}

class _RootScreenState extends State<RootScreen> {
  @override
  void initState() {
    super.initState();
    AuthProvider.instance.bootstrap();
  }

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: AuthProvider.instance,
      builder: (context, _) {
        switch (AuthProvider.instance.status) {
          case AuthStatus.loading:
            return const Scaffold(body: Center(child: CircularProgressIndicator()));
          case AuthStatus.anonymous:
            return const LoginScreen();
          case AuthStatus.authenticated:
            return const ScanScreen();
        }
      },
    );
  }
}
