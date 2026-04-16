import 'package:firfoto_viewer/src/app.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('FirFoto Viewer shell renders', (tester) async {
    final binding = TestWidgetsFlutterBinding.ensureInitialized();
    await binding.setSurfaceSize(const Size(1440, 900));
    addTearDown(() => binding.setSurfaceSize(null));

    await tester.pumpWidget(const FirFotoViewerApp());

    expect(find.text('Basic'), findsOneWidget);
    expect(find.text('Advanced'), findsOneWidget);
    expect(find.byIcon(Icons.folder_open_rounded), findsOneWidget);
    expect(find.byIcon(Icons.menu_rounded), findsOneWidget);
    expect(find.textContaining('Build 2026-04-15 10:30 TSİ'), findsOneWidget);
  });

  testWidgets('left and right arrow shortcuts stay mapped for photo navigation', (tester) async {
    final binding = TestWidgetsFlutterBinding.ensureInitialized();
    await binding.setSurfaceSize(const Size(1440, 900));
    addTearDown(() => binding.setSurfaceSize(null));

    await tester.pumpWidget(const FirFotoViewerApp());

    final shortcuts = tester.widgetList<Shortcuts>(find.byType(Shortcuts)).toList();
    expect(shortcuts, isNotEmpty);

    final shortcutMap = shortcuts.first.shortcuts;
    expect(
      shortcutMap.containsKey(const SingleActivator(LogicalKeyboardKey.arrowLeft)),
      isTrue,
    );
    expect(
      shortcutMap.containsKey(const SingleActivator(LogicalKeyboardKey.arrowRight)),
      isTrue,
    );
  });
}
