import 'package:path/path.dart' as p;

import 'analysis_summary.dart';
import 'bridge_runtime.dart';

class ResultsBridge {
  ResultsBridge({BridgeRuntime? runtime}) : _runtime = runtime ?? BridgeRuntime();

  final BridgeRuntime _runtime;

  Future<List<AnalysisSummary>> loadResults(String folderPath) async {
    final dbPath = p.join(folderPath, '.firfoto', 'analysis.sqlite3');
    final result = await _runtime.runCommand(<String>[
      'results',
      folderPath,
      '--db',
      dbPath,
      '--json',
    ]);

    if (result.exitCode != 0) {
      throw StateError(result.stderrText.isNotEmpty ? result.stderrText : 'Results load failed.');
    }

    final payload = result.decodeJsonObject();
    final items = (payload['results'] as List<dynamic>?) ?? const <dynamic>[];
    return items
        .whereType<Map<String, dynamic>>()
        .map(AnalysisSummary.fromJson)
        .toList();
  }
}
