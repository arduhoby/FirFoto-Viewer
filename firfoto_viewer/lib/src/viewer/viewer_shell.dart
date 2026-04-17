import 'dart:async';
import 'dart:io';
import 'dart:math' as math;

import 'package:file_selector/file_selector.dart';
import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:path/path.dart' as p;

import 'analysis_summary.dart';
import 'file_metadata.dart';
import 'photo_entry.dart';
import 'preview_snapshot.dart';
import 'viewer_controller.dart';

const MethodChannel _openFileChannel = MethodChannel('firfoto/open_file');
const String _brandAssetPath = 'assets/branding/firfoto_logo.png';
const List<String> _categoryOptions = <String>[
  'general',
  'bird',
  'wildlife',
  'portrait',
  'landscape',
  'sky',
  'aerial',
  'product',
  'macro',
];

enum _DecisionFilter {
  all('All'),
  selected('Selected'),
  candidate('Candidate'),
  rejected('Rejected'),
  bestOfBurst('Best');

  const _DecisionFilter(this.label);

  final String label;
}

enum _SortMode {
  date('Date'),
  name('Name'),
  extension('Ext');

  const _SortMode(this.label);

  final String label;
}

enum _ViewerMode {
  basic('Basic'),
  advanced('Advanced');

  const _ViewerMode(this.label);

  final String label;
}

enum _DrawerPage {
  settings('Settings'),
  details('Details');

  const _DrawerPage(this.label);

  final String label;
}

String _buildStampLabel() {
  final now = DateTime.now();
  String two(int value) => value.toString().padLeft(2, '0');
  return 'Build ${now.year}-${two(now.month)}-${two(now.day)} ${two(now.hour)}:${two(now.minute)}';
}

class ViewerShell extends StatefulWidget {
  const ViewerShell({super.key});

  @override
  State<ViewerShell> createState() => _ViewerShellState();
}

class _ViewerShellState extends State<ViewerShell> {
  final ViewerController controller = ViewerController();
  final FocusNode _focusNode = FocusNode();
  final GlobalKey<ScaffoldState> _scaffoldKey = GlobalKey<ScaffoldState>();
  final ScrollController _thumbScrollController = ScrollController();
  final TransformationController _transformationController =
      TransformationController();
  Size _previewViewportSize = Size.zero;
  _ViewerMode _viewerMode = _ViewerMode.basic;
  _DrawerPage _drawerPage = _DrawerPage.settings;
  _DecisionFilter _decisionFilter = _DecisionFilter.all;
  _SortMode _sortMode = _SortMode.date;
  bool _sortAscending = false;
  String _activeTagFilter = 'All';
  bool _showFileList = false;
  bool _showCameraAf = false;
  bool _showSharpGuess = true;
  bool _showDetails = false;
  bool _showThumbnails = false;
  bool _showFileListExpanded = true;
  bool _autoExposureOnOpen = false;
  bool _autoExposureActive = false;
  int _rotationQuarterTurns = 0;
  String? _rotationPath;
  int _thumbnailSize = 64;
  String? _autoExposureAppliedPath;
  bool _autoExposureInFlight = false;

