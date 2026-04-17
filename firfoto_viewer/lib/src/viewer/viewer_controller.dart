import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:path/path.dart' as p;

import 'analysis_summary.dart';
import 'analyze_bridge.dart';
import 'feedback_bridge.dart';
import 'file_metadata.dart';
import 'metadata_bridge.dart';
import 'photo_entry.dart';
import 'preview_bridge.dart';
import 'preview_snapshot.dart';
import 'results_bridge.dart';

class ViewerController extends ChangeNotifier {
  ViewerController({
    MetadataBridge? metadataBridge,
    PreviewBridge? previewBridge,
    ResultsBridge? resultsBridge,
    AnalyzeBridge? analyzeBridge,
    FeedbackBridge? feedbackBridge,
  }) : _metadataBridge = metadataBridge ?? MetadataBridge(),
       _previewBridge = previewBridge ?? PreviewBridge(),
       _resultsBridge = resultsBridge ?? ResultsBridge(),
       _analyzeBridge = analyzeBridge ?? AnalyzeBridge(),
       _feedbackBridge = feedbackBridge ?? FeedbackBridge();

  final MetadataBridge _metadataBridge;
  final PreviewBridge _previewBridge;
  final ResultsBridge _resultsBridge;
  final AnalyzeBridge _analyzeBridge;
  final FeedbackBridge _feedbackBridge;

  String? _selectedFolder;
  bool _recursive = false;
  bool _isLoading = false;
  bool _isLoadingMetadata = false;
  bool _isLoadingPreview = false;
  bool _isAnalyzing = false;
  int _analysisProgress = 0;
  int _analysisTotal = 0;
  double _exposureEv = 0;
  String _statusText = 'Bir klasor sec, sonra Load ile goruntule.';
  List<PhotoEntry> _entries = const [];
  int _selectedIndex = -1;
  double _zoom = 1;
  final Map<String, FileMetadataSnapshot> _metadataCache = <String, FileMetadataSnapshot>{};
  final Map<String, String> _previewCache = <String, String>{};
  final Map<String, PreviewSnapshot> _previewSnapshotCache = <String, PreviewSnapshot>{};
  final Set<String> _thumbnailRequests = <String>{};
  final Map<String, AnalysisSummary> _analysisByPath = <String, AnalysisSummary>{};
  final Map<String, ViewerFeedback> _feedbackByPath = <String, ViewerFeedback>{};
  List<String> _availableTags = const <String>[];
  FileMetadataSnapshot? _selectedMetadata;
  String? _metadataError;
  String? _selectedPreviewPath;
  String? _previewError;
  PreviewSnapshot? _selectedPreviewSnapshot;
  AnalyzeSession? _activeAnalyzeSession;
  StreamSubscription<AnalyzeEvent>? _analysisSubscription;
  int _metadataRequestId = 0;
  int _previewRequestId = 0;

  String? get selectedFolder => _selectedFolder;
  bool get recursive => _recursive;
  bool get isLoading => _isLoading;
  bool get isLoadingMetadata => _isLoadingMetadata;
  bool get isLoadingPreview => _isLoadingPreview;
  bool get isAnalyzing => _isAnalyzing;
  int get analysisProgress => _analysisProgress;
  int get analysisTotal => _analysisTotal;
  double get exposureEv => _exposureEv;
  String get statusText => _statusText;
  List<PhotoEntry> get entries => _entries;
  int get selectedIndex => _selectedIndex;
  double get zoom => _zoom;
  FileMetadataSnapshot? get selectedMetadata => _selectedMetadata;
  String? get metadataError => _metadataError;
  String? get selectedPreviewPath => _selectedPreviewPath;
  String? get previewError => _previewError;
  PreviewSnapshot? get selectedPreviewSnapshot => _selectedPreviewSnapshot;
  List<String> get availableTags => _availableTags;
  AnalysisSummary? get selectedAnalysis {
    final entry = selectedEntry;
    if (entry == null) {
      return null;
    }
    return analysisFor(entry);
  }

