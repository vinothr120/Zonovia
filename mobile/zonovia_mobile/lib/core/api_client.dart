import 'dart:convert';

import 'package:http/http.dart' as http;

import 'token_store.dart';

/// 10.0.2.2 is the Android emulator's alias for the host machine's localhost.
/// Point this at a LAN IP (e.g. http://192.168.1.x:8000/api/v1) to run against
/// a real device, or override at build time with --dart-define=API_BASE_URL=...
const String _defaultBaseUrl = 'http://10.0.2.2:8000/api/v1';
const String apiBaseUrl = String.fromEnvironment(
  'API_BASE_URL',
  defaultValue: _defaultBaseUrl,
);

class ApiErrorBody {
  final String code;
  final String message;
  final Map<String, dynamic>? fieldErrors;

  ApiErrorBody({required this.code, required this.message, this.fieldErrors});

  factory ApiErrorBody.fromJson(Map<String, dynamic> json) => ApiErrorBody(
        code: json['code'] as String? ?? 'UNKNOWN',
        message: json['message'] as String? ?? 'Something went wrong.',
        fieldErrors: json['field_errors'] as Map<String, dynamic>?,
      );

  factory ApiErrorBody.unknown([String message = 'Something went wrong.']) =>
      ApiErrorBody(code: 'UNKNOWN', message: message);
}

class ApiException implements Exception {
  final int status;
  final ApiErrorBody body;

  ApiException(this.status, this.body);

  String get message => body.message;

  @override
  String toString() => 'ApiException($status, ${body.code}: ${body.message})';
}

class ApiClient {
  ApiClient._();
  static final ApiClient instance = ApiClient._();

  final http.Client _http = http.Client();
  Future<String?>? _refreshInFlight;

  Uri _buildUri(String path, Map<String, dynamic>? params) {
    final uri = Uri.parse('$apiBaseUrl$path');
    if (params == null || params.isEmpty) return uri;
    final query = <String, String>{};
    params.forEach((key, value) {
      if (value != null) query[key] = value.toString();
    });
    return uri.replace(queryParameters: {...uri.queryParameters, ...query});
  }

  Future<http.Response> _rawRequest(
    String method,
    String path, {
    Map<String, dynamic>? params,
    Object? body,
    bool skipAuth = false,
    String? accessToken,
  }) {
    final uri = _buildUri(path, params);
    final headers = <String, String>{'Content-Type': 'application/json'};
    if (accessToken != null && !skipAuth) {
      headers['Authorization'] = 'Bearer $accessToken';
    }
    final encodedBody = body != null ? jsonEncode(body) : null;

    switch (method) {
      case 'GET':
        return _http.get(uri, headers: headers);
      case 'POST':
        return _http.post(uri, headers: headers, body: encodedBody);
      case 'PATCH':
        return _http.patch(uri, headers: headers, body: encodedBody);
      case 'PUT':
        return _http.put(uri, headers: headers, body: encodedBody);
      case 'DELETE':
        return _http.delete(uri, headers: headers, body: encodedBody);
      default:
        throw ArgumentError('Unsupported method: $method');
    }
  }

  Future<String?> _refreshAccessToken() {
    final refreshToken = TokenStore.instance.refreshToken;
    if (refreshToken == null) return Future.value(null);

    return _refreshInFlight ??= () async {
      try {
        final res = await _http.post(
          Uri.parse('$apiBaseUrl/auth/refresh'),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode({'refresh_token': refreshToken}),
        );
        if (res.statusCode != 200) return null;
        final envelope = jsonDecode(res.body) as Map<String, dynamic>;
        final data = envelope['data'] as Map<String, dynamic>?;
        if (data == null) return null;
        final accessToken = data['access_token'] as String;
        final newRefreshToken = data['refresh_token'] as String;
        await TokenStore.instance.setTokens(accessToken, newRefreshToken);
        return accessToken;
      } catch (_) {
        return null;
      } finally {
        _refreshInFlight = null;
      }
    }();
  }

  /// Performs a request and returns the decoded `data` payload, retrying once
  /// with a refreshed access token on a 401.
  Future<T> request<T>(
    String method,
    String path, {
    Map<String, dynamic>? params,
    Object? body,
    bool skipAuth = false,
  }) async {
    var accessToken = TokenStore.instance.accessToken;
    var res = await _rawRequest(method, path,
        params: params, body: body, skipAuth: skipAuth, accessToken: accessToken);

    if (res.statusCode == 401 && !skipAuth && TokenStore.instance.refreshToken != null) {
      accessToken = await _refreshAccessToken();
      if (accessToken != null) {
        res = await _rawRequest(method, path,
            params: params, body: body, skipAuth: skipAuth, accessToken: accessToken);
      }
    }

    if (res.statusCode == 204 || res.body.isEmpty) {
      return null as T;
    }

    final envelope = jsonDecode(res.body) as Map<String, dynamic>;
    final error = envelope['error'] as Map<String, dynamic>?;
    if (res.statusCode < 200 || res.statusCode >= 300 || error != null) {
      if (res.statusCode == 401) await TokenStore.instance.clear();
      throw ApiException(
        res.statusCode,
        error != null ? ApiErrorBody.fromJson(error) : ApiErrorBody.unknown(),
      );
    }
    return envelope['data'] as T;
  }

  Future<T> get<T>(String path, [Map<String, dynamic>? params]) =>
      request<T>('GET', path, params: params);

  Future<T> post<T>(String path, [Object? body, bool skipAuth = false]) =>
      request<T>('POST', path, body: body, skipAuth: skipAuth);

  Future<T> patch<T>(String path, [Object? body]) =>
      request<T>('PATCH', path, body: body);

  Future<T> put<T>(String path, [Object? body]) =>
      request<T>('PUT', path, body: body);

  Future<T> delete<T>(String path, [Object? body]) =>
      request<T>('DELETE', path, body: body);
}

final api = ApiClient.instance;