  @override
  void initState() {
    super.initState();
    controller.addListener(_handleControllerChanged);
    _openFileChannel.setMethodCallHandler(_handleOpenFileCall);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      unawaited(_consumePendingOpenFiles());
    });
  }

  @override
  void dispose() {
    _openFileChannel.setMethodCallHandler(null);
    controller.removeListener(_handleControllerChanged);
    controller.dispose();
    _focusNode.dispose();
    _thumbScrollController.dispose();
    _transformationController.dispose();
    super.dispose();
  }

  void _handleControllerChanged() {
    _syncPreviewTransform();
    _syncRotationSelection();
    _ensureThumbVisible();
    unawaited(_maybeAutoApplyExposure());
    if (mounted) {
      setState(() {});
    }
  }

  void _syncRotationSelection() {
    final path = controller.selectedEntry?.file.path;
    if (path == _rotationPath) {
      return;
    }
    _rotationPath = path;
    _rotationQuarterTurns = 0;
  }

  void _syncPreviewTransform() {
    final zoom = controller.zoom;
    if (_previewViewportSize == Size.zero) {
      _transformationController.value = Matrix4.diagonal3Values(zoom, zoom, 1);
      return;
    }
    final dx = (_previewViewportSize.width * (1 - zoom)) / 2;
    final dy = (_previewViewportSize.height * (1 - zoom)) / 2;
    _transformationController.value = Matrix4.identity()
      ..translateByDouble(dx, dy, 0, 1)
      ..scaleByDouble(zoom, zoom, 1, 1);
  }

  void _updatePreviewViewportSize(Size size) {
    if ((_previewViewportSize.width - size.width).abs() < 0.5 &&
        (_previewViewportSize.height - size.height).abs() < 0.5) {
      return;
    }
    _previewViewportSize = size;
    _syncPreviewTransform();
  }

  Future<void> _maybeAutoApplyExposure() async {
    if (!_autoExposureOnOpen || _autoExposureInFlight) {
      return;
    }
    final entry = controller.selectedEntry;
    if (entry == null) {
      return;
    }
    final path = entry.file.path;
    if (_autoExposureAppliedPath == path) {
      return;
    }
    _autoExposureInFlight = true;
    try {
      final applied = await controller.applyAutoExposureForSelected();
      if (!mounted || controller.selectedEntry?.file.path != path) {
        return;
      }
      _autoExposureAppliedPath = path;
      if (applied != null) {
        setState(() {
          _autoExposureActive = true;
        });
      }
    } finally {
      _autoExposureInFlight = false;
    }
  }

  Future<void> _consumePendingOpenFiles() async {
    try {
      final pendingPaths = await _openFileChannel.invokeListMethod<String>(
        'consumePendingOpenFiles',
      );
      await _openFileChannel.invokeMethod<void>('markOpenFileClientReady');
      if (!mounted || pendingPaths == null || pendingPaths.isEmpty) {
        return;
      }
      await _openPhotoFromPath(pendingPaths.first);
    } catch (_) {
      // Finder open-file bridge is optional for development flows.
    }
  }

  Future<void> _handleOpenFileCall(MethodCall call) async {
    if (call.method != 'openFiles') {
      return;
    }
    final arguments = call.arguments;
    final paths = switch (arguments) {
      final List<dynamic> values => values.whereType<String>().toList(),
      _ => const <String>[],
    };
    if (!mounted || paths.isEmpty) {
      return;
    }
    await _openPhotoFromPath(paths.first);
  }

  Future<void> _openPhotoFromPath(String path) async {
    _setViewerMode(_ViewerMode.basic);
    await controller.openPhotoFile(path);
    if (!mounted) {
      return;
    }
    if (controller.entries.isEmpty) {
      return;
    }
    ScaffoldMessenger.of(context).hideCurrentSnackBar();
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('${p.basename(path)} basic modda acildi.'),
        duration: const Duration(seconds: 3),
      ),
    );
  }

  void _showLoadResultBanner() {
    final entryCount = controller.entries.length;
    if (entryCount == 0) {
      return;
    }
    ScaffoldMessenger.of(context).hideCurrentSnackBar();
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('$entryCount dosya yuklendi, ilk fotograf secildi.'),
        duration: const Duration(seconds: 3),
      ),
    );
  }

  Future<void> _pickFolder() async {
    try {
      final folder = await getDirectoryPath(confirmButtonText: 'Sec');
      if (!mounted) {
        return;
      }
      if (folder == null || folder.isEmpty) {
        return;
      }
      controller.setFolder(folder);
      ScaffoldMessenger.of(context).hideCurrentSnackBar();
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Klasor secildi, yukleme baslatiliyor...'),
          duration: Duration(seconds: 2),
        ),
      );
      await controller.loadFolder();
      if (!mounted) {
        return;
      }
      _showLoadResultBanner();
    } catch (error) {
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text('Browse acilamadi: $error')));
    }
  }

  void _ensureThumbVisible() {
    if (!mounted ||
        controller.entries.isEmpty ||
        !_thumbScrollController.hasClients) {
      return;
    }
    final selectedIndex = controller.selectedIndex;
    if (selectedIndex < 0) {
      return;
    }
    final targetOffset = (selectedIndex * (_thumbnailSize + 18.0)) - 180.0;
    final clamped = targetOffset.clamp(
      0.0,
      _thumbScrollController.position.maxScrollExtent,
    );
    _thumbScrollController.animateTo(
      clamped,
      duration: const Duration(milliseconds: 180),
      curve: Curves.easeOutCubic,
    );
  }

  void _setViewerMode(_ViewerMode mode) {
    setState(() {
      _viewerMode = mode;
      if (mode == _ViewerMode.basic) {
        _showFileList = false;
        _showThumbnails = false;
      } else {
        _showFileList = true;
        _showThumbnails = false;
        _showFileListExpanded = true;
      }
    });
    if (mode == _ViewerMode.advanced &&
        _showDetails &&
        controller.selectedEntry != null) {
      _openDetailsDrawer();
    }
  }

  Future<void> _applyAutoExposureFromButton() async {
    final applied = await controller.applyAutoExposureForSelected();
    if (!mounted) {
      return;
    }
    if (applied == null) {
      ScaffoldMessenger.of(context).hideCurrentSnackBar();
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Otomatik EV hesaplanamadi.')),
      );
      return;
    }
    setState(() {
      _autoExposureActive = true;
      _autoExposureAppliedPath = controller.selectedEntry?.file.path;
    });
    ScaffoldMessenger.of(context).hideCurrentSnackBar();
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text('Otomatik EV uygulandi: ${_formatEv(applied)}')),
    );
  }

  void _closeDrawer() {
    _scaffoldKey.currentState?.closeEndDrawer();
  }

  void _openSettingsDrawer() {
    setState(() {
      _drawerPage = _DrawerPage.settings;
    });
    _scaffoldKey.currentState?.openEndDrawer();
  }

  void _openDetailsDrawer() {
    if (controller.selectedEntry == null) {
      return;
    }
    setState(() {
      _drawerPage = _DrawerPage.details;
    });
    _scaffoldKey.currentState?.openEndDrawer();
  }

  @override
  Widget build(BuildContext context) {
    final selected = controller.selectedEntry;
    final visibleEntries = _filteredEntries();
    final hasLoadedContent = controller.entries.isNotEmpty || selected != null;
    final useBasicOverlayHud =
        _viewerMode == _ViewerMode.basic && selected != null;
    final effectiveShowFileList =
        _viewerMode == _ViewerMode.advanced && _showFileList;
    final effectiveShowCameraAf = _showCameraAf;
    final effectiveShowSharpGuess = _showSharpGuess;
    final effectiveShowThumbnails =
        _viewerMode == _ViewerMode.advanced && _showThumbnails;

    return Shortcuts(
      shortcuts: <ShortcutActivator, Intent>{
        const SingleActivator(LogicalKeyboardKey.arrowLeft): const _MoveIntent(
          -1,
        ),
        const SingleActivator(LogicalKeyboardKey.arrowRight): const _MoveIntent(
          1,
        ),
        const SingleActivator(LogicalKeyboardKey.arrowUp): const _ZoomIntent(
          true,
        ),
        const SingleActivator(LogicalKeyboardKey.arrowDown): const _ZoomIntent(
          false,
        ),
      },
      child: Actions(
        actions: <Type, Action<Intent>>{
          _MoveIntent: CallbackAction<_MoveIntent>(
            onInvoke: (intent) {
              if (intent.delta > 0) {
                controller.selectNext();
              } else {
                controller.selectPrevious();
              }
              return null;
            },
          ),
          _ZoomIntent: CallbackAction<_ZoomIntent>(
            onInvoke: (intent) {
              if (intent.zoomIn) {
                controller.zoomIn();
              } else {
                controller.zoomOut();
              }
              return null;
            },
          ),
        },
        child: Focus(
          autofocus: true,
          focusNode: _focusNode,
          child: Listener(
            onPointerDown: (PointerDownEvent event) {
              _focusNode.requestFocus();
              if ((event.buttons & kBackMouseButton) != 0) {
                controller.selectPrevious();
              } else if ((event.buttons & kForwardMouseButton) != 0) {
                controller.selectNext();
              }
            },
            child: GestureDetector(
              behavior: HitTestBehavior.translucent,
              onTap: _focusNode.requestFocus,
              child: Scaffold(
                key: _scaffoldKey,
                endDrawer: _buildEndDrawer(
                  selected: selected,
                  effectiveShowFileList: effectiveShowFileList,
                  effectiveShowThumbnails: effectiveShowThumbnails,
                  effectiveShowCameraAf: effectiveShowCameraAf,
                  effectiveShowSharpGuess: effectiveShowSharpGuess,
                ),
                body: DecoratedBox(
                  decoration: const BoxDecoration(
                    gradient: LinearGradient(
                      colors: <Color>[Color(0xFF15171B), Color(0xFF0B0C0F)],
                      begin: Alignment.topLeft,
                      end: Alignment.bottomRight,
                    ),
                  ),
                  child: SafeArea(
                    child: LayoutBuilder(
                      builder: (BuildContext context, BoxConstraints constraints) {
                        final compact =
                            constraints.maxWidth < 1500 ||
                            constraints.maxHeight < 920;
                        return Stack(
                          children: <Widget>[
                            Padding(
                              padding: const EdgeInsets.all(16),
                              child: Column(
                                children: <Widget>[
                                  if (!useBasicOverlayHud) ...<Widget>[
                                    _TopBar(
                                      selectedFolder: controller.selectedFolder,
                                      hasActivePhoto: selected != null,
                                      viewerMode: _viewerMode,
                                      isLoading: controller.isLoading,
                                      isAnalyzing: controller.isAnalyzing,
                                      analysisProgress:
                                          controller.analysisProgress,
                                      analysisTotal: controller.analysisTotal,
                                      statusText: controller.statusText,
                                      onBrowse: _pickFolder,
                                      onOpenSettings: _openSettingsDrawer,
                                      onModeChanged: _setViewerMode,
                                      compact: compact,
                                    ),
                                    const SizedBox(height: 10),
                                  ],
                                  Expanded(
                                    child: !hasLoadedContent
                                        ? _centerPane(
                                            selected,
                                            compact: compact,
                                            effectiveShowThumbnails:
                                                effectiveShowThumbnails,
                                            effectiveShowCameraAf:
                                                effectiveShowCameraAf,
                                            effectiveShowSharpGuess:
                                                effectiveShowSharpGuess,
                                            effectiveShowFileList:
                                                effectiveShowFileList,
                                            selectedAnalysis:
                                                controller.selectedAnalysis,
                                            onOpenDetails: _openDetailsDrawer,
                                            showBasicHud: useBasicOverlayHud,
                                            selectedFolder:
                                                controller.selectedFolder,
                                            onBrowse: _pickFolder,
                                            onOpenSettings: _openSettingsDrawer,
                                            onModeChanged: _setViewerMode,
                                            viewerMode: _viewerMode,
                                          )
                                        : compact
                                        ? Row(
                                            children: <Widget>[
                                              if (effectiveShowFileList) ...<
                                                Widget
                                              >[
                                                _buildFilePanel(
                                                  entries: visibleEntries,
                                                  selectedPath:
                                                      selected?.file.path,
                                                  compact: true,
                                                ),
                                                const SizedBox(width: 12),
                                              ],
                                              Expanded(
                                                child: _centerPane(
                                                  selected,
                                                  compact: true,
                                                  effectiveShowThumbnails:
                                                      effectiveShowThumbnails,
                                                  effectiveShowCameraAf:
                                                      effectiveShowCameraAf,
                                                  effectiveShowSharpGuess:
                                                      effectiveShowSharpGuess,
                                                  effectiveShowFileList:
                                                      effectiveShowFileList,
                                                  selectedAnalysis: controller
                                                      .selectedAnalysis,
                                                  onOpenDetails:
                                                      _openDetailsDrawer,
                                                  showBasicHud:
                                                      useBasicOverlayHud,
                                                  selectedFolder:
                                                      controller.selectedFolder,
                                                  onBrowse: _pickFolder,
                                                  onOpenSettings:
                                                      _openSettingsDrawer,
                                                  onModeChanged: _setViewerMode,
                                                  viewerMode: _viewerMode,
                                                ),
                                              ),
                                            ],
                                          )
                                        : Row(
                                            children: <Widget>[
                                              if (effectiveShowFileList) ...<
                                                Widget
                                              >[
                                                _buildFilePanel(
                                                  entries: visibleEntries,
                                                  selectedPath:
                                                      selected?.file.path,
                                                  compact: false,
                                                ),
                                                const SizedBox(width: 12),
                                              ],
                                              Expanded(
                                                child: _centerPane(
                                                  selected,
                                                  compact: false,
                                                  effectiveShowThumbnails:
                                                      effectiveShowThumbnails,
                                                  effectiveShowCameraAf:
                                                      effectiveShowCameraAf,
                                                  effectiveShowSharpGuess:
                                                      effectiveShowSharpGuess,
                                                  effectiveShowFileList:
                                                      effectiveShowFileList,
                                                  selectedAnalysis: controller
                                                      .selectedAnalysis,
                                                  onOpenDetails:
                                                      _openDetailsDrawer,
                                                  showBasicHud:
                                                      useBasicOverlayHud,
                                                  selectedFolder:
                                                      controller.selectedFolder,
                                                  onBrowse: _pickFolder,
                                                  onOpenSettings:
                                                      _openSettingsDrawer,
                                                  onModeChanged: _setViewerMode,
                                                  viewerMode: _viewerMode,
                                                ),
                                              ),
                                            ],
                                          ),
                                  ),
                                ],
                              ),
                            ),
                            Positioned(
                              right: 18,
                              bottom: 8,
                              child: IgnorePointer(
                                child: Text(
                                  _buildStampLabel(),
                                  style: Theme.of(context).textTheme.labelSmall
                                      ?.copyWith(
                                        color: Colors.white38,
                                        fontSize: 10,
                                      ),
                                ),
                              ),
                            ),
                          ],
                        );
                      },
                    ),
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _centerPane(
    PhotoEntry? selected, {
    required bool compact,
    required bool effectiveShowThumbnails,
    required bool effectiveShowCameraAf,
    required bool effectiveShowSharpGuess,
    required bool effectiveShowFileList,
    required AnalysisSummary? selectedAnalysis,
    required VoidCallback onOpenDetails,
    required bool showBasicHud,
    required String? selectedFolder,
    required Future<void> Function() onBrowse,
    required VoidCallback onOpenSettings,
    required ValueChanged<_ViewerMode> onModeChanged,
    required _ViewerMode viewerMode,
  }) {
    final showThumbnails =
        effectiveShowThumbnails && controller.entries.isNotEmpty;
    return Column(
      children: <Widget>[
        Expanded(
          child: ConstrainedBox(
            constraints: const BoxConstraints(minWidth: 400),
            child: _PreviewSurface(
              entry: selected,
              previewPath: controller.selectedPreviewPath,
              previewSnapshot: controller.selectedPreviewSnapshot,
              metadata: controller.selectedMetadata,
              isLoadingPreview: controller.isLoadingPreview,
              previewError: controller.previewError,
              exposureEv: controller.exposureEv,
              exposureAdjustMode: _autoExposureActive,
              rotationQuarterTurns: _rotationQuarterTurns,
              analysis: selectedAnalysis,
              showCameraAf: effectiveShowCameraAf,
              showSharpGuess: effectiveShowSharpGuess,
              selectedFolder: controller.selectedFolder,
              isAnalyzing: controller.isAnalyzing,
              zoom: controller.zoom,
              transformationController: _transformationController,
              onViewportSizeChanged: _updatePreviewViewportSize,
              onResetZoom: controller.resetZoom,
              onRotateLeft: () {
                setState(() {
                  _rotationQuarterTurns = (_rotationQuarterTurns + 3) % 4;
                });
              },
              onRotateRight: () {
                setState(() {
                  _rotationQuarterTurns = (_rotationQuarterTurns + 1) % 4;
                });
              },
              onToggleExposureMode: () {
                if (_autoExposureActive) {
                  setState(() {
                    _autoExposureActive = false;
                  });
                  return;
                }
                unawaited(_applyAutoExposureFromButton());
              },
              onAdjustZoom: (double delta) {
                controller.setZoom(controller.zoom * (1 + delta));
              },
              onAdjustExposure: (double delta) {
                setState(() {
                  _autoExposureActive = false;
                });
                controller.setExposureEv(controller.exposureEv + delta);
              },
              onResetExposure: () {
                setState(() {
                  _autoExposureActive = false;
                });
                controller.resetExposureEv();
              },
              onAnalyze: controller.startAnalysis,
              onCancelAnalyze: controller.cancelAnalysis,
              onPrevious: controller.selectPrevious,
              onNext: controller.selectNext,
              onOpenDetails: _openDetailsDrawer,
              onToggleSharpGuess: () {
                setState(() {
                  _showSharpGuess = !_showSharpGuess;
                });
              },
              onToggleCameraAf: () {
                setState(() {
                  _showCameraAf = !_showCameraAf;
                });
              },
              onShare: () async {
                if (selected == null) {
                  return;
                }
                await Clipboard.setData(
                  ClipboardData(
                    text: '${selected.name}\n${selected.file.path}',
                  ),
                );
                if (!mounted) {
                  return;
                }
                ScaffoldMessenger.of(context).hideCurrentSnackBar();
                ScaffoldMessenger.of(context).showSnackBar(
                  SnackBar(
                    content: Text('${selected.name} panoya kopyalandi.'),
                  ),
                );
              },
              onToggleQuickTag: (String value) async {
                try {
                  await controller.toggleSelectedTag(value);
                } catch (error) {
                  if (!mounted) {
                    return;
                  }
                  ScaffoldMessenger.of(context).showSnackBar(
                    SnackBar(content: Text('Etiket kaydedilemedi: $error')),
                  );
                }
              },
              showBasicHud: showBasicHud,
              hudSelectedFolder: selectedFolder,
              hudOnBrowse: onBrowse,
              hudOnOpenSettings: onOpenSettings,
              hudOnModeChanged: onModeChanged,
              hudViewerMode: viewerMode,
            ),
          ),
        ),
        if (showThumbnails) ...<Widget>[
          const SizedBox(height: 12),
          _ThumbnailStrip(
            entries: controller.entries,
            selectedIndex: controller.selectedIndex,
            thumbnailResolver: controller.thumbnailPathFor,
            onSelected: controller.selectByIndex,
            onVisible: controller.requestThumbnail,
            scrollController: _thumbScrollController,
            thumbnailSize: _thumbnailSize,
            compact: compact,
          ),
        ],
      ],
    );
  }

  Widget _buildFilePanel({
    required List<PhotoEntry> entries,
    required String? selectedPath,
    required bool compact,
  }) {
    if (!_showFileListExpanded) {
      return Container(
        width: 28,
        decoration: BoxDecoration(
          color: const Color(0xCC16181D),
          borderRadius: BorderRadius.circular(18),
          border: Border.all(color: Colors.white.withValues(alpha: 0.06)),
        ),
        child: Center(
          child: IconButton(
            tooltip: 'Dosya panelini ac',
            onPressed: () {
              setState(() {
                _showFileListExpanded = true;
              });
            },
            visualDensity: VisualDensity.compact,
            padding: EdgeInsets.zero,
            icon: const Icon(Icons.chevron_right_rounded, size: 18),
          ),
        ),
      );
    }

    return SizedBox(
      width: compact ? 168 : 182,
      child: _FileList(
        entries: entries,
        selectedPath: selectedPath,
        analysisLookup: controller.analysisFor,
        activeFilter: _decisionFilter,
        activeSort: _sortMode,
        sortAscending: _sortAscending,
        activeTagFilter: _activeTagFilter,
        compact: compact,
        onFilterChanged: (_DecisionFilter value) {
          setState(() {
            _decisionFilter = value;
          });
        },
        onSortChanged: (_SortMode value) {
          setState(() {
            _sortMode = value;
          });
        },
        onSortDirectionChanged: () {
          setState(() {
            _sortAscending = !_sortAscending;
          });
        },
        onTagFilterChanged: (String value) {
          setState(() {
            _activeTagFilter = value;
          });
        },
        onSelected: controller.selectByIndex,
        onToggleCollapsed: () {
          setState(() {
            _showFileListExpanded = false;
          });
        },
      ),
    );
  }

  List<PhotoEntry> _filteredEntries() {
    final filtered = controller.entries.where((PhotoEntry entry) {
      final analysis = controller.analysisFor(entry);
      final decision = analysis?.decision;
      switch (_decisionFilter) {
        case _DecisionFilter.all:
          break;
        case _DecisionFilter.selected:
          if (decision != 'selected') {
            return false;
          }
          break;
        case _DecisionFilter.candidate:
          if (decision != 'candidate') {
            return false;
          }
          break;
        case _DecisionFilter.rejected:
          if (decision != 'rejected') {
            return false;
          }
          break;
        case _DecisionFilter.bestOfBurst:
          if (decision != 'best_of_burst') {
            return false;
          }
          break;
      }
      if (_activeTagFilter != 'All' &&
          !(analysis?.tags.contains(_activeTagFilter) ?? false)) {
        return false;
      }
      return true;
    }).toList();

    filtered.sort((PhotoEntry a, PhotoEntry b) {
      late final int compare;
      switch (_sortMode) {
        case _SortMode.date:
          compare = a.modifiedAt.compareTo(b.modifiedAt);
          break;
        case _SortMode.name:
          compare = a.name.toLowerCase().compareTo(b.name.toLowerCase());
          break;
        case _SortMode.extension:
          compare = a.extension.compareTo(b.extension);
          break;
      }
      if (compare != 0) {
        return _sortAscending ? compare : -compare;
      }
      return a.name.toLowerCase().compareTo(b.name.toLowerCase());
    });
    return filtered;
  }

  Widget _buildEndDrawer({
    required PhotoEntry? selected,
    required bool effectiveShowFileList,
    required bool effectiveShowThumbnails,
    required bool effectiveShowCameraAf,
    required bool effectiveShowSharpGuess,
  }) {
    final theme = Theme.of(context);
    final showingSettings = _drawerPage == _DrawerPage.settings;
    return Drawer(
      width: 380,
      backgroundColor: const Color(0xFF111318),
      child: SafeArea(
        child: Column(
          children: <Widget>[
            Padding(
              padding: const EdgeInsets.fromLTRB(18, 14, 18, 8),
              child: Row(
                children: <Widget>[
                  Text(
                    showingSettings ? 'Settings' : 'Details',
                    style: theme.textTheme.titleLarge?.copyWith(
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  const Spacer(),
                  IconButton(
                    tooltip: 'Kapat',
                    onPressed: _closeDrawer,
                    icon: const Icon(Icons.close_rounded),
                  ),
                ],
              ),
            ),
            Expanded(
              child: showingSettings
                  ? ListView(
                      key: const ValueKey<String>('settings'),
                      padding: const EdgeInsets.symmetric(
                        horizontal: 18,
                        vertical: 4,
                      ),
                      children: <Widget>[
                        _DrawerSectionTitle('View Mode'),
                        Text(
                          _viewerMode == _ViewerMode.basic
                              ? 'Basic: sadece fotoğraf ve üzerindeki ikonlar.'
                              : 'Advanced: detayli inceleme araçlari aktif.',
                          style: theme.textTheme.bodySmall?.copyWith(
                            color: Colors.white70,
                          ),
                        ),
                        const SizedBox(height: 14),
                        _DrawerSectionTitle('Visibility'),
                        SwitchListTile(
                          contentPadding: EdgeInsets.zero,
                          title: const Text('Files panel'),
                          subtitle: const Text(
                            'Dosya isimleri solda görünsün.',
                          ),
                          value: _showFileList,
                          onChanged: (bool value) {
                            setState(() {
                              _showFileList = value;
                            });
                          },
                        ),
                        SwitchListTile(
                          contentPadding: EdgeInsets.zero,
                          title: const Text('Thumbnail strip'),
                          subtitle: const Text(
                            'Foto üstünde küçük thumbnail’ler.',
                          ),
                          value: _showThumbnails,
                          onChanged: (bool value) {
                            setState(() {
                              _showThumbnails = value;
                            });
                          },
                        ),
                        SwitchListTile(
                          contentPadding: EdgeInsets.zero,
                          title: const Text('Sharp guess'),
                          subtitle: const Text('Tahmini netlik noktası.'),
                          value: _showSharpGuess,
                          onChanged: (bool value) {
                            setState(() {
                              _showSharpGuess = value;
                            });
                          },
                        ),
                        SwitchListTile(
                          contentPadding: EdgeInsets.zero,
                          title: const Text('Camera AF'),
                          subtitle: const Text('Kamera AF kutulari.'),
                          value: _showCameraAf,
                          onChanged: (bool value) {
                            setState(() {
                              _showCameraAf = value;
                            });
                          },
                        ),
                        SwitchListTile(
                          contentPadding: EdgeInsets.zero,
                          title: const Text('Auto EV on open'),
                          subtitle: const Text(
                            'Acilan her fotoda uygun EV otomatik uygulansin.',
                          ),
                          value: _autoExposureOnOpen,
                          onChanged: (bool value) {
                            setState(() {
                              _autoExposureOnOpen = value;
                              if (!value) {
                                _autoExposureAppliedPath = null;
                              }
                            });
                            if (value) {
                              unawaited(_maybeAutoApplyExposure());
                            }
                          },
                        ),
                        SwitchListTile(
                          contentPadding: EdgeInsets.zero,
                          title: const Text('Details auto open'),
                          subtitle: const Text(
                            'Advanced modda secili foto ile Details kendiliginden acilsin.',
                          ),
                          value: _showDetails,
                          onChanged: (bool value) {
                            setState(() {
                              _showDetails = value;
                            });
                          },
                        ),
                        const SizedBox(height: 12),
                        _DrawerSectionTitle('Thumbnail Size'),
                        const SizedBox(height: 8),
                        Wrap(
                          spacing: 8,
                          children: <int>[64, 100, 140].map((int size) {
                            return ChoiceChip(
                              selected: _thumbnailSize == size,
                              label: Text('$size px'),
                              onSelected: (_) {
                                setState(() {
                                  _thumbnailSize = size;
                                });
                              },
                            );
                          }).toList(),
                        ),
                        const SizedBox(height: 12),
                        _DrawerSectionTitle('Hints'),
                        Text(
                          'Preview üstündeki kontroller zaten basic moda uygun şekilde sadeleştiriliyor.',
                          style: theme.textTheme.bodySmall?.copyWith(
                            color: Colors.white70,
                          ),
                        ),
                        const SizedBox(height: 12),
                        _DrawerSectionTitle('Current State'),
                        Text(
                          'Files panel: ${effectiveShowFileList ? 'open' : 'hidden'}\n'
                          'Thumbnails: ${effectiveShowThumbnails ? 'open' : 'hidden'}\n'
                          'Camera AF: ${effectiveShowCameraAf ? 'open' : 'hidden'}\n'
                          'Sharp guess: ${effectiveShowSharpGuess ? 'open' : 'hidden'}\n'
                          'Auto EV: ${_autoExposureOnOpen ? 'open' : 'hidden'}\n'
                          'Details auto open: ${_showDetails ? 'open' : 'hidden'}',
                          style: theme.textTheme.bodySmall?.copyWith(
                            color: Colors.white70,
                          ),
                        ),
                      ],
                    )
                  : Padding(
                      padding: const EdgeInsets.fromLTRB(18, 4, 18, 18),
                      child: _MetadataPanel(
                        entry: controller.selectedEntry,
                        metadata: controller.selectedMetadata,
                        analysis: controller.selectedAnalysis,
                        isLoading: controller.isLoadingMetadata,
                        isVisible: true,
                        errorText: controller.metadataError,
                        statusText: controller.statusText,
                        zoom: controller.zoom,
                        onDecisionChanged: (String value) async {
                          await controller.updateSelectedDecision(value);
                        },
                        onCategoryChanged: (String value) async {
                          await controller.updateSelectedCategory(value);
                        },
                        onTagToggled: (String value) async {
                          await controller.toggleSelectedTag(value);
                        },
                        onTagsChanged: (List<String> values) async {
                          await controller.setSelectedTags(values);
                        },
                        availableTags: controller.availableTags,
                        onRenameTagGlobally:
                            (String oldTag, String newTag) async {
                              await controller.renameTagGlobally(
                                oldTag,
                                newTag,
                              );
                            },
                        onDeleteTagGlobally: (String tag) async {
                          await controller.deleteTagGlobally(tag);
                        },
                      ),
                    ),
            ),
          ],
        ),
      ),
    );
  }
}

class _TopBar extends StatelessWidget {
  const _TopBar({
    required this.selectedFolder,
    required this.hasActivePhoto,
    required this.isLoading,
    required this.isAnalyzing,
    required this.analysisProgress,
    required this.analysisTotal,
    required this.statusText,
    required this.viewerMode,
    required this.onBrowse,
    required this.onOpenSettings,
    required this.onModeChanged,
    required this.compact,
  });

  final String? selectedFolder;
  final bool hasActivePhoto;
  final bool isLoading;
  final bool isAnalyzing;
  final int analysisProgress;
  final int analysisTotal;
  final String statusText;
  final _ViewerMode viewerMode;
  final Future<void> Function() onBrowse;
  final VoidCallback onOpenSettings;
  final ValueChanged<_ViewerMode> onModeChanged;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final progressValue = analysisTotal > 0
        ? analysisProgress / analysisTotal
        : null;
    final hasFolder = selectedFolder != null && selectedFolder!.isNotEmpty;
    final basicMode = viewerMode == _ViewerMode.basic;
    final compactBasicHeader =
        basicMode && hasActivePhoto && !isAnalyzing && !isLoading;
    final showStatusRow = isAnalyzing || isLoading || !hasActivePhoto;

    return Container(
      padding: compactBasicHeader
          ? const EdgeInsets.fromLTRB(10, 6, 10, 4)
          : const EdgeInsets.fromLTRB(12, 6, 12, 5),
      decoration: BoxDecoration(
        color: const Color(0xD2191B20),
        borderRadius: BorderRadius.circular(22),
        border: Border.all(color: Colors.white.withValues(alpha: 0.06)),
      ),
      child: Column(
        children: <Widget>[
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              _brandIcon(compact: compact || !basicMode),
              const SizedBox(width: 10),
              Expanded(
                child: Align(
                  alignment: Alignment.topCenter,
                  child: _modeSelector(),
                ),
              ),
              Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: <Widget>[
                  Row(
                    mainAxisSize: MainAxisSize.min,
                    children: <Widget>[
                      Tooltip(
                        message: 'Browse klasor secimi',
                        child: basicMode
                            ? _topIconButton(
                                icon: Icons.folder_open_rounded,
                                onPressed: isLoading || isAnalyzing
                                    ? null
                                    : onBrowse,
                              )
                            : FilledButton.tonalIcon(
                                onPressed: isLoading || isAnalyzing
                                    ? null
                                    : onBrowse,
                                icon: const Icon(
                                  Icons.folder_open_rounded,
                                  size: 16,
                                ),
                                label: const Text('Browse'),
                                style: _compactButtonStyle(),
                              ),
                      ),
                      const SizedBox(width: 6),
                      Tooltip(
                        message: 'Ayarlar',
                        child: _topIconButton(
                          icon: Icons.menu_rounded,
                          onPressed: onOpenSettings,
                        ),
                      ),
                    ],
                  ),
                  if (hasFolder && !compactBasicHeader) ...<Widget>[
                    const SizedBox(height: 2),
                    ConstrainedBox(
                      constraints: BoxConstraints(
                        maxWidth: compact ? 150 : 200,
                      ),
                      child: Text(
                        selectedFolder!,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        textAlign: TextAlign.right,
                        style: theme.textTheme.labelSmall?.copyWith(
                          color: Colors.white54,
                          fontSize: 10,
                        ),
                      ),
                    ),
                  ],
                ],
              ),
            ],
          ),
          SizedBox(height: compactBasicHeader ? 1 : 3),
          Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: <Widget>[
              if (showStatusRow)
                Expanded(
                  child: Row(
                    children: <Widget>[
                      Expanded(
                        child: Text(
                          statusText,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: theme.textTheme.bodySmall?.copyWith(
                            color: Colors.white60,
                            fontSize: 11,
                          ),
                        ),
                      ),
                      if (isAnalyzing) ...<Widget>[
                        const SizedBox(width: 10),
                        SizedBox(
                          width: compact ? 100 : 150,
                          child: LinearProgressIndicator(value: progressValue),
                        ),
                        const SizedBox(width: 8),
                        Text(
                          '$analysisProgress/$analysisTotal',
                          style: theme.textTheme.labelSmall?.copyWith(
                            color: Colors.white70,
                          ),
                        ),
                      ],
                    ],
                  ),
                )
              else
                const Spacer(),
            ],
          ),
        ],
      ),
    );
  }

  Widget _brandIcon({required bool compact}) {
    final size = compact ? 44.0 : 54.0;
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        color: const Color(0xFF20242B),
        borderRadius: BorderRadius.circular(compact ? 14 : 18),
        border: Border.all(color: Colors.white.withValues(alpha: 0.06)),
      ),
      child: Padding(
        padding: EdgeInsets.all(compact ? 4 : 5),
        child: ClipRRect(
          borderRadius: BorderRadius.circular(compact ? 10 : 13),
          child: Image.asset(_brandAssetPath, fit: BoxFit.contain),
        ),
      ),
    );
  }

  Widget _topIconButton({
    required IconData icon,
    required VoidCallback? onPressed,
  }) {
    return IconButton(
      onPressed: onPressed,
      icon: Icon(icon, size: 18),
      visualDensity: VisualDensity.compact,
      style: IconButton.styleFrom(
        backgroundColor: const Color(0xFF20242B),
        foregroundColor: Colors.white,
        minimumSize: const Size(30, 30),
        padding: EdgeInsets.zero,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
      ),
    );
  }

  Widget _modeSelector() {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.04),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: Colors.white.withValues(alpha: 0.06)),
      ),
      child: Padding(
        padding: const EdgeInsets.all(3),
        child: SegmentedButton<_ViewerMode>(
          segments: _viewerModeSegments(),
          selected: <_ViewerMode>{viewerMode},
          showSelectedIcon: false,
          onSelectionChanged: (Set<_ViewerMode> values) {
            final mode = values.first;
            onModeChanged(mode);
          },
          style: SegmentedButton.styleFrom(
            visualDensity: VisualDensity.compact,
            padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 2),
            tapTargetSize: MaterialTapTargetSize.shrinkWrap,
          ),
        ),
      ),
    );
  }

  List<ButtonSegment<_ViewerMode>> _viewerModeSegments() {
    return <ButtonSegment<_ViewerMode>>[
      ButtonSegment<_ViewerMode>(
        value: _ViewerMode.basic,
        label: Text(
          _ViewerMode.basic.label,
          style: const TextStyle(fontSize: 11),
        ),
      ),
      ButtonSegment<_ViewerMode>(
        value: _ViewerMode.advanced,
        label: Text(
          _ViewerMode.advanced.label,
          style: const TextStyle(fontSize: 11),
        ),
      ),
    ];
  }
}