  PhotoEntry? get selectedEntry {
    if (_selectedIndex < 0 || _selectedIndex >= _entries.length) {
      return null;
    }
    return _entries[_selectedIndex];
  }

  @override
  void dispose() {
    unawaited(_analysisSubscription?.cancel());
    super.dispose();
  }

  void setFolder(String? folder) {
    _selectedFolder = folder;
    _statusText = folder == null || folder.isEmpty
        ? 'Bir klasor sec, sonra Load ile goruntule.'
        : 'Klasor secildi. Load ile listeyi hazirla, Analyze ile kalici sonucu al.';
    notifyListeners();
  }

  void setRecursive(bool value) {
    _recursive = value;
    notifyListeners();
  }

  Future<void> openPhotoFile(String filePath) async {
    final normalizedPath = _normalizePath(filePath);
    final file = File(normalizedPath);
    if (!await file.exists()) {
      _statusText = 'Dosya bulunamadi.';
      notifyListeners();
      return;
    }

    final extension = p.extension(file.path).toLowerCase();
    if (!supportedPhotoExtensions.contains(extension)) {
      _statusText = 'Desteklenmeyen dosya turu: ${p.basename(file.path)}';
      notifyListeners();
      return;
    }

    _selectedFolder = file.parent.path;
    _recursive = false;
    _statusText = 'Fotograf aciliyor: ${p.basename(file.path)}';
    notifyListeners();

    await loadFolder();
    if (_entries.isEmpty) {
      return;
    }

    final selectedPath = _normalizePath(file.path);
    var matchIndex = _entries.indexWhere((entry) => _normalizePath(entry.file.path) == selectedPath);
    if (matchIndex == -1) {
      final selectedDirectory = _normalizePath(file.parent.path);
      final selectedName = p.basename(selectedPath).toLowerCase();
      matchIndex = _entries.indexWhere(
        (entry) =>
            p.basename(entry.file.path).toLowerCase() == selectedName &&
            _normalizePath(entry.file.parent.path) == selectedDirectory,
      );
    }
    if (matchIndex == -1) {
      _statusText = 'Fotograf listede bulunamadi: ${p.basename(file.path)}';
      notifyListeners();
      return;
    }

    if (_selectedIndex != matchIndex) {
      selectByIndex(matchIndex);
    } else {
      _statusText = '${matchIndex + 1}/${_entries.length}  ${_entries[matchIndex].name}';
      notifyListeners();
    }
  }

  Future<void> loadFolder() async {
    final folder = _selectedFolder;
    if (folder == null || folder.isEmpty) {
      _statusText = 'Once bir klasor sec.';
      notifyListeners();
      return;
    }

    final directory = Directory(folder);
    if (!await directory.exists()) {
      _statusText = 'Klasor bulunamadi.';
      notifyListeners();
      return;
    }

    _isLoading = true;
    _statusText = 'Dosyalar yukleniyor...';
    notifyListeners();
    await Future<void>.delayed(Duration.zero);

    try {
      var scanResult = await _scanDirectory(directory, recursive: _recursive);
      if (!_recursive && scanResult.files.isEmpty && scanResult.subdirectoryCount > 0) {
        _statusText = 'Kok klasorde fotograf yok, alt klasorler taraniyor...';
        notifyListeners();
        await Future<void>.delayed(Duration.zero);
        scanResult = await _scanDirectory(directory, recursive: true);
      }

      scanResult.files.sort((a, b) => a.path.toLowerCase().compareTo(b.path.toLowerCase()));

      _entries = <PhotoEntry>[
        for (var index = 0; index < scanResult.files.length; index += 1)
          PhotoEntry(file: scanResult.files[index], index: index),
      ];
    } on FileSystemException catch (error) {
      _isLoading = false;
      _statusText = 'Klasor okunamadi: ${error.message}';
      notifyListeners();
      return;
    }
    _selectedIndex = _entries.isEmpty ? -1 : 0;
    _zoom = 1;
    _metadataCache.clear();
    _previewCache.clear();
    _previewSnapshotCache.clear();
    _thumbnailRequests.clear();
    _analysisByPath.clear();
    _feedbackByPath.clear();
    _selectedMetadata = null;
    _metadataError = null;
    _selectedPreviewPath = null;
    _previewError = null;
    _isLoading = false;
    _statusText = _entries.isEmpty
        ? 'Desteklenen fotograf bulunamadi.'
        : '${_entries.length} dosya yuklendi. Kayitli analizler kontrol ediliyor...';
    notifyListeners();

    if (_selectedIndex >= 0) {
      _statusText = '${_entries.length} dosya yuklendi. Ilk fotograf hazirlaniyor...';
      notifyListeners();
    }

    await _loadSavedResults();
    await _loadSavedFeedback();
    await _loadTagCatalog();
    await _loadSelectedMetadata();
    await _loadSelectedPreview();
    _primeThumbnailWindow();
  }

