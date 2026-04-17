import 'dart:io';

import 'package:path/path.dart' as p;

import 'bridge_runtime.dart';
import 'preview_snapshot.dart';

class PreviewBridge {
  PreviewBridge({BridgeRuntime? runtime}) : _runtime = runtime ?? BridgeRuntime();

  final BridgeRuntime _runtime;

  Future<PreviewSnapshot> renderPreview(
    String filePath, {
    String? metadataSourcePath,
    int maxWidth = 1800,
    int maxHeight = 1400,
    String variant = 'preview',
  }) async {
    final cacheDir = await _ensureCacheDir(variant);
    final safeName = '${filePath.hashCode.abs()}_${maxWidth}x$maxHeight.png';
    final outputPath = p.join(cacheDir.path, safeName);

    final result = await _runtime.runCommand(<String>[
      'render-preview',
      filePath,
      '--output',
      outputPath,
      if (metadataSourcePath != null) ...<String>['--metadata-source', metadataSourcePath],
      '--max-width',
      '$maxWidth',
      '--max-height',
      '$maxHeight',
      '--json',
    ]);

    if (result.exitCode != 0) {
      throw StateError(result.stderrText.isNotEmpty ? result.stderrText : 'Preview render failed.');
    }

    final payload = result.decodeJsonObject();
    if ((payload['output_path']?.toString() ?? '').isEmpty) {
      payload['output_path'] = outputPath;
    }
    return PreviewSnapshot.fromJson(payload);
  }

  Future<Directory> _ensureCacheDir(String variant) async {
    final dir = Directory(p.join(Directory.systemTemp.path, 'firfoto_viewer_$variant'));
    if (!await dir.exists()) {
      await dir.create(recursive: true);
    }
    return dir;
  }
}