class _FileList extends StatelessWidget {
  const _FileList({
    required this.entries,
    required this.selectedPath,
    required this.analysisLookup,
    required this.activeFilter,
    required this.activeSort,
    required this.sortAscending,
    required this.activeTagFilter,
    required this.compact,
    required this.onFilterChanged,
    required this.onSortChanged,
    required this.onSortDirectionChanged,
    required this.onTagFilterChanged,
    required this.onSelected,
    required this.onToggleCollapsed,
  });

  final List<PhotoEntry> entries;
  final String? selectedPath;
  final AnalysisSummary? Function(PhotoEntry entry) analysisLookup;
  final _DecisionFilter activeFilter;
  final _SortMode activeSort;
  final bool sortAscending;
  final String activeTagFilter;
  final bool compact;
  final ValueChanged<_DecisionFilter> onFilterChanged;
  final ValueChanged<_SortMode> onSortChanged;
  final VoidCallback onSortDirectionChanged;
  final ValueChanged<String> onTagFilterChanged;
  final ValueChanged<int> onSelected;
  final VoidCallback onToggleCollapsed;

  @override
  Widget build(BuildContext context) {
    final availableTags = <String>{
      for (final PhotoEntry entry in entries) ...?analysisLookup(entry)?.tags,
    }.toList()..sort();
    final tagOptions = <String>['All', ...availableTags];

    return Container(
      decoration: BoxDecoration(
        color: const Color(0xCC16181D),
        borderRadius: BorderRadius.circular(24),
        border: Border.all(color: Colors.white.withValues(alpha: 0.06)),
      ),
      child: Column(
        children: <Widget>[
          Padding(
            padding: EdgeInsets.fromLTRB(
              14,
              compact ? 10 : 14,
              14,
              compact ? 8 : 10,
            ),
            child: Column(
              children: <Widget>[
                Row(
                  children: <Widget>[
                    Text(
                      'Files',
                      style: Theme.of(context).textTheme.titleSmall?.copyWith(
                        fontWeight: FontWeight.w700,
                        letterSpacing: 0.2,
                      ),
                    ),
                    const Spacer(),
                    IconButton(
                      tooltip: 'Dosya panelini kapat',
                      onPressed: onToggleCollapsed,
                      visualDensity: VisualDensity.compact,
                      padding: EdgeInsets.zero,
                      constraints: const BoxConstraints.tightFor(
                        width: 24,
                        height: 24,
                      ),
                      icon: const Icon(Icons.chevron_left_rounded, size: 16),
                    ),
                    Tooltip(
                      message: sortAscending
                          ? 'Artan siralama'
                          : 'Azalan siralama',
                      child: IconButton(
                        onPressed: onSortDirectionChanged,
                        visualDensity: VisualDensity.compact,
                        padding: EdgeInsets.zero,
                        constraints: const BoxConstraints.tightFor(
                          width: 28,
                          height: 28,
                        ),
                        icon: Icon(
                          sortAscending
                              ? Icons.arrow_upward_rounded
                              : Icons.arrow_downward_rounded,
                          size: 16,
                        ),
                      ),
                    ),
                    PopupMenuButton<_SortMode>(
                      tooltip: 'Sort',
                      initialValue: activeSort,
                      onSelected: onSortChanged,
                      position: PopupMenuPosition.under,
                      color: const Color(0xFF1C2026),
                      itemBuilder: (BuildContext context) {
                        return _SortMode.values
                            .map(
                              (_SortMode value) => PopupMenuItem<_SortMode>(
                                value: value,
                                child: Text(value.label),
                              ),
                            )
                            .toList();
                      },
                      child: Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 10,
                          vertical: 6,
                        ),
                        decoration: BoxDecoration(
                          color: Colors.white.withValues(alpha: 0.05),
                          borderRadius: BorderRadius.circular(999),
                          border: Border.all(
                            color: Colors.white.withValues(alpha: 0.06),
                          ),
                        ),
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: <Widget>[
                            Text(
                              activeSort.label,
                              style: Theme.of(context).textTheme.labelSmall
                                  ?.copyWith(
                                    color: Colors.white70,
                                    fontWeight: FontWeight.w600,
                                  ),
                            ),
                            const SizedBox(width: 4),
                            const Icon(Icons.swap_vert_rounded, size: 14),
                          ],
                        ),
                      ),
                    ),
                  ],
                ),
                SizedBox(height: compact ? 8 : 10),
                Align(
                  alignment: Alignment.centerLeft,
                  child: Wrap(
                    spacing: 6,
                    runSpacing: 6,
                    children: _DecisionFilter.values.map((
                      _DecisionFilter filter,
                    ) {
                      return ChoiceChip(
                        selected: activeFilter == filter,
                        label: Text(filter.label),
                        labelStyle: Theme.of(context).textTheme.labelSmall,
                        visualDensity: VisualDensity.compact,
                        materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                        side: BorderSide(
                          color: Colors.white.withValues(alpha: 0.05),
                        ),
                        onSelected: (_) => onFilterChanged(filter),
                      );
                    }).toList(),
                  ),
                ),
                if (!compact && tagOptions.length > 1) ...<Widget>[
                  const SizedBox(height: 10),
                  Align(
                    alignment: Alignment.centerLeft,
                    child: Text(
                      'Tags',
                      style: Theme.of(
                        context,
                      ).textTheme.bodySmall?.copyWith(color: Colors.white54),
                    ),
                  ),
                  const SizedBox(height: 8),
                  SingleChildScrollView(
                    scrollDirection: Axis.horizontal,
                    child: Row(
                      children: tagOptions.map((String tag) {
                        return Padding(
                          padding: const EdgeInsets.only(right: 6),
                          child: FilterChip(
                            selected: activeTagFilter == tag,
                            label: Text(tag),
                            labelStyle: Theme.of(context).textTheme.labelSmall,
                            visualDensity: VisualDensity.compact,
                            materialTapTargetSize:
                                MaterialTapTargetSize.shrinkWrap,
                            side: BorderSide(
                              color: Colors.white.withValues(alpha: 0.05),
                            ),
                            onSelected: (_) => onTagFilterChanged(tag),
                          ),
                        );
                      }).toList(),
                    ),
                  ),
                ],
              ],
            ),
          ),
          const Divider(height: 1),
          Expanded(
            child: ListView.builder(
              itemCount: entries.length,
              itemBuilder: (BuildContext context, int index) {
                final entry = entries[index];
                final selected = entry.file.path == selectedPath;
                final analysis = analysisLookup(entry);
                final decisionColor = _decisionColor(analysis?.decision);
                final decisionLabel = switch (analysis?.decision) {
                  'selected' => 'Sel',
                  'candidate' => 'Cand',
                  'rejected' => 'Rej',
                  'best_of_burst' => 'Best',
                  _ => null,
                };
                return InkWell(
                  onTap: () => onSelected(entry.index),
                  child: Container(
                    margin: const EdgeInsets.symmetric(
                      horizontal: 10,
                      vertical: 4,
                    ),
                    padding: const EdgeInsets.symmetric(
                      horizontal: 12,
                      vertical: 10,
                    ),
                    decoration: BoxDecoration(
                      color: selected
                          ? const Color(0xFF223548)
                          : Colors.transparent,
                      borderRadius: BorderRadius.circular(16),
                    ),
                    child: Row(
                      children: <Widget>[
                        Container(
                          width: 8,
                          height: 38,
                          decoration: BoxDecoration(
                            color: decisionColor,
                            borderRadius: BorderRadius.circular(99),
                          ),
                        ),
                        const SizedBox(width: 10),
                        Text(
                          '${index + 1}'.padLeft(2, '0'),
                          style: TextStyle(
                            color: selected ? Colors.white : Colors.white54,
                            fontFeatures: const <FontFeature>[
                              FontFeature.tabularFigures(),
                            ],
                          ),
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: <Widget>[
                              Text(
                                entry.name,
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                              ),
                              const SizedBox(height: 3),
                              Wrap(
                                spacing: 6,
                                runSpacing: 2,
                                crossAxisAlignment: WrapCrossAlignment.center,
                                children: <Widget>[
                                  Text(
                                    entry.extension
                                        .replaceFirst('.', '')
                                        .toUpperCase(),
                                    style: Theme.of(context).textTheme.bodySmall
                                        ?.copyWith(color: Colors.white54),
                                  ),
                                  if (decisionLabel != null)
                                    Text(
                                      decisionLabel,
                                      style: Theme.of(context)
                                          .textTheme
                                          .bodySmall
                                          ?.copyWith(
                                            color: decisionColor,
                                            fontWeight: FontWeight.w600,
                                          ),
                                    ),
                                ],
                              ),
                            ],
                          ),
                        ),
                        if (!compact && analysis?.overallQuality != null)
                          Text(
                            analysis!.overallQuality!.toStringAsFixed(2),
                            style: Theme.of(context).textTheme.labelMedium
                                ?.copyWith(
                                  color: Colors.white70,
                                  fontFeatures: const <FontFeature>[
                                    FontFeature.tabularFigures(),
                                  ],
                                ),
                          ),
                      ],
                    ),
                  ),
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}

class _ThumbnailStrip extends StatelessWidget {
  const _ThumbnailStrip({
    required this.entries,
    required this.selectedIndex,
    required this.thumbnailResolver,
    required this.onSelected,
    required this.onVisible,
    required this.scrollController,
    required this.thumbnailSize,
    required this.compact,
  });

  final List<PhotoEntry> entries;
  final int selectedIndex;
  final String? Function(PhotoEntry entry) thumbnailResolver;
  final ValueChanged<int> onSelected;
  final ValueChanged<PhotoEntry> onVisible;
  final ScrollController scrollController;
  final int thumbnailSize;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    return Container(
      height: thumbnailSize.toDouble() + 38,
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
      decoration: BoxDecoration(
        color: const Color(0xCC16181D),
        borderRadius: BorderRadius.circular(24),
        border: Border.all(color: Colors.white.withValues(alpha: 0.06)),
      ),
      child: ListView.separated(
        controller: scrollController,
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.symmetric(horizontal: 2, vertical: 2),
        itemCount: entries.length,
        separatorBuilder: (_, _) => const SizedBox(width: 8),
        itemBuilder: (BuildContext context, int index) {
          final entry = entries[index];
          final selected = index == selectedIndex;
          onVisible(entry);
          final thumbPath = thumbnailResolver(entry);
          return GestureDetector(
            onTap: () => onSelected(index),
            child: AnimatedContainer(
              duration: const Duration(milliseconds: 180),
              width: thumbnailSize.toDouble(),
              padding: const EdgeInsets.all(5),
              decoration: BoxDecoration(
                color: selected
                    ? const Color(0xFF223548)
                    : const Color(0xFF121419),
                borderRadius: BorderRadius.circular(18),
                border: Border.all(
                  color: selected
                      ? const Color(0xFFFFA574)
                      : Colors.white.withValues(alpha: 0.05),
                ),
              ),
              child: Column(
                children: <Widget>[
                  Expanded(
                    child: ClipRRect(
                      borderRadius: BorderRadius.circular(12),
                      child: thumbPath != null
                          ? Image.file(
                              File(thumbPath),
                              fit: BoxFit.cover,
                              cacheWidth: thumbnailSize * 2,
                              errorBuilder: (_, _, _) =>
                                  const _RawPlaceholder(),
                            )
                          : const _RawPlaceholder(),
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    '${index + 1}',
                    style: Theme.of(context).textTheme.labelSmall?.copyWith(
                      color: selected ? Colors.white : Colors.white60,
                    ),
                  ),
                ],
              ),
            ),
          );
        },
      ),
    );
  }
}

class _PreviewSurface extends StatelessWidget {
  const _PreviewSurface({
    required this.entry,
    required this.selectedFolder,
    required this.previewPath,
    required this.previewSnapshot,
    required this.metadata,
    required this.isLoadingPreview,
    required this.previewError,
    required this.exposureEv,
    required this.exposureAdjustMode,
    required this.rotationQuarterTurns,
    required this.analysis,
    required this.showCameraAf,
    required this.showSharpGuess,
    required this.isAnalyzing,
    required this.zoom,
    required this.transformationController,
    required this.onViewportSizeChanged,
    required this.onResetZoom,
    required this.onRotateLeft,
    required this.onRotateRight,
    required this.onToggleExposureMode,
    required this.onAdjustZoom,
    required this.onAdjustExposure,
    required this.onResetExposure,
    required this.onAnalyze,
    required this.onCancelAnalyze,
    required this.onPrevious,
    required this.onNext,
    required this.onOpenDetails,
    required this.onToggleSharpGuess,
    required this.onToggleCameraAf,
    required this.onShare,
    required this.onToggleQuickTag,
    required this.showBasicHud,
    required this.hudSelectedFolder,
    required this.hudOnBrowse,
    required this.hudOnOpenSettings,
    required this.hudOnModeChanged,
    required this.hudViewerMode,
  });

  final PhotoEntry? entry;
  final String? selectedFolder;
  final String? previewPath;
  final PreviewSnapshot? previewSnapshot;
  final FileMetadataSnapshot? metadata;
  final bool isLoadingPreview;
  final String? previewError;
  final double exposureEv;
  final bool exposureAdjustMode;
  final int rotationQuarterTurns;
  final AnalysisSummary? analysis;
  final bool showCameraAf;
  final bool showSharpGuess;
  final bool isAnalyzing;
  final double zoom;
  final TransformationController transformationController;
  final ValueChanged<Size> onViewportSizeChanged;
  final VoidCallback onResetZoom;
  final VoidCallback onRotateLeft;
  final VoidCallback onRotateRight;
  final VoidCallback onToggleExposureMode;
  final ValueChanged<double> onAdjustZoom;
  final ValueChanged<double> onAdjustExposure;
  final VoidCallback onResetExposure;
  final Future<void> Function() onAnalyze;
  final Future<void> Function() onCancelAnalyze;
  final VoidCallback onPrevious;
  final VoidCallback onNext;
  final VoidCallback onOpenDetails;
  final VoidCallback onToggleSharpGuess;
  final VoidCallback onToggleCameraAf;
  final Future<void> Function() onShare;
  final Future<void> Function(String value) onToggleQuickTag;
  final bool showBasicHud;
  final String? hudSelectedFolder;
  final Future<void> Function() hudOnBrowse;
  final VoidCallback hudOnOpenSettings;
  final ValueChanged<_ViewerMode> hudOnModeChanged;
  final _ViewerMode hudViewerMode;

  @override
  Widget build(BuildContext context) {
    final topOverlayOffset = showBasicHud ? 80.0 : 20.0;
    final mediaWidth = MediaQuery.sizeOf(context).width;
    final mediaHeight = MediaQuery.sizeOf(context).height;
    final sideArrowOffset = mediaHeight * 0.5;
    return Container(
      decoration: BoxDecoration(
        color: const Color(0xCC16181D),
        borderRadius: BorderRadius.circular(28),
        border: Border.all(color: Colors.white.withValues(alpha: 0.06)),
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(28),
        child: entry == null
            ? const _ViewerEmptyState()
            : Stack(
                children: <Widget>[
                  Positioned.fill(
                    child: LayoutBuilder(
                      builder:
                          (BuildContext context, BoxConstraints constraints) {
                            WidgetsBinding.instance.addPostFrameCallback((_) {
                              onViewportSizeChanged(constraints.biggest);
                            });
                            return Listener(
                              onPointerSignal: (PointerSignalEvent event) {
                                if (event is PointerScrollEvent) {
                                  final delta = (-event.scrollDelta.dy / 480.0)
                                      .clamp(-0.2, 0.2);
                                  if (delta != 0) {
                                    onAdjustZoom(delta);
                                  }
                                }
                              },
                              child: Stack(
                                children: <Widget>[
                                  Positioned.fill(
                                    child: InteractiveViewer(
                                      transformationController:
                                          transformationController,
                                      minScale: 0.4,
                                      maxScale: 6,
                                      trackpadScrollCausesScale: true,
                                      child: ColoredBox(
                                        color: const Color(0xFF0D0F12),
                                        child: Center(
                                          child: _PreviewWithOverlay(
                                            entry: entry,
                                            previewPath: previewPath,
                                            previewSnapshot: previewSnapshot,
                                            metadata: metadata,
                                            previewError: previewError,
                                            exposureEv: exposureEv,
                                            rotationQuarterTurns:
                                                rotationQuarterTurns,
                                            analysis: analysis,
                                            showCameraAf: showCameraAf,
                                            showSharpGuess: showSharpGuess,
                                            zoom: zoom,
                                            exposureAdjustMode:
                                                exposureAdjustMode,
                                            showBasicHud: showBasicHud,
                                          ),
                                        ),
                                      ),
                                    ),
                                  ),
                                ],
                              ),
                            );
                          },
                    ),
                  ),
                  Positioned(
                    left: 20,
                    top: sideArrowOffset.clamp(
                      topOverlayOffset + 32,
                      mediaHeight - 160,
                    ),
                    child: _PreviewArrowButton(
                      icon: Icons.chevron_left_rounded,
                      onPressed: onPrevious,
                      tooltip: 'Onceki fotograf (Sol ok veya mouse back)',
                    ),
                  ),
                  Positioned(
                    right: 20,
                    top: sideArrowOffset.clamp(
                      topOverlayOffset + 32,
                      mediaHeight - 160,
                    ),
                    child: _PreviewArrowButton(
                      icon: Icons.chevron_right_rounded,
                      onPressed: onNext,
                      tooltip: 'Sonraki fotograf (Sag ok veya mouse forward)',
                    ),
                  ),
                  if (!showBasicHud)
                    Positioned(
                      left: 16,
                      bottom: 16,
                      child: Tooltip(
                        message: isAnalyzing
                            ? 'Analizi durdur'
                            : 'Secili klasoru analiz et ve kalite puanlarini guncelle',
                        child: FilledButton.tonal(
                          onPressed: selectedFolder == null
                              ? null
                              : (isAnalyzing ? onCancelAnalyze : onAnalyze),
                          style: FilledButton.styleFrom(
                            minimumSize: const Size(38, 38),
                            padding: const EdgeInsets.symmetric(
                              horizontal: 12,
                              vertical: 10,
                            ),
                            shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(14),
                            ),
                          ),
                          child: Icon(
                            isAnalyzing
                                ? Icons.stop_circle_outlined
                                : Icons.auto_awesome_rounded,
                            size: 16,
                          ),
                        ),
                      ),
                    ),
                  Positioned(
                    right: 16,
                    bottom: 16,
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.end,
                      children: <Widget>[
                        Tooltip(
                          message: showCameraAf
                              ? 'Camera AF kutularini gizle'
                              : 'Camera AF kutularini goster',
                          child: _PreviewToggleBadge(
                            icon: Icons.crop_free_rounded,
                            active: showCameraAf,
                            label: 'AF',
                            onPressed: onToggleCameraAf,
                            onLongPress: () {},
                          ),
                        ),
                        const SizedBox(height: 4),
                        Tooltip(
                          message: showSharpGuess
                              ? 'Netlik noktasini gizle'
                              : 'Netlik noktasini goster',
                          child: _PreviewToggleBadge(
                            icon: Icons.center_focus_weak_rounded,
                            active: showSharpGuess,
                            label: 'Sharp',
                            onPressed: onToggleSharpGuess,
                            onLongPress: () {},
                          ),
                        ),
                        const SizedBox(height: 4),
                        Tooltip(
                          message: 'EV otomatik uygula',
                          child: Row(
                            mainAxisSize: MainAxisSize.min,
                            children: <Widget>[
                              Tooltip(
                                message: 'Pozlamayi azalt',
                                child: _PreviewStepButton(
                                  icon: Icons.remove_rounded,
                                  onPressed: () => onAdjustExposure(-0.2),
                                ),
                              ),
                              const SizedBox(width: 4),
                              _PreviewToggleBadge(
                                icon: Icons.exposure_rounded,
                                active: exposureAdjustMode,
                                label: _formatEv(exposureEv),
                                onPressed: onToggleExposureMode,
                                onLongPress: onResetExposure,
                              ),
                              const SizedBox(width: 4),
                              Tooltip(
                                message: 'Pozlamayi artir',
                                child: _PreviewStepButton(
                                  icon: Icons.add_rounded,
                                  onPressed: () => onAdjustExposure(0.2),
                                ),
                              ),
                            ],
                          ),
                        ),
                        const SizedBox(height: 4),
                        Row(
                          mainAxisSize: MainAxisSize.min,
                          children: <Widget>[
                            Tooltip(
                              message: 'Sola cevir',
                              child: _PreviewIconButton(
                                icon: Icons.rotate_90_degrees_ccw_rounded,
                                onPressed: onRotateLeft,
                              ),
                            ),
                            const SizedBox(width: 4),
                            Tooltip(
                              message: 'Saga cevir',
                              child: _PreviewIconButton(
                                icon: Icons.rotate_90_degrees_cw_rounded,
                                onPressed: onRotateRight,
                              ),
                            ),
                            const SizedBox(width: 4),
                            Tooltip(
                              message:
                                  'Paylas: dosya adini ve yolunu panoya kopyala',
                              child: _PreviewIconButton(
                                icon: Icons.share_outlined,
                                onPressed: () {
                                  onShare();
                                },
                              ),
                            ),
                            const SizedBox(width: 4),
                            Tooltip(
                              message: 'Details',
                              child: _PreviewIconButton(
                                icon: Icons.info_outline_rounded,
                                onPressed: onOpenDetails,
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 4),
                        Tooltip(
                          message: 'Fotografi ekrana tekrar oturt',
                          child: FilledButton.tonalIcon(
                            onPressed: onResetZoom,
                            icon: const Icon(
                              Icons.center_focus_strong_rounded,
                              size: 16,
                            ),
                            label: const Text('Fit'),
                            style: FilledButton.styleFrom(
                              visualDensity: VisualDensity.compact,
                              padding: const EdgeInsets.symmetric(
                                horizontal: 10,
                                vertical: 10,
                              ),
                              minimumSize: const Size(0, 34),
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                  if (showBasicHud)
                    Positioned(
                      left: 20,
                      right: 20,
                      top: 16,
                      child: _BasicPreviewHud(
                        viewerMode: hudViewerMode,
                        selectedFolder: hudSelectedFolder,
                        onBrowse: hudOnBrowse,
                        onOpenSettings: hudOnOpenSettings,
                        onModeChanged: hudOnModeChanged,
                      ),
                    ),
                  if (analysis != null)
                    Positioned(
                      left: 20,
                      bottom: 76,
                      child: ConstrainedBox(
                        constraints: BoxConstraints(
                          // Leave a safe lane for the right-side preview controls.
                          maxWidth: (mediaWidth - 220).clamp(120.0, 900.0),
                        ),
                        child: _QuickTagBar(
                          selectedTags: analysis!.tags,
                          onRemove: onToggleQuickTag,
                        ),
                      ),
                    ),
                ],
              ),
      ),
    );
  }
}

class _PreviewWithOverlay extends StatelessWidget {
  const _PreviewWithOverlay({
    required this.entry,
    required this.previewPath,
    required this.previewSnapshot,
    required this.metadata,
    required this.previewError,
    required this.exposureEv,
    required this.rotationQuarterTurns,
    required this.analysis,
    required this.showCameraAf,
    required this.showSharpGuess,
    required this.zoom,
    required this.exposureAdjustMode,
    required this.showBasicHud,
  });

  final PhotoEntry? entry;
  final String? previewPath;
  final PreviewSnapshot? previewSnapshot;
  final FileMetadataSnapshot? metadata;
  final String? previewError;
  final double exposureEv;
  final int rotationQuarterTurns;
  final AnalysisSummary? analysis;
  final bool showCameraAf;
  final bool showSharpGuess;
  final double zoom;
  final bool exposureAdjustMode;
  final bool showBasicHud;

  @override
  Widget build(BuildContext context) {
    if (previewPath == null) {
      return _PreviewUnavailable(message: previewError);
    }
    return Stack(
      alignment: Alignment.center,
      children: <Widget>[
        RotatedBox(
          quarterTurns: rotationQuarterTurns,
          child: Stack(
            alignment: Alignment.center,
            children: <Widget>[
              ColorFiltered(
                colorFilter: ColorFilter.matrix(_exposureMatrix(exposureEv)),
                child: Image.file(
                  File(previewPath!),
                  fit: BoxFit.contain,
                  errorBuilder: (_, _, _) =>
                      _PreviewUnavailable(message: previewError),
                ),
              ),
              Positioned.fill(
                child: IgnorePointer(
                  child: CustomPaint(
                    painter: _PreviewOverlayPainter(
                      snapshot: previewSnapshot,
                      showCameraAf: showCameraAf,
                      showSharpGuess: showSharpGuess,
                      zoom: zoom,
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
        if (analysis?.overallQuality != null)
          Positioned(
            top: showBasicHud ? 74 : 16,
            right: 18,
            child: _AnalysisScoreBadge(
              score: (analysis!.overallQuality!.clamp(0.0, 1.0) * 100).round(),
            ),
          ),
        if (entry != null)
          Positioned(
            left: 16,
            right: 16,
            bottom: 16,
            child: IgnorePointer(
              child: Align(
                alignment: Alignment.bottomCenter,
                child: _PreviewFileNamePlate(
                  name: entry!.name,
                  subtitle: metadata?.cameraModel ?? metadata?.lensModel,
                ),
              ),
            ),
          ),
      ],
    );
  }
}

class _MetadataPanel extends StatelessWidget {
  const _MetadataPanel({
    required this.entry,
    required this.metadata,
    required this.analysis,
    required this.isLoading,
    required this.isVisible,
    required this.errorText,
    required this.statusText,
    required this.zoom,
    required this.onDecisionChanged,
    required this.onCategoryChanged,
    required this.onTagToggled,
    required this.onTagsChanged,
    required this.availableTags,
    required this.onRenameTagGlobally,
    required this.onDeleteTagGlobally,
  });

  final PhotoEntry? entry;
  final FileMetadataSnapshot? metadata;
  final AnalysisSummary? analysis;
  final bool isLoading;
  final bool isVisible;
  final String? errorText;
  final String statusText;
  final double zoom;
  final Future<void> Function(String value) onDecisionChanged;
  final Future<void> Function(String value) onCategoryChanged;
  final Future<void> Function(String value) onTagToggled;
  final Future<void> Function(List<String> values) onTagsChanged;
  final List<String> availableTags;
  final Future<void> Function(String oldTag, String newTag) onRenameTagGlobally;
  final Future<void> Function(String tag) onDeleteTagGlobally;

  @override
  Widget build(BuildContext context) {
    final file = entry?.file;
    final stat = file != null && file.existsSync() ? file.statSync() : null;
    final effectiveDecision = analysis?.decision ?? 'candidate';
    final effectiveCategory =
        analysis?.category ?? metadata?.categoryHint ?? 'general';

    if (!isVisible) {
      return Container(
        decoration: BoxDecoration(
          color: const Color(0xCC16181D),
          borderRadius: BorderRadius.circular(24),
          border: Border.all(color: Colors.white.withValues(alpha: 0.06)),
        ),
        padding: const EdgeInsets.all(18),
        child: const Center(
          child: Text('Details gizli. Ustten tekrar acabilirsin.'),
        ),
      );
    }

    return Container(
      decoration: BoxDecoration(
        color: const Color(0xCC16181D),
        borderRadius: BorderRadius.circular(24),
        border: Border.all(color: Colors.white.withValues(alpha: 0.06)),
      ),
      padding: const EdgeInsets.all(18),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text(
            'Inspector',
            style: Theme.of(
              context,
            ).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700),
          ),
          const SizedBox(height: 6),
          Text(
            statusText,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: Theme.of(
              context,
            ).textTheme.bodySmall?.copyWith(color: Colors.white70),
          ),
          const SizedBox(height: 18),
          if (entry == null)
            const Expanded(
              child: Center(
                child: Text(
                  'Bir dosya secildiginde bilgiler burada gorunecek.',
                ),
              ),
            )
          else
            Expanded(
              child: ListView(
                children: <Widget>[
                  _InspectorTile(label: 'Dosya', value: p.basename(file!.path)),
                  _InspectorTile(
                    label: 'Tur',
                    value: entry!.extension.replaceFirst('.', '').toUpperCase(),
                  ),
                  _InspectorTile(
                    label: 'Boyut',
                    value: _formatBytes(stat?.size ?? 0),
                  ),
                  _InspectorTile(
                    label: 'Zoom',
                    value: '${(zoom * 100).round()}%',
                  ),
                  const SizedBox(height: 12),
                  _OverrideEditor(
                    decision: effectiveDecision,
                    category: effectiveCategory,
                    tags: analysis?.tags ?? const <String>[],
                    isDecisionOverridden:
                        analysis?.isDecisionOverridden ?? false,
                    isCategoryOverridden:
                        analysis?.isCategoryOverridden ?? false,
                    onDecisionChanged: onDecisionChanged,
                    onCategoryChanged: onCategoryChanged,
                    onTagToggled: onTagToggled,
                    onTagsChanged: onTagsChanged,
                    availableTags: availableTags,
                    onRenameTagGlobally: onRenameTagGlobally,
                    onDeleteTagGlobally: onDeleteTagGlobally,
                  ),
                  if (analysis != null) ...<Widget>[
                    const SizedBox(height: 12),
                    _DecisionCard(analysis: analysis!),
                  ],
                  const SizedBox(height: 14),
                  if (isLoading)
                    const Padding(
                      padding: EdgeInsets.symmetric(vertical: 24),
                      child: Center(child: CircularProgressIndicator()),
                    )
                  else if (errorText != null)
                    Text(
                      errorText!,
                      style: const TextStyle(color: Colors.orangeAccent),
                    )
                  else if (metadata != null) ...<Widget>[
                    _InspectorTile(
                      label: 'Kamera',
                      value: _joinNonEmpty(<String?>[
                        metadata!.cameraMaker,
                        metadata!.cameraModel,
                      ]),
                    ),
                    _InspectorTile(
                      label: 'Lens',
                      value: _joinNonEmpty(<String?>[
                        metadata!.lensMaker,
                        metadata!.lensModel,
                      ]),
                    ),
                    _InspectorTile(
                      label: 'Cozunurluk',
                      value: metadata!.width != null && metadata!.height != null
                          ? '${metadata!.width} x ${metadata!.height}'
                          : '-',
                    ),
                    _InspectorTile(
                      label: 'Odak uzakligi',
                      value: metadata!.focalLengthMm != null
                          ? '${metadata!.focalLengthMm!.round()} mm'
                          : '-',
                    ),
                    _InspectorTile(
                      label: 'Diyafram',
                      value: metadata!.apertureF != null
                          ? 'f/${metadata!.apertureF!.toStringAsFixed(metadata!.apertureF! % 1 == 0 ? 0 : 1)}'
                          : '-',
                    ),
                    _InspectorTile(
                      label: 'Enstantane',
                      value: _formatExposure(metadata!.exposureTimeS),
                    ),
                    _InspectorTile(
                      label: 'ISO',
                      value: metadata!.iso?.toString() ?? '-',
                    ),
                    _InspectorTile(
                      label: 'AF noktasi',
                      value: metadata!.afPointLabel ?? '-',
                    ),
                    _InspectorTile(
                      label: 'AF modu',
                      value: metadata!.afAreaMode ?? '-',
                    ),
                    _InspectorTile(
                      label: 'Kategori ipucu',
                      value: metadata!.categoryHint,
                    ),
                    if (analysis != null) ...<Widget>[
                      const SizedBox(height: 14),
                      Text(
                        'Kalite',
                        style: Theme.of(context).textTheme.titleSmall?.copyWith(
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                      const SizedBox(height: 8),
                      _MetricTile(label: 'Netlik', value: analysis!.sharpness),
                      _MetricTile(label: 'Pozlama', value: analysis!.exposure),
                      _MetricTile(label: 'Kontrast', value: analysis!.contrast),
                      _MetricTile(label: 'Noise', value: analysis!.noise),
                      _MetricTile(
                        label: 'Motion blur',
                        value: analysis!.motionBlurProbability,
                      ),
                      _MetricTile(
                        label: 'Genel kalite',
                        value: analysis!.overallQuality,
                      ),
                      if (analysis!.reasons.isNotEmpty) ...<Widget>[
                        const SizedBox(height: 14),
                        Text(
                          'Nedenler',
                          style: Theme.of(context).textTheme.titleSmall
                              ?.copyWith(fontWeight: FontWeight.w700),
                        ),
                        const SizedBox(height: 8),
                        for (
                          int index = 0;
                          index < analysis!.reasons.length;
                          index += 1
                        )
                          Padding(
                            padding: const EdgeInsets.only(bottom: 6),
                            child: Row(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: <Widget>[
                                Container(
                                  width: 8,
                                  height: 8,
                                  margin: const EdgeInsets.only(top: 5),
                                  decoration: BoxDecoration(
                                    color: _severityColor(
                                      index < analysis!.reasonSeverities.length
                                          ? analysis!.reasonSeverities[index]
                                          : 'info',
                                    ),
                                    shape: BoxShape.circle,
                                  ),
                                ),
                                const SizedBox(width: 8),
                                Expanded(
                                  child: Text(
                                    analysis!.reasons[index],
                                    style: Theme.of(context).textTheme.bodySmall
                                        ?.copyWith(color: Colors.white70),
                                  ),
                                ),
                              ],
                            ),
                          ),
                      ],
                    ],
                    if (metadata!.notes.isNotEmpty) ...<Widget>[
                      const SizedBox(height: 14),
                      Text(
                        'Notlar',
                        style: Theme.of(context).textTheme.titleSmall?.copyWith(
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                      const SizedBox(height: 8),
                      for (final String note in metadata!.notes)
                        Padding(
                          padding: const EdgeInsets.only(bottom: 6),
                          child: Text(
                            '- $note',
                            style: Theme.of(context).textTheme.bodySmall
                                ?.copyWith(color: Colors.white70),
                          ),
                        ),
                    ],
                  ] else
                    const Text('Metadata henuz yuklenmedi.'),
                ],
              ),
            ),
        ],
      ),
    );
  }
}

class _DecisionCard extends StatelessWidget {
  const _DecisionCard({required this.analysis});

  final AnalysisSummary analysis;

  @override
  Widget build(BuildContext context) {
    final color = _decisionColor(analysis.decision);
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: color.withValues(alpha: 0.4)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              Text(
                analysis.decision.toUpperCase(),
                style: Theme.of(context).textTheme.titleSmall?.copyWith(
                  color: color,
                  fontWeight: FontWeight.w800,
                ),
              ),
              if (analysis.isDecisionOverridden) ...<Widget>[
                const SizedBox(width: 8),
                const _OverridePill(label: 'manual'),
              ],
              const Spacer(),
              if (analysis.overallQuality != null)
                Text(
                  analysis.overallQuality!.toStringAsFixed(2),
                  style: Theme.of(context).textTheme.titleSmall?.copyWith(
                    fontFeatures: const <FontFeature>[
                      FontFeature.tabularFigures(),
                    ],
                  ),
                ),
            ],
          ),
          const SizedBox(height: 6),
          Row(
            children: <Widget>[
              Text(
                'Kategori: ${analysis.category}',
                style: Theme.of(
                  context,
                ).textTheme.bodySmall?.copyWith(color: Colors.white70),
              ),
              if (analysis.isCategoryOverridden) ...<Widget>[
                const SizedBox(width: 8),
                const _OverridePill(label: 'override'),
              ],
            ],
          ),
          if (analysis.reasons.isNotEmpty) ...<Widget>[
            const SizedBox(height: 10),
            for (final String reason in analysis.reasons.take(4))
              Padding(
                padding: const EdgeInsets.only(bottom: 4),
                child: Text(
                  '• $reason',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ),
          ],
        ],
      ),
    );
  }
}

class _QuickTagBar extends StatelessWidget {
  const _QuickTagBar({required this.selectedTags, required this.onRemove});

  final List<String> selectedTags;
  final Future<void> Function(String value) onRemove;

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: Colors.black.withValues(alpha: 0.34),
          borderRadius: BorderRadius.circular(18),
          border: Border.all(color: Colors.white.withValues(alpha: 0.08)),
        ),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              Text(
                'Secili etiketler',
                style: Theme.of(context).textTheme.labelMedium?.copyWith(
                  color: Colors.white70,
                  fontWeight: FontWeight.w700,
                ),
              ),
              const SizedBox(width: 10),
              if (selectedTags.isEmpty)
                Text(
                  'Etiket yok',
                  style: Theme.of(
                    context,
                  ).textTheme.bodySmall?.copyWith(color: Colors.white54),
                )
              else
                for (final String value in selectedTags)
                  Padding(
                    padding: const EdgeInsets.only(right: 8),
                    child: InputChip(
                      label: Text(value),
                      onDeleted: () => onRemove(value),
                      visualDensity: VisualDensity.compact,
                      materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                    ),
                  ),
            ],
          ),
        ),
      ),
    );
  }
}

class _PreviewFileNamePlate extends StatelessWidget {
  const _PreviewFileNamePlate({required this.name, this.subtitle});

  final String name;
  final String? subtitle;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: Colors.black.withValues(alpha: 0.28),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: Colors.white.withValues(alpha: 0.08)),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Text(
              name,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: Theme.of(context).textTheme.titleSmall?.copyWith(
                color: Colors.white,
                fontWeight: FontWeight.w700,
              ),
            ),
            if (subtitle != null && subtitle!.isNotEmpty)
              Text(
                subtitle!,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: Theme.of(
                  context,
                ).textTheme.bodySmall?.copyWith(color: Colors.white70),
              ),
          ],
        ),
      ),
    );
  }
}

class _OverrideEditor extends StatefulWidget {
  const _OverrideEditor({
    required this.decision,
    required this.category,
    required this.tags,
    required this.isDecisionOverridden,
    required this.isCategoryOverridden,
    required this.onDecisionChanged,
    required this.onCategoryChanged,
    required this.onTagToggled,
    required this.onTagsChanged,
    required this.availableTags,
    required this.onRenameTagGlobally,
    required this.onDeleteTagGlobally,
  });

  final String decision;
  final String category;
  final List<String> tags;
  final bool isDecisionOverridden;
  final bool isCategoryOverridden;
  final Future<void> Function(String value) onDecisionChanged;
  final Future<void> Function(String value) onCategoryChanged;
  final Future<void> Function(String value) onTagToggled;
  final Future<void> Function(List<String> values) onTagsChanged;
  final List<String> availableTags;
  final Future<void> Function(String oldTag, String newTag) onRenameTagGlobally;
  final Future<void> Function(String tag) onDeleteTagGlobally;

  @override
  State<_OverrideEditor> createState() => _OverrideEditorState();
}

class _OverrideEditorState extends State<_OverrideEditor> {
  late final TextEditingController _tagController;
  late final TextEditingController _renameController;
  String? _selectedCatalogTag;

  @override
  void initState() {
    super.initState();
    _tagController = TextEditingController();
    _renameController = TextEditingController();
  }

  @override
  void dispose() {
    _tagController.dispose();
    _renameController.dispose();
    super.dispose();
  }

  Future<void> _addCustomTag() async {
    final newTag = _tagController.text.trim();
    if (newTag.isEmpty) {
      return;
    }
    final tags = <String>{...widget.tags, newTag}.toList()..sort();
    _tagController.clear();
    await widget.onTagsChanged(tags);
  }

  Future<void> _removeTag(String tag) async {
    final tags = widget.tags.where((value) => value != tag).toList()..sort();
    await widget.onTagsChanged(tags);
  }

  Future<void> _renameSelectedCatalogTag() async {
    final selected = _selectedCatalogTag;
    final replacement = _renameController.text.trim();
    if (selected == null || replacement.isEmpty) {
      return;
    }
    await widget.onRenameTagGlobally(selected, replacement);
    setState(() {
      _selectedCatalogTag = replacement;
    });
    _renameController.clear();
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Row(
          children: <Widget>[
            Text(
              'Karar ve kategori',
              style: Theme.of(
                context,
              ).textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w700),
            ),
            const SizedBox(width: 8),
            if (widget.isDecisionOverridden || widget.isCategoryOverridden)
              Text(
                'SQLite kayitli',
                style: Theme.of(context).textTheme.labelSmall?.copyWith(
                  color: const Color(0xFFFFA574),
                ),
              ),
          ],
        ),
        const SizedBox(height: 10),
        SegmentedButton<String>(
          segments: const <ButtonSegment<String>>[
            ButtonSegment<String>(value: 'selected', label: Text('Selected')),
            ButtonSegment<String>(value: 'candidate', label: Text('Candidate')),
            ButtonSegment<String>(value: 'rejected', label: Text('Rejected')),
            ButtonSegment<String>(value: 'best_of_burst', label: Text('Best')),
          ],
          selected: <String>{widget.decision},
          multiSelectionEnabled: false,
          showSelectedIcon: false,
          onSelectionChanged: (Set<String> values) {
            final value = values.isEmpty ? null : values.first;
            if (value != null) {
              widget.onDecisionChanged(value);
            }
          },
        ),
        const SizedBox(height: 12),
        DropdownButtonFormField<String>(
          initialValue: _categoryOptions.contains(widget.category)
              ? widget.category
              : 'general',
          decoration: const InputDecoration(
            labelText: 'Kategori',
            border: OutlineInputBorder(),
            isDense: true,
          ),
          items: _categoryOptions
              .map(
                (String value) =>
                    DropdownMenuItem<String>(value: value, child: Text(value)),
              )
              .toList(),
          onChanged: (String? value) {
            if (value != null) {
              widget.onCategoryChanged(value);
            }
          },
        ),
        const SizedBox(height: 12),
        Align(
          alignment: Alignment.centerLeft,
          child: Text(
            'Etiketler',
            style: Theme.of(
              context,
            ).textTheme.labelLarge?.copyWith(fontWeight: FontWeight.w700),
          ),
        ),
        const SizedBox(height: 8),
        Row(
          children: <Widget>[
            Expanded(
              child: TextField(
                controller: _tagController,
                decoration: const InputDecoration(
                  labelText: 'Yeni etiket',
                  hintText: 'ornek: portfolio',
                  border: OutlineInputBorder(),
                  isDense: true,
                ),
                onSubmitted: (_) {
                  _addCustomTag();
                },
              ),
            ),
            const SizedBox(width: 8),
            FilledButton.tonalIcon(
              onPressed: _addCustomTag,
              icon: const Icon(Icons.add_rounded),
              label: const Text('Ekle'),
            ),
          ],
        ),
        const SizedBox(height: 10),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: widget.availableTags.map((String value) {
            final selected = widget.tags.contains(value);
            return FilterChip(
              selected: selected,
              label: Text(value),
              onSelected: (_) => widget.onTagToggled(value),
            );
          }).toList(),
        ),
        if (widget.tags.isNotEmpty) ...<Widget>[
          const SizedBox(height: 8),
          Wrap(
            spacing: 6,
            runSpacing: 6,
            children: widget.tags
                .map(
                  (String value) => InputChip(
                    label: Text(value),
                    onDeleted: () {
                      _removeTag(value);
                    },
                  ),
                )
                .toList(),
          ),
        ],
        const SizedBox(height: 14),
        Align(
          alignment: Alignment.centerLeft,
          child: Text(
            'Tum etiketleri yonet',
            style: Theme.of(
              context,
            ).textTheme.labelLarge?.copyWith(fontWeight: FontWeight.w700),
          ),
        ),
        const SizedBox(height: 8),
        DropdownButtonFormField<String>(
          initialValue: widget.availableTags.contains(_selectedCatalogTag)
              ? _selectedCatalogTag
              : null,
          decoration: const InputDecoration(
            labelText: 'Etiket sec',
            border: OutlineInputBorder(),
            isDense: true,
          ),
          items: widget.availableTags
              .map(
                (String value) =>
                    DropdownMenuItem<String>(value: value, child: Text(value)),
              )
              .toList(),
          onChanged: (String? value) {
            setState(() {
              _selectedCatalogTag = value;
            });
          },
        ),
        const SizedBox(height: 8),
        Row(
          children: <Widget>[
            Expanded(
              child: TextField(
                controller: _renameController,
                decoration: const InputDecoration(
                  labelText: 'Yeni ad',
                  border: OutlineInputBorder(),
                  isDense: true,
                ),
                onSubmitted: (_) {
                  _renameSelectedCatalogTag();
                },
              ),
            ),
            const SizedBox(width: 8),
            FilledButton.tonal(
              onPressed: _renameSelectedCatalogTag,
              child: const Text('Degistir'),
            ),
            const SizedBox(width: 8),
            FilledButton.tonal(
              onPressed: _selectedCatalogTag == null
                  ? null
                  : () {
                      widget.onDeleteTagGlobally(_selectedCatalogTag!);
                    },
              child: const Text('Tumden sil'),
            ),
          ],
        ),
      ],
    );
  }
}

