import 'bridge_runtime.dart';
import 'file_metadata.dart';

class MetadataBridge {
  MetadataBridge({BridgeRuntime? runtime}) : _runtime = runtime ?? BridgeRuntime();

  final BridgeRuntime _runtime;

  Future<FileMetadataSnapshot> inspectFile(String filePath) async {
    final result = await _runtime.runCommand(<String>['metadata', filePath, '--json']);
    if (result.exitCode != 0) {
      throw StateError(result.stderrText.isNotEmpty ? result.stderrText : 'Metadata command failed.');
    }
    return FileMetadataSnapshot.fromJson(result.decodeJsonObject());
  }
}
