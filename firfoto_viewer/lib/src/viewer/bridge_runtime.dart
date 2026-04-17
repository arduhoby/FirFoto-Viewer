import 'dart:convert';
import 'dart:io';

const String _workspaceProjectRoot = '/Volumes/public/Firfoto';

class BridgeRuntime {
  Future<BridgeProcessResult> runCommand(List<String> arguments) async {
    final projectRoot = await _resolveProjectRoot();
    final pythonExecutable = await _resolvePythonExecutable(projectRoot);
    final env = _buildPythonEnv(projectRoot);
    final result = await Process.run(
      pythonExecutable,
      <String>['-m', 'firfoto.cli', ...arguments],
      workingDirectory: projectRoot,
      environment: env,
    );
    return BridgeProcessResult(
      exitCode: result.exitCode,
      stdoutText: (result.stdout ?? '').toString(),
      stderrText: (result.stderr ?? '').toString(),
      projectRoot: projectRoot,
      pythonExecutable: pythonExecutable,
      environment: env,
    );
  }

  Future<Process> startCommand(List<String> arguments) async {
    final projectRoot = await _resolveProjectRoot();
    final pythonExecutable = await _resolvePythonExecutable(projectRoot);
    final env = _buildPythonEnv(projectRoot);
    return Process.start(
      pythonExecutable,
      <String>['-m', 'firfoto.cli', ...arguments],
      workingDirectory: projectRoot,
      environment: env,
      runInShell: false,
    );
  }

  Future<String> _resolveProjectRoot() async {
    final envRoot = Platform.environment['FIRFOTO_PROJECT_ROOT'];
    if (envRoot != null && envRoot.isNotEmpty) {
      if (await File('$envRoot/src/firfoto/cli.py').exists()) {
        return envRoot;
      }
    }

    if (await File('$_workspaceProjectRoot/src/firfoto/cli.py').exists()) {
      return _workspaceProjectRoot;
    }

    final current = Directory.current;
    if (await File('${current.path}/src/firfoto/cli.py').exists()) {
      return current.path;
    }

    Directory probe = current;
    while (true) {
      final cli = File('${probe.path}/src/firfoto/cli.py');
      if (await cli.exists()) {
        return probe.path;
      }
      if (probe.parent.path == probe.path) {
        throw StateError(
          'Firfoto Python bridge root could not be resolved. '
          'Set FIRFOTO_PROJECT_ROOT if the app is launched outside the repo.',
        );
      }
      probe = probe.parent;
    }
  }

  Future<String> _resolvePythonExecutable(String projectRoot) async {
    final envPython = Platform.environment['FIRFOTO_PYTHON'];
    if (envPython != null && envPython.isNotEmpty) {
      return envPython;
    }

    final candidates = <String>[
      if (Platform.isWindows)
        '$projectRoot\\.venv\\Scripts\\python.exe'
      else
        '$projectRoot/.venv/bin/python',
      if (!Platform.isWindows) 'python3',
      'python',
    ];

    for (final candidate in candidates) {
      if (candidate.contains(Platform.pathSeparator)) {
        if (await File(candidate).exists()) {
          return candidate;
        }
        continue;
      }
      try {
        final result = await Process.run(candidate, const <String>['--version']);
        if (result.exitCode == 0) {
          return candidate;
        }
      } catch (_) {
        continue;
      }
    }
    throw StateError('Python executable for Firfoto bridge not found.');
  }

  Map<String, String> _buildPythonEnv(String projectRoot) {
    final env = Map<String, String>.from(Platform.environment);
    final existing = env['PYTHONPATH'];
    env['PYTHONPATH'] = [
      if (existing != null && existing.isNotEmpty) existing,
      projectRoot,
      '$projectRoot/src',
    ].join(Platform.isWindows ? ';' : ':');
    return env;
  }
}

class BridgeProcessResult {
  BridgeProcessResult({
    required this.exitCode,
    required this.stdoutText,
    required this.stderrText,
    required this.projectRoot,
    required this.pythonExecutable,
    required this.environment,
  });

  final int exitCode;
  final String stdoutText;
  final String stderrText;
  final String projectRoot;
  final String pythonExecutable;
  final Map<String, String> environment;

  Map<String, dynamic> decodeJsonObject() {
    final decoded = jsonDecode(stdoutText);
    if (decoded is! Map<String, dynamic>) {
      throw StateError('Expected JSON object but received: $decoded');
    }
    return decoded;
  }
}