class _OverridePill extends StatelessWidget {
  const _OverridePill({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: const Color(0x33FFA574),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: const Color(0x66FFA574)),
      ),
      child: Text(
        label,
        style: Theme.of(context).textTheme.labelSmall?.copyWith(
          color: const Color(0xFFFFC2A1),
          fontWeight: FontWeight.w700,
        ),
      ),
    );
  }
}

class _InspectorTile extends StatelessWidget {
  const _InspectorTile({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text(
            label,
            style: Theme.of(
              context,
            ).textTheme.labelMedium?.copyWith(color: Colors.white54),
          ),
          const SizedBox(height: 3),
          Text(
            value.isEmpty ? '-' : value,
            style: Theme.of(context).textTheme.bodyMedium,
          ),
        ],
      ),
    );
  }
}

class _MetricTile extends StatelessWidget {
  const _MetricTile({required this.label, required this.value});

  final String label;
  final double? value;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        children: <Widget>[
          Expanded(
            child: Text(
              label,
              style: theme.textTheme.bodySmall?.copyWith(color: Colors.white70),
            ),
          ),
          Text(
            value == null ? '-' : value!.toStringAsFixed(3),
            style: theme.textTheme.bodySmall?.copyWith(
              color: Colors.white,
              fontFeatures: const <FontFeature>[FontFeature.tabularFigures()],
            ),
          ),
        ],
      ),
    );
  }
}