  void selectByIndex(int index) {
    if (index < 0 || index >= _entries.length || index == _selectedIndex) {
      return;
    }
    _selectedIndex = index;
    _statusText = '${index + 1}/${_entries.length}  ${_entries[index].name}';
    notifyListeners();
    unawaited(_loadSelectedMetadata());
    unawaited(_loadSelectedPreview());
    _primeThumbnailWindow();
  }

  void selectNext() => selectByIndex(_selectedIndex + 1);

  void selectPrevious() => selectByIndex(_selectedIndex - 1);

  void zoomIn() => setZoom(_zoom * 1.15);

  void zoomOut() => setZoom(_zoom / 1.15);

  void setZoom(double value) {
    final clamped = value.clamp(0.4, 6.0);
    if ((clamped - _zoom).abs() < 0.001) {
      return;
    }
    _zoom = clamped;
    notifyListeners();
  }

  void resetZoom() {
    _zoom = 1;
    notifyListeners();
  }

  void setExposureEv(double value) {
    final clamped = value.clamp(-2.0, 2.0);
    if ((clamped - _exposureEv).abs() < 0.001) {
      return;
    }
    _exposureEv = clamped;
    notifyListeners();
  }

  void resetExposureEv() {
    if (_exposureEv == 0) {
      return;
    }
    _exposureEv = 0;
    notifyListeners();
  }

  Future<double?> applyAutoExposureForSelected() async {
    final snapshot = await _ensureSelectedPreviewSnapshotForExposure();
    final suggested = snapshot?.suggestedExposureEv;
    if (suggested == null) {
      return null;
    }
    setExposureEv(suggested);
    return _exposureEv;
  }

  String? thumbnailPathFor(PhotoEntry entry) {
    if (entry.isPreviewable) {
      return entry.file.path;
    }
    return _previewCache[_thumbnailCacheKey(entry.file.path)];
  }

  AnalysisSummary? analysisFor(PhotoEntry entry) {
    final base = _analysisByPath[entry.file.path];
    final feedback = _feedbackByPath[entry.file.path];
    if (base == null && feedback == null) {
      return null;
    }

    final seeded = base ??
        AnalysisSummary.placeholder(
          path: entry.file.path,
          category: _metadataCache[entry.file.path]?.categoryHint ?? 'general',
        );

    if (feedback == null) {
      return seeded;
    }

    return seeded.copyWith(
      decision: feedback.decisionOverride ?? seeded.decision,
      category: feedback.categoryOverride ?? seeded.category,
      tags: feedback.tags,
      isDecisionOverridden: feedback.decisionOverride != null,
      isCategoryOverridden: feedback.categoryOverride != null,
    );
  }

  Future<void> updateSelectedDecision(String decision) async {
    final folder = _selectedFolder;
    final entry = selectedEntry;
    if (folder == null || folder.isEmpty || entry == null) {
      return;
    }

    final existing = _feedbackByPath[entry.file.path];
    final saved = await _feedbackBridge.saveFeedback(
      folder,
      path: entry.file.path,
      decisionOverride: decision,
      categoryOverride: existing?.categoryOverride,
      tags: existing?.tags,
    );
    _feedbackByPath[entry.file.path] = saved;
    _statusText = 'Karar guncellendi: ${entry.name} -> $decision';
    notifyListeners();
  }

