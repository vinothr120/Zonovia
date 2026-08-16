import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:zonovia_mobile/main.dart';

void main() {
  testWidgets('App boots to the login screen when signed out', (WidgetTester tester) async {
    await tester.pumpWidget(const ZonoviaApp());
    await tester.pump();

    expect(find.text('Zonovia'), findsWidgets);
    expect(find.byType(TextFormField), findsWidgets);
  });
}