class _RawPlaceholder extends StatelessWidget {
  const _RawPlaceholder();

  @override
  Widget build(BuildContext context) {
    return Container(
      color: const Color(0xFF20242B),
      alignment: Alignment.center,
      child: const Icon(Icons.raw_on_rounded, color: Colors.white54),
    );
  }
}

class _PreviewArrowButton extends StatelessWidget {
  const _PreviewArrowButton({
    required this.icon,
    required this.onPressed,
    required this.tooltip,
  });

  final IconData icon;
  final VoidCallback onPressed;
  final String tooltip;

  @override
  Widget build(BuildContext context) {
    return Tooltip(
      message: tooltip,
      child: Material(
        color: Colors.black.withValues(alpha: 0.34),
        borderRadius: BorderRadius.circular(999),
        child: InkWell(
          onTap: onPressed,
          borderRadius: BorderRadius.circular(999),
          child: SizedBox(
            width: 32,
            height: 32,
            child: Icon(icon, size: 19, color: Colors.white),
          ),
        ),
      ),
    );
  }
}

class _BasicPreviewHud extends StatelessWidget {
  const _BasicPreviewHud({
    required this.viewerMode,
    required this.selectedFolder,
    required this.onBrowse,
    required this.onOpenSettings,
    required this.onModeChanged,
  });