  Future<void> updateSelectedCategory(String category) async {
    final folder = _selectedFolder;
    final entry = selectedEntry;
    if (folder == null || folder.isEmpty || entry == null) {
      return;
    }

    final existing = _feedbackByPath[entry.file.path];
    final saved = await _feedbackBridge.saveFeedback(
      folder,
      path: entry.file.path,
      decisionOverride: existing?.decisionOverride,
      categoryOverride: category,
      tags: existing?.tags,
    );
    _feedbackByPath[entry.file.path] = saved;
    _statusText = 'Kategori guncellendi: ${entry.name} -> $category';
    notifyListeners();
  }

  Future<void> toggleSelectedTag(String tag) async {
    final folder = _selectedFolder;
    final entry = selectedEntry;
    if (folder == null || folder.isEmpty || entry == null) {
      return;
    }

    final existing = _feedbackByPath[entry.file.path];
    final tags = <String>{...(existing?.tags ?? const <String>[])};
    if (tags.contains(tag)) {
      tags.remove(tag);
    } else {
      tags.add(tag);
    }

    final saved = await _feedbackBridge.saveFeedback(
      folder,
      path: entry.file.path,
      decisionOverride: existing?.decisionOverride,
      categoryOverride: existing?.categoryOverride,
      tags: tags.toList()..sort(),
    );
    _feedbackByPath[entry.file.path] = saved;
    _statusText = 'Etiketler guncellendi: ${entry.name}';
    notifyListeners();
  }

  Future<void> setSelectedTags(List<String> tags) async {
    final folder = _selectedFolder;
    final entry = selectedEntry;
    if (folder == null || folder.isEmpty || entry == null) {
      return;
    }

    final existing = _feedbackByPath[entry.file.path];
    final normalized = tags
        .map((value) => value.trim())
        .where((value) => value.isNotEmpty)
        .toSet()
        .toList()
      ..sort();

    final saved = await _feedbackBridge.saveFeedback(
      folder,
      path: entry.file.path,
      decisionOverride: existing?.decisionOverride,
      categoryOverride: existing?.categoryOverride,
      tags: normalized,
    );
    _feedbackByPath[entry.file.path] = saved;
    _availableTags = await _feedbackBridge.addTagsToCatalog(folder, normalized);
    _statusText = 'Etiketler guncellendi: ${entry.name}';
    notifyListeners();
  }

  Future<void> renameTagGlobally(String oldTag, String newTag) async {
    final folder = _selectedFolder;
    if (folder == null || folder.isEmpty) {
      return;
    }
    final updatedCatalog = await _feedbackBridge.renameTagGlobally(folder, oldTag, newTag);
    _availableTags = updatedCatalog;
    for (final entry in _feedbackByPath.entries.toList()) {
      final updatedTags = entry.value.tags
          .map((value) => value == oldTag ? newTag : value)
          .toSet()
          .toList()
        ..sort();
      _feedbackByPath[entry.key] = ViewerFeedback(
        path: entry.value.path,
        decisionOverride: entry.value.decisionOverride,
        categoryOverride: entry.value.categoryOverride,
        tags: updatedTags,
      );
    }
    _statusText = 'Etiket yeniden adlandirildi: $oldTag -> $newTag';
    notifyListeners();
  }

  Future<void> deleteTagGlobally(String tag) async {
    final folder = _selectedFolder;
    if (folder == null || folder.isEmpty) {
      return;
    }
    final updatedCatalog = await _feedbackBridge.deleteTagGlobally(folder, tag);
    _availableTags = updatedCatalog;
    for (final entry in _feedbackByPath.entries.toList()) {
      final updatedTags = entry.value.tags.where((value) => value != tag).toList()..sort();
      _feedbackByPath[entry.key] = ViewerFeedback(
        path: entry.value.path,
        decisionOverride: entry.value.decisionOverride,
        categoryOverride: entry.value.categoryOverride,
        tags: updatedTags,
      );
    }
    _statusText = 'Etiket tum fotograflardan silindi: $tag';
    notifyListeners();
  }

