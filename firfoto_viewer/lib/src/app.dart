import 'package:flutter/material.dart';

import 'viewer/viewer_shell.dart';

class FirFotoViewerApp extends StatelessWidget {
  const FirFotoViewerApp({super.key});

  @override
  Widget build(BuildContext context) {
    final scheme = ColorScheme.fromSeed(
      seedColor: const Color(0xFFB84728),
      brightness: Brightness.dark,
    );

    return MaterialApp(
      title: 'FirFoto Viewer',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        useMaterial3: true,
        brightness: Brightness.dark,
        colorScheme: scheme,
        scaffoldBackgroundColor: const Color(0xFF101114),
        fontFamily: 'SF Pro Display',
      ),
      home: const ViewerShell(),
    );
  }
}