  final _ViewerMode viewerMode;
  final String? selectedFolder;
  final Future<void> Function() onBrowse;
  final VoidCallback onOpenSettings;
  final ValueChanged<_ViewerMode> onModeChanged;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final hasFolder = selectedFolder != null && selectedFolder!.isNotEmpty;
    return DecoratedBox(
      decoration: BoxDecoration(
        color: Colors.black.withValues(alpha: 0.24),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: Colors.white.withValues(alpha: 0.06)),
      ),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(8, 6, 8, 5),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Row(
              children: <Widget>[
                Container(
                  width: 46,
                  height: 46,
                  decoration: BoxDecoration(
                    color: Colors.white.withValues(alpha: 0.06),
                    borderRadius: BorderRadius.circular(14),
                    border: Border.all(
                      color: Colors.white.withValues(alpha: 0.06),
                    ),
                  ),
                  child: Padding(
                    padding: const EdgeInsets.all(4),
                    child: ClipRRect(
                      borderRadius: BorderRadius.circular(10),
                      child: Image.asset(_brandAssetPath, fit: BoxFit.contain),
                    ),
                  ),
                ),
                const Spacer(),
                DecoratedBox(
                  decoration: BoxDecoration(
                    color: Colors.white.withValues(alpha: 0.03),
                    borderRadius: BorderRadius.circular(999),
                    border: Border.all(
                      color: Colors.white.withValues(alpha: 0.06),
                    ),
                  ),
                  child: Padding(
                    padding: const EdgeInsets.all(2),
                    child: SegmentedButton<_ViewerMode>(
                      segments: const <ButtonSegment<_ViewerMode>>[
                        ButtonSegment<_ViewerMode>(
                          value: _ViewerMode.basic,
                          label: Text('Basic', style: TextStyle(fontSize: 10)),
                        ),
                        ButtonSegment<_ViewerMode>(
                          value: _ViewerMode.advanced,
                          label: Text(
                            'Advanced',
                            style: TextStyle(fontSize: 10),
                          ),
                        ),
                      ],
                      selected: <_ViewerMode>{viewerMode},
                      showSelectedIcon: false,
                      onSelectionChanged: (Set<_ViewerMode> values) =>
                          onModeChanged(values.first),
                      style: SegmentedButton.styleFrom(
                        visualDensity: VisualDensity.compact,
                        padding: const EdgeInsets.symmetric(
                          horizontal: 3,
                          vertical: 1,
                        ),
                        tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                      ),
                    ),
                  ),
                ),
                const Spacer(),
                Tooltip(
                  message: 'Browse klasor secimi',
                  child: _HudIconButton(
                    icon: Icons.folder_open_rounded,
                    onPressed: () {
                      onBrowse();
                    },
                  ),
                ),
                const SizedBox(width: 6),
                Tooltip(
                  message: 'Ayarlar',
                  child: _HudIconButton(
                    icon: Icons.menu_rounded,
                    onPressed: onOpenSettings,
                  ),
                ),
              ],
            ),
            if (hasFolder) ...<Widget>[
              const SizedBox(height: 3),
              Align(
                alignment: Alignment.centerRight,
                child: ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 180),
                  child: Text(
                    selectedFolder!,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    textAlign: TextAlign.right,
                    style: theme.textTheme.labelSmall?.copyWith(
                      color: Colors.white54,
                      fontSize: 9,
                    ),
                  ),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _HudIconButton extends StatelessWidget {
  const _HudIconButton({required this.icon, required this.onPressed});

  final IconData icon;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return IconButton(
      onPressed: onPressed,
      icon: Icon(icon, size: 16),
      visualDensity: VisualDensity.compact,
      style: IconButton.styleFrom(
        backgroundColor: Colors.white.withValues(alpha: 0.06),
        foregroundColor: Colors.white,
        minimumSize: const Size(24, 24),
        padding: EdgeInsets.zero,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
      ),
    );
  }
}

class _PreviewIconButton extends StatelessWidget {
  const _PreviewIconButton({required this.icon, required this.onPressed});