  void requestThumbnail(PhotoEntry entry) {
    if (entry.isPreviewable) {
      return;
    }
    final cacheKey = _thumbnailCacheKey(entry.file.path);
    if (_previewCache.containsKey(cacheKey) || _thumbnailRequests.contains(cacheKey)) {
      return;
    }
    _thumbnailRequests.add(cacheKey);
    unawaited(_loadRawThumbnail(entry));
  }

  Future<void> startAnalysis() async {
    if (_isAnalyzing) {
      return;
    }
    final folder = _selectedFolder;
    if (folder == null || folder.isEmpty) {
      _statusText = 'Once bir klasor sec.';
      notifyListeners();
      return;
    }

    _isAnalyzing = true;
    _analysisProgress = 0;
    _analysisTotal = 0;
    _statusText = 'Analiz baslatiliyor...';
    notifyListeners();
    try {
      final session = await _analyzeBridge.startAnalysis(folder, recursive: _recursive);
      _activeAnalyzeSession = session;
      await _analysisSubscription?.cancel();
      _analysisSubscription = session.events.listen(_handleAnalyzeEvent);
    } catch (error) {
      _isAnalyzing = false;
      _statusText = 'Analiz baslatilamadi: $error';
      notifyListeners();
    }
  }

  Future<void> cancelAnalysis() async {
    await _activeAnalyzeSession?.cancel();
    _isAnalyzing = false;
    _statusText = 'Analiz iptal istendi.';
    notifyListeners();
  }

  void _handleAnalyzeEvent(AnalyzeEvent event) {
    switch (event) {
      case AnalyzeStarted():
        _statusText = 'Analiz basladi.';
      case AnalyzeProgress():
        _analysisProgress = event.index;
        _analysisTotal = event.total;
        final fileName = event.path.isEmpty ? '' : p.basename(event.path);
        _statusText = '${event.index}/${event.total} analiz ediliyor: $fileName';
      case AnalyzeCompleted():
        _isAnalyzing = false;
        _analysisProgress = event.analyzedCount;
        _analysisTotal = event.analyzedCount;
        _statusText = '${event.analyzedCount} dosya analiz edildi.';
        unawaited(_loadSavedResults());
      case AnalyzeFailed():
        _isAnalyzing = false;
        _statusText = event.message;
    }
    notifyListeners();
  }

  Future<void> _loadSavedResults() async {
    final folder = _selectedFolder;
    if (folder == null || folder.isEmpty) {
      return;
    }
    try {
      final results = await _resultsBridge.loadResults(folder);
      _analysisByPath
        ..clear()
        ..addEntries(results.map((item) => MapEntry(item.path, item)));
      if (results.isNotEmpty) {
        _statusText = '${_entries.length} dosya yuklendi, ${results.length} kayitli analiz bulundu.';
      } else if (_entries.isNotEmpty) {
        _statusText = '${_entries.length} dosya yuklendi. Henuz kayitli analiz yok.';
      }
      notifyListeners();
    } catch (_) {
      // No saved results is fine for a first load.
    }
  }

  Future<void> _loadSavedFeedback() async {
    final folder = _selectedFolder;
    if (folder == null || folder.isEmpty) {
      return;
    }
    try {
      final items = await _feedbackBridge.loadFeedback(folder);
      _feedbackByPath
        ..clear()
        ..addEntries(items.map((item) => MapEntry(item.path, item)));
      notifyListeners();
    } catch (_) {
      // No saved feedback is fine for a first load.
    }
  }

  Future<void> _loadTagCatalog() async {
    final folder = _selectedFolder;
    if (folder == null || folder.isEmpty) {
      return;
    }
    try {
      _availableTags = await _feedbackBridge.loadTagCatalog(folder);
      notifyListeners();
    } catch (_) {
      // Fallback to tags discovered in feedback below.
      _availableTags = _feedbackByPath.values.expand((item) => item.tags).toSet().toList()..sort();
      notifyListeners();
    }
  }

