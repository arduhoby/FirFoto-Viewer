import 'package:path/path.dart' as p;

import 'bridge_runtime.dart';

class ViewerFeedback {
  const ViewerFeedback({
    required this.path,
    required this.decisionOverride,
    required this.categoryOverride,
    required this.tags,
  });

  final String path;
  final String? decisionOverride;
  final String? categoryOverride;
  final List<String> tags;

  factory ViewerFeedback.fromJson(Map<String, dynamic> json) {
    return ViewerFeedback(
      path: json['path']?.toString() ?? '',
      decisionOverride: json['decision_override']?.toString(),
      categoryOverride: json['category_override']?.toString(),
      tags: ((json['tags'] as List<dynamic>?) ?? const <dynamic>[])
          .map((item) => item.toString())
          .toList(),
    );
  }
}

class FeedbackBridge {
  FeedbackBridge({BridgeRuntime? runtime}) : _runtime = runtime ?? BridgeRuntime();

  final BridgeRuntime _runtime;

  Future<List<ViewerFeedback>> loadFeedback(String folderPath) async {
    final dbPath = p.join(folderPath, '.firfoto', 'analysis.sqlite3');
    final result = await _runtime.runCommand(<String>[
      'feedback-get',
      folderPath,
      '--db',
      dbPath,
      '--json',
    ]);

    if (result.exitCode != 0) {
      throw StateError(result.stderrText.isNotEmpty ? result.stderrText : 'Feedback load failed.');
    }

    final payload = result.decodeJsonObject();
    final items = (payload['items'] as List<dynamic>?) ?? const <dynamic>[];
    return items
        .whereType<Map<String, dynamic>>()
        .map(ViewerFeedback.fromJson)
        .toList();
  }

  Future<ViewerFeedback> saveFeedback(
    String folderPath, {
    required String path,
    String? decisionOverride,
    String? categoryOverride,
    List<String>? tags,
  }) async {
    final dbPath = p.join(folderPath, '.firfoto', 'analysis.sqlite3');
    final result = await _runtime.runCommand(<String>[
      'feedback-set',
      folderPath,
      path,
      '--db',
      dbPath,
      if (decisionOverride != null) ...<String>['--decision', decisionOverride],
      if (categoryOverride != null) ...<String>['--category', categoryOverride],
      ...<String>[
        for (final String tag in tags ?? const <String>[]) ...<String>['--tag', tag],
      ],
      '--json',
    ]);

    if (result.exitCode != 0) {
      throw StateError(result.stderrText.isNotEmpty ? result.stderrText : 'Feedback save failed.');
    }

    final payload = result.decodeJsonObject();
    final item = payload['item'] as Map<String, dynamic>? ?? const <String, dynamic>{};
    return ViewerFeedback.fromJson(item);
  }

  Future<List<String>> loadTagCatalog(String folderPath) async {
    final dbPath = p.join(folderPath, '.firfoto', 'analysis.sqlite3');
    final result = await _runtime.runCommand(<String>[
      'tags-get',
      folderPath,
      '--db',
      dbPath,
      '--json',
    ]);
    if (result.exitCode != 0) {
      throw StateError(result.stderrText.isNotEmpty ? result.stderrText : 'Tag catalog load failed.');
    }
    final payload = result.decodeJsonObject();
    return ((payload['tags'] as List<dynamic>?) ?? const <dynamic>[]).map((item) => item.toString()).toList();
  }

  Future<List<String>> addTagsToCatalog(String folderPath, List<String> tags) async {
    final dbPath = p.join(folderPath, '.firfoto', 'analysis.sqlite3');
    final result = await _runtime.runCommand(<String>[
      'tags-add',
      folderPath,
      '--db',
      dbPath,
      ...<String>[for (final String tag in tags) ...<String>['--tag', tag]],
      '--json',
    ]);
    if (result.exitCode != 0) {
      throw StateError(result.stderrText.isNotEmpty ? result.stderrText : 'Tag catalog update failed.');
    }
    final payload = result.decodeJsonObject();
    return ((payload['tags'] as List<dynamic>?) ?? const <dynamic>[]).map((item) => item.toString()).toList();
  }

  Future<List<String>> renameTagGlobally(String folderPath, String oldTag, String newTag) async {
    final dbPath = p.join(folderPath, '.firfoto', 'analysis.sqlite3');
    final result = await _runtime.runCommand(<String>[
      'tags-rename',
      folderPath,
      oldTag,
      newTag,
      '--db',
      dbPath,
      '--json',
    ]);
    if (result.exitCode != 0) {
      throw StateError(result.stderrText.isNotEmpty ? result.stderrText : 'Tag rename failed.');
    }
    final payload = result.decodeJsonObject();
    return ((payload['tags'] as List<dynamic>?) ?? const <dynamic>[]).map((item) => item.toString()).toList();
  }

  Future<List<String>> deleteTagGlobally(String folderPath, String tag) async {
    final dbPath = p.join(folderPath, '.firfoto', 'analysis.sqlite3');
    final result = await _runtime.runCommand(<String>[
      'tags-delete',
      folderPath,
      tag,
      '--db',
      dbPath,
      '--json',
    ]);
    if (result.exitCode != 0) {
      throw StateError(result.stderrText.isNotEmpty ? result.stderrText : 'Tag delete failed.');
    }
    final payload = result.decodeJsonObject();
    return ((payload['tags'] as List<dynamic>?) ?? const <dynamic>[]).map((item) => item.toString()).toList();
  }
}