  final IconData icon;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.black.withValues(alpha: 0.38),
      shape: const CircleBorder(),
      child: InkWell(
        onTap: onPressed,
        customBorder: const CircleBorder(),
        child: SizedBox(
          width: 22,
          height: 22,
          child: Icon(icon, size: 12, color: Colors.white),
        ),
      ),
    );
  }
}

class _AnalysisScoreBadge extends StatelessWidget {
  const _AnalysisScoreBadge({required this.score});

  final int score;

  @override
  Widget build(BuildContext context) {
    final color = _scoreColor(score);
    return DecoratedBox(
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.86),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: Colors.white.withValues(alpha: 0.12)),
        boxShadow: <BoxShadow>[
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.22),
            blurRadius: 10,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Text(
              score.toString().padLeft(2, '0'),
              style: Theme.of(context).textTheme.labelMedium?.copyWith(
                color: Colors.white,
                fontWeight: FontWeight.w800,
                fontSize: 12,
                fontFeatures: const <FontFeature>[FontFeature.tabularFigures()],
              ),
            ),
            const SizedBox(width: 4),
            Text(
              '/100',
              style: Theme.of(context).textTheme.labelSmall?.copyWith(
                color: Colors.white.withValues(alpha: 0.88),
                fontSize: 10,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _PreviewToggleBadge extends StatelessWidget {
  const _PreviewToggleBadge({
    required this.icon,
    required this.active,
    required this.label,
    required this.onPressed,
    required this.onLongPress,
  });

  final IconData icon;
  final bool active;
  final String label;
  final VoidCallback onPressed;
  final VoidCallback onLongPress;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: active
          ? const Color(0xD67A4A2A)
          : Colors.black.withValues(alpha: 0.42),
      borderRadius: BorderRadius.circular(999),
      child: InkWell(
        onTap: onPressed,
        onLongPress: onLongPress,
        borderRadius: BorderRadius.circular(999),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 5),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              Icon(icon, size: 10, color: Colors.white),
              const SizedBox(width: 4),
              Text(
                label,
                style: Theme.of(context).textTheme.labelSmall?.copyWith(
                  color: Colors.white,
                  fontWeight: FontWeight.w700,
                  fontSize: 9.5,
                  fontFeatures: const <FontFeature>[
                    FontFeature.tabularFigures(),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _PreviewStepButton extends StatelessWidget {
  const _PreviewStepButton({required this.icon, required this.onPressed});

  final IconData icon;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.black.withValues(alpha: 0.42),
      borderRadius: BorderRadius.circular(999),
      child: InkWell(
        onTap: onPressed,
        borderRadius: BorderRadius.circular(999),
        child: SizedBox(
          width: 26,
          height: 26,
          child: Icon(icon, size: 14, color: Colors.white),
        ),
      ),
    );
  }
}

class _PreviewUnavailable extends StatelessWidget {
  const _PreviewUnavailable({this.message});

  final String? message;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          const Icon(
            Icons.photo_size_select_large_rounded,
            size: 44,
            color: Colors.white54,
          ),
          const SizedBox(height: 12),
          Text(message ?? 'Bu dosya icin preview hazir degil.'),
        ],
      ),
    );
  }
}

class _DrawerSectionTitle extends StatelessWidget {
  const _DrawerSectionTitle(this.text);

