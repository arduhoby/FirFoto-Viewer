import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:path/path.dart' as p;

import 'bridge_runtime.dart';

sealed class AnalyzeEvent {
  const AnalyzeEvent();
}

class AnalyzeStarted extends AnalyzeEvent {
  const AnalyzeStarted({required this.folderPath, required this.dbPath});

  final String folderPath;
  final String dbPath;
}

class AnalyzeProgress extends AnalyzeEvent {
  const AnalyzeProgress({
    required this.index,
    required this.total,
    required this.path,
  });

  final int index;
  final int total;
  final String path;
}

class AnalyzeCompleted extends AnalyzeEvent {
  const AnalyzeCompleted({
    required this.analyzedCount,
    required this.dbPath,
    required this.canceled,
  });

  final int analyzedCount;
  final String dbPath;
  final bool canceled;
}

class AnalyzeFailed extends AnalyzeEvent {
  const AnalyzeFailed(this.message);

  final String message;
}

class AnalyzeSession {
  AnalyzeSession(this._process, this.events);

  final Process _process;
  final Stream<AnalyzeEvent> events;

  Future<void> cancel() async {
    _process.kill(ProcessSignal.sigterm);
  }
}

class AnalyzeBridge {
  AnalyzeBridge({BridgeRuntime? runtime}) : _runtime = runtime ?? BridgeRuntime();

  final BridgeRuntime _runtime;

  Future<AnalyzeSession> startAnalysis(String folderPath, {required bool recursive}) async {
    final dbPath = p.join(folderPath, '.firfoto', 'analysis.sqlite3');
    final process = await _runtime.startCommand(<String>[
      'analyze-stream',
      folderPath,
      '--db',
      dbPath,
      if (recursive) '--recursive',
    ]);

    final controller = StreamController<AnalyzeEvent>();
    final stdoutLines = process.stdout.transform(utf8.decoder).transform(const LineSplitter());
    final stderrLines = process.stderr.transform(utf8.decoder).transform(const LineSplitter());

    stdoutLines.listen(
      (line) {
        if (line.trim().isEmpty) {
          return;
        }
        try {
          final payload = jsonDecode(line) as Map<String, dynamic>;
          final eventName = payload['event']?.toString();
          switch (eventName) {
            case 'started':
              controller.add(
                AnalyzeStarted(
                  folderPath: payload['folder']?.toString() ?? folderPath,
                  dbPath: payload['db_path']?.toString() ?? dbPath,
                ),
              );
              break;
            case 'progress':
              controller.add(
                AnalyzeProgress(
                  index: (payload['index'] as num?)?.toInt() ?? 0,
                  total: (payload['total'] as num?)?.toInt() ?? 0,
                  path: payload['path']?.toString() ?? '',
                ),
              );
              break;
            case 'completed':
              controller.add(
                AnalyzeCompleted(
                  analyzedCount: (payload['analyzed_count'] as num?)?.toInt() ?? 0,
                  dbPath: payload['db_path']?.toString() ?? dbPath,
                  canceled: payload['canceled'] == true,
                ),
              );
              break;
            case 'cancelled':
              controller.add(const AnalyzeFailed('Analiz durduruldu.'));
              break;
            case 'error':
              controller.add(AnalyzeFailed(payload['message']?.toString() ?? 'Analiz hatasi.'));
              break;
            default:
              break;
          }
        } catch (error) {
          controller.add(AnalyzeFailed('Analiz cikisi okunamadi: $error'));
        }
      },
      onError: (Object error, StackTrace stackTrace) {
        controller.add(AnalyzeFailed('Analiz akisi bozuldu: $error'));
      },
    );

    stderrLines.listen((line) {
      if (line.trim().isNotEmpty) {
        controller.add(AnalyzeFailed(line.trim()));
      }
    });

    process.exitCode.then((code) async {
      if (code != 0 && code != 130) {
        controller.add(AnalyzeFailed('Analiz $code kodu ile sonlandi.'));
      }
      await controller.close();
    });

    return AnalyzeSession(process, controller.stream);
  }
}