  Future<void> _loadSelectedMetadata() async {
    final entry = selectedEntry;
    if (entry == null) {
      _selectedMetadata = null;
      _metadataError = null;
      _isLoadingMetadata = false;
      notifyListeners();
      return;
    }

    final cached = _metadataCache[entry.file.path];
    if (cached != null) {
      _selectedMetadata = cached;
      _metadataError = null;
      _isLoadingMetadata = false;
      notifyListeners();
      return;
    }

    final requestId = ++_metadataRequestId;
    _isLoadingMetadata = true;
    _selectedMetadata = null;
    _metadataError = null;
    notifyListeners();

    try {
      final snapshot = await _metadataBridge.inspectFile(entry.file.path);
      if (requestId != _metadataRequestId) {
        return;
      }
      _metadataCache[entry.file.path] = snapshot;
      _selectedMetadata = snapshot;
      _metadataError = null;
    } catch (error) {
      if (requestId != _metadataRequestId) {
        return;
      }
      _selectedMetadata = null;
      _metadataError = error.toString();
    } finally {
      if (requestId == _metadataRequestId) {
        _isLoadingMetadata = false;
        notifyListeners();
      }
    }
  }

  Future<void> _loadSelectedPreview() async {
    final entry = selectedEntry;
    if (entry == null) {
      _selectedPreviewPath = null;
      _previewError = null;
      _selectedPreviewSnapshot = null;
      _isLoadingPreview = false;
      notifyListeners();
      return;
    }

    final renderSourcePath = await _resolvePreviewRenderSource(entry);

    if (entry.isPreviewable) {
      _selectedPreviewPath = entry.file.path;
      _previewError = null;
      _selectedPreviewSnapshot = null;
      _isLoadingPreview = false;
      notifyListeners();
      return;
    }

    final cacheKey = _previewCacheKey(renderSourcePath);
    final cached = _previewCache[cacheKey];
    if (cached != null) {
      _selectedPreviewPath = cached;
      _selectedPreviewSnapshot = _previewSnapshotCache[cacheKey];
      _previewError = null;
      _isLoadingPreview = false;
      notifyListeners();
      return;
    }

    final requestId = ++_previewRequestId;
    _selectedPreviewPath = null;
    _selectedPreviewSnapshot = null;
    _previewError = null;
    _isLoadingPreview = true;
    notifyListeners();

    try {
      final snapshot = await _previewBridge.renderPreview(
        renderSourcePath,
        metadataSourcePath: entry.file.path,
      );
      if (requestId != _previewRequestId) {
        return;
      }
      _previewCache[cacheKey] = snapshot.outputPath;
      _previewSnapshotCache[cacheKey] = snapshot;
      _selectedPreviewPath = snapshot.outputPath;
      _selectedPreviewSnapshot = snapshot;
      _previewError = null;
    } catch (error) {
      if (requestId != _previewRequestId) {
        return;
      }
      _selectedPreviewPath = null;
      _selectedPreviewSnapshot = null;
      _previewError = error.toString();
    } finally {
      if (requestId == _previewRequestId) {
        _isLoadingPreview = false;
        notifyListeners();
      }
    }
  }

  Future<PreviewSnapshot?> _ensureSelectedPreviewSnapshotForExposure() async {
    final entry = selectedEntry;
    if (entry == null) {
      return null;
    }

    if (_selectedPreviewSnapshot?.suggestedExposureEv != null) {
      return _selectedPreviewSnapshot;
    }

    final renderSourcePath = await _resolvePreviewRenderSource(entry);
    final cacheKey = _previewCacheKey(renderSourcePath);
    final cachedSnapshot = _previewSnapshotCache[cacheKey];
    if (cachedSnapshot?.suggestedExposureEv != null) {
      _selectedPreviewSnapshot = cachedSnapshot;
      notifyListeners();
      return cachedSnapshot;
    }

    final snapshot = await _previewBridge.renderPreview(
      renderSourcePath,
      metadataSourcePath: entry.file.path,
    );
    _previewSnapshotCache[cacheKey] = snapshot;
    if (!entry.isPreviewable) {
      _previewCache[cacheKey] = snapshot.outputPath;
      if (selectedEntry?.file.path == entry.file.path) {
        _selectedPreviewPath = snapshot.outputPath;
      }
    }
    if (selectedEntry?.file.path == entry.file.path) {
      _selectedPreviewSnapshot = snapshot;
      notifyListeners();
    }
    return snapshot;
  }