  final String text;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Text(
        text,
        style: Theme.of(
          context,
        ).textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w700),
      ),
    );
  }
}

class _ViewerEmptyState extends StatelessWidget {
  const _ViewerEmptyState();

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 520),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Container(
              width: 84,
              height: 84,
              decoration: BoxDecoration(
                color: const Color(0xFF20242B),
                borderRadius: BorderRadius.circular(28),
              ),
              child: const Icon(
                Icons.photo_library_outlined,
                size: 38,
                color: Colors.white70,
              ),
            ),
            const SizedBox(height: 18),
            Text(
              'Bir klasör seç ve fotoğrafları büyük ekranda incelemeye başla.',
              textAlign: TextAlign.center,
              style: theme.textTheme.titleMedium?.copyWith(
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: 10),
            Text(
              'Files ve Details kapalı başlayacak. Böylece odağın önce fotoğrafta kalacak.',
              textAlign: TextAlign.center,
              style: theme.textTheme.bodyMedium?.copyWith(
                color: Colors.white70,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _PreviewOverlayPainter extends CustomPainter {
  const _PreviewOverlayPainter({
    required this.snapshot,
    required this.showCameraAf,
    required this.showSharpGuess,
    required this.zoom,
  });

  final PreviewSnapshot? snapshot;
  final bool showCameraAf;
  final bool showSharpGuess;
  final double zoom;

  @override
  void paint(Canvas canvas, Size size) {
    final snapshot = this.snapshot;
    if (snapshot == null ||
        snapshot.previewWidth == null ||
        snapshot.previewHeight == null) {
      return;
    }

    final sourceWidth = snapshot.previewWidth!.toDouble();
    final sourceHeight = snapshot.previewHeight!.toDouble();
    if (sourceWidth <= 0 || sourceHeight <= 0) {
      return;
    }

    final fitted = applyBoxFit(
      BoxFit.contain,
      Size(sourceWidth, sourceHeight),
      size,
    );
    final renderRect = Alignment.center.inscribe(
      fitted.destination,
      Offset.zero & size,
    );
    final scaleX = renderRect.width / sourceWidth;
    final scaleY = renderRect.height / sourceHeight;

    if (showCameraAf) {
      final effectiveZoom = zoom <= 0 ? 1.0 : zoom;
      final rectStroke = Paint()
        ..color = const Color(0xFFE13030)
        ..style = PaintingStyle.stroke
        ..strokeWidth = (2.4 / effectiveZoom).clamp(1.1, 2.4);
      final labelPainter = TextPainter(textDirection: TextDirection.ltr);

      for (final PreviewFocusRect rect in snapshot.cameraAfRects) {
        final drawRect = Rect.fromLTWH(
          renderRect.left + (rect.x * scaleX),
          renderRect.top + (rect.y * scaleY),
          (rect.width * scaleX).clamp(10.0, size.width),
          (rect.height * scaleY).clamp(10.0, size.height),
        );
        canvas.drawRect(drawRect, rectStroke);
        if (rect.label != null && rect.label!.isNotEmpty) {
          labelPainter.text = TextSpan(
            text: rect.label,
            style: const TextStyle(
              color: Colors.white,
              fontSize: 11,
              fontWeight: FontWeight.w700,
            ),
          );
          labelPainter.layout();
          final labelRect = RRect.fromRectAndRadius(
            Rect.fromLTWH(
              drawRect.left,
              (drawRect.top - labelPainter.height - 8).clamp(
                8.0,
                size.height - labelPainter.height - 8,
              ),
              labelPainter.width + 12,
              labelPainter.height + 6,
            ),
            const Radius.circular(8),
          );
          canvas.drawRRect(labelRect, Paint()..color = const Color(0xDDE13030));
          labelPainter.paint(
            canvas,
            Offset(labelRect.left + 6, labelRect.top + 3),
          );
        }
      }
    }

    if (showSharpGuess && snapshot.sharpFocusPoint != null) {
      final point = snapshot.sharpFocusPoint!;
      final center = Offset(
        renderRect.left + (point.x * scaleX),
        renderRect.top + (point.y * scaleY),
      );
      final radius = (point.radius * ((scaleX + scaleY) / 2)).clamp(7.0, 80.0);
      final fill = Paint()
        ..color = const Color(0x40F1C40F)
        ..style = PaintingStyle.fill;
      final stroke = Paint()
        ..color = const Color(0xFFF1C40F)
        ..style = PaintingStyle.stroke
        ..strokeWidth = 2;
      canvas.drawCircle(center, radius, fill);
      canvas.drawCircle(center, radius, stroke);
      canvas.drawLine(
        Offset(center.dx - radius * 1.2, center.dy),
        Offset(center.dx + radius * 1.2, center.dy),
        stroke,
      );
      canvas.drawLine(
        Offset(center.dx, center.dy - radius * 1.2),
        Offset(center.dx, center.dy + radius * 1.2),
        stroke,
      );
    }
  }

  @override
  bool shouldRepaint(covariant _PreviewOverlayPainter oldDelegate) {
    return oldDelegate.snapshot != snapshot ||
        oldDelegate.showCameraAf != showCameraAf ||
        oldDelegate.showSharpGuess != showSharpGuess ||
        oldDelegate.zoom != zoom;
  }
}

Color _decisionColor(String? decision) {
  switch (decision) {
    case 'selected':
      return const Color(0xFF67D88B);
    case 'rejected':
      return const Color(0xFFFF7E7E);
    case 'best_of_burst':
      return const Color(0xFF8DBBFF);
    case 'candidate':
    default:
      return const Color(0xFFFFC46B);
  }
}

Color _scoreColor(int score) {
  if (score >= 75) {
    return const Color(0xFF56C97A);
  }
  if (score >= 50) {
    return const Color(0xFFFFB65C);
  }
  return const Color(0xFFFF6B6B);
}

String _formatBytes(int value) {
  if (value < 1024) {
    return '$value B';
  }
  if (value < 1024 * 1024) {
    return '${(value / 1024).toStringAsFixed(1)} KB';
  }
  if (value < 1024 * 1024 * 1024) {
    return '${(value / (1024 * 1024)).toStringAsFixed(1)} MB';
  }
  return '${(value / (1024 * 1024 * 1024)).toStringAsFixed(1)} GB';
}

String _joinNonEmpty(List<String?> values) {
  final filtered = values
      .whereType<String>()
      .where((String value) => value.trim().isNotEmpty)
      .toList();
  return filtered.isEmpty ? '-' : filtered.join(' ');
}

String _formatExposure(double? seconds) {
  if (seconds == null || seconds <= 0) {
    return '-';
  }
  if (seconds >= 1) {
    return '${seconds.toStringAsFixed(seconds % 1 == 0 ? 0 : 1)} s';
  }
  final denominator = (1 / seconds).round();
  return '1/$denominator s';
}

String _formatEv(double value) {
  final rounded = value.abs() < 0.05 ? 0.0 : value;
  final sign = rounded > 0 ? '+' : '';
  return 'EV $sign${rounded.toStringAsFixed(1)}';
}

Color _severityColor(String severity) {
  switch (severity) {
    case 'warning':
      return const Color(0xFFFFC46B);
    case 'error':
      return const Color(0xFFFF7E7E);
    case 'info':
    default:
      return const Color(0xFF8DBBFF);
  }
}

ButtonStyle _compactButtonStyle() {
  return FilledButton.styleFrom(
    visualDensity: VisualDensity.compact,
    tapTargetSize: MaterialTapTargetSize.shrinkWrap,
    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
  );
}

double exposureGainForEv(double ev) {
  final gain = math.pow(2, ev).toDouble();
  return gain.clamp(0.25, 4.0);
}

List<double> _exposureMatrix(double ev) {
  final gain = exposureGainForEv(ev);
  return <double>[
    gain,
    0,
    0,
    0,
    0,
    0,
    gain,
    0,
    0,
    0,
    0,
    0,
    gain,
    0,
    0,
    0,
    0,
    0,
    1,
    0,
  ];
}

class _MoveIntent extends Intent {
  const _MoveIntent(this.delta);

  final int delta;
}

class _ZoomIntent extends Intent {
  const _ZoomIntent(this.zoomIn);

  final bool zoomIn;
}
