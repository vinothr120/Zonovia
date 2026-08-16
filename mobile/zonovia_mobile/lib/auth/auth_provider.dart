import 'package:flutter/foundation.dart';

import '../core/api_client.dart';
import '../core/models.dart';
import '../core/token_store.dart';

enum AuthStatus { loading, authenticated, anonymous }

class AuthProvider extends ChangeNotifier {
  AuthProvider._();
  static final AuthProvider instance = AuthProvider._();

  Me? me;
  AuthStatus status = AuthStatus.loading;

  Future<void> bootstrap() async {
    await TokenStore.instance.load();
    await loadMe();
  }

  Future<void> loadMe() async {
    if (TokenStore.instance.accessToken == null) {
      me = null;
      status = AuthStatus.anonymous;
      notifyListeners();
      return;
    }
    try {
      me = await api.get<Map<String, dynamic>>('/users/me').then(Me.fromJson);
      status = AuthStatus.authenticated;
    } catch (_) {
      await TokenStore.instance.clear();
      me = null;
      status = AuthStatus.anonymous;
    }
    notifyListeners();
  }

  Future<void> login(String tenantSlug, String email, String password) async {
    final tokens = await api.post<Map<String, dynamic>>(
      '/auth/login',
      {'tenant_slug': tenantSlug, 'email': email, 'password': password},
      true,
    );
    await TokenStore.instance.setTokens(
      tokens['access_token'] as String,
      tokens['refresh_token'] as String,
    );
    await loadMe();
  }

  Future<void> logout() async {
    final refreshToken = TokenStore.instance.refreshToken;
    await TokenStore.instance.clear();
    me = null;
    status = AuthStatus.anonymous;
    notifyListeners();
    if (refreshToken != null) {
      try {
        await api.post('/auth/logout', {'refresh_token': refreshToken}, true);
      } catch (_) {
        // best-effort — the client-side token is already cleared either way
      }
    }
  }
}