  Future<void> _loadRawThumbnail(PhotoEntry entry) async {
    final renderSourcePath = await _resolvePreviewRenderSource(entry);
    final cacheKey = _thumbnailCacheKey(renderSourcePath);
    try {
      final snapshot = await _previewBridge.renderPreview(
        renderSourcePath,
        metadataSourcePath: entry.file.path,
        maxWidth: 240,
        maxHeight: 240,
        variant: 'thumb',
      );
      _previewCache[cacheKey] = snapshot.outputPath;
      _previewSnapshotCache[cacheKey] = snapshot;
    } catch (_) {
      // Keep placeholder if thumbnail rendering fails.
    } finally {
      _thumbnailRequests.remove(cacheKey);
      notifyListeners();
    }
  }

  void _primeThumbnailWindow() {
    if (_selectedIndex < 0 || _entries.isEmpty) {
      return;
    }
    final start = (_selectedIndex - 8).clamp(0, _entries.length - 1);
    final end = (_selectedIndex + 8).clamp(0, _entries.length - 1);
    for (var index = start; index <= end; index += 1) {
      requestThumbnail(_entries[index]);
    }
  }

  String _previewCacheKey(String path) => 'preview::$path';

  String _thumbnailCacheKey(String path) => 'thumb::$path';

  Future<String> _resolvePreviewRenderSource(PhotoEntry entry) async {
    if (entry.isPreviewable) {
      return entry.file.path;
    }

    final directory = entry.file.parent;
    final baseName = p.basenameWithoutExtension(entry.file.path).toLowerCase();
    const preferredExtensions = <String>['.jpg', '.jpeg'];

    for (final extension in preferredExtensions) {
      final candidate = File(p.join(directory.path, '$baseName$extension'));
      if (await candidate.exists()) {
        return candidate.path;
      }

      final originalCase = File(p.join(directory.path, '${p.basenameWithoutExtension(entry.file.path)}$extension'));
      if (await originalCase.exists()) {
        return originalCase.path;
      }
    }

    final entities = await directory.list().toList();
    for (final entity in entities) {
      if (entity is! File) {
        continue;
      }
      final entityBaseName = p.basenameWithoutExtension(entity.path).toLowerCase();
      final extension = p.extension(entity.path).toLowerCase();
      if (entityBaseName == baseName && previewableExtensions.contains(extension)) {
        return entity.path;
      }
    }

    return entry.file.path;
  }

  Future<_DirectoryScanResult> _scanDirectory(Directory directory, {required bool recursive}) async {
    final files = <File>[];
    var scanned = 0;
    var subdirectoryCount = 0;
    final stream = recursive ? directory.list(recursive: true) : directory.list();
    await for (final entity in stream) {
      scanned += 1;
      if (entity is Directory && !recursive) {
        subdirectoryCount += 1;
      }
      if (entity is File) {
        final name = p.basename(entity.path);
        if (!name.startsWith('.')) {
          final lowerPath = entity.path.toLowerCase();
          if (supportedPhotoExtensions.any(lowerPath.endsWith)) {
            files.add(entity);
          }
        }
      }

      if (scanned % 200 == 0) {
        _statusText = 'Taranıyor... $scanned oge, ${files.length} fotograf bulundu';
        notifyListeners();
        await Future<void>.delayed(Duration.zero);
      }
    }
    return _DirectoryScanResult(files: files, subdirectoryCount: subdirectoryCount);
  }

  String _normalizePath(String path) {
    try {
      return File(path).absolute.resolveSymbolicLinksSync();
    } catch (_) {
      return p.normalize(File(path).absolute.path);
    }
  }
}

class _DirectoryScanResult {
  _DirectoryScanResult({required this.files, required this.subdirectoryCount});

  final List<File> files;
  final int subdirectoryCount;
}
