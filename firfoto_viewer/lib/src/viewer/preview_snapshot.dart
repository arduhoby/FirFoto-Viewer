class PreviewSnapshot {
  const PreviewSnapshot({
    required this.outputPath,
    required this.previewWidth,
    required this.previewHeight,
    required this.meanLuma,
    required this.suggestedExposureEv,
    required this.sharpFocusPoint,
    required this.cameraAfRects,
  });

  final String outputPath;
  final int? previewWidth;
  final int? previewHeight;
  final double? meanLuma;
  final double? suggestedExposureEv;
  final PreviewFocusPoint? sharpFocusPoint;
  final List<PreviewFocusRect> cameraAfRects;

  factory PreviewSnapshot.fromJson(Map<String, dynamic> json) {
    final sharp = json['sharp_focus_point'];
    final rects = (json['camera_af_rects'] as List<dynamic>?) ?? const <dynamic>[];
    return PreviewSnapshot(
      outputPath: json['output_path']?.toString() ?? '',
      previewWidth: (json['preview_width'] as num?)?.toInt(),
      previewHeight: (json['preview_height'] as num?)?.toInt(),
      meanLuma: (json['mean_luma'] as num?)?.toDouble(),
      suggestedExposureEv: (json['suggested_exposure_ev'] as num?)?.toDouble(),
      sharpFocusPoint: sharp is Map<String, dynamic> ? PreviewFocusPoint.fromJson(sharp) : null,
      cameraAfRects: rects
          .whereType<Map<String, dynamic>>()
          .map(PreviewFocusRect.fromJson)
          .toList(),
    );
  }
}

class PreviewFocusPoint {
  const PreviewFocusPoint({
    required this.x,
    required this.y,
    required this.radius,
    required this.score,
    required this.label,
    required this.source,
  });

  final double x;
  final double y;
  final double radius;
  final double score;
  final String? label;
  final String source;

  factory PreviewFocusPoint.fromJson(Map<String, dynamic> json) {
    return PreviewFocusPoint(
      x: (json['x'] as num?)?.toDouble() ?? 0,
      y: (json['y'] as num?)?.toDouble() ?? 0,
      radius: (json['radius'] as num?)?.toDouble() ?? 0,
      score: (json['score'] as num?)?.toDouble() ?? 0,
      label: json['label']?.toString(),
      source: json['source']?.toString() ?? 'sharpness',
    );
  }
}

class PreviewFocusRect {
  const PreviewFocusRect({
    required this.x,
    required this.y,
    required this.width,
    required this.height,
    required this.label,
    required this.source,
  });

  final double x;
  final double y;
  final double width;
  final double height;
  final String? label;
  final String source;

  factory PreviewFocusRect.fromJson(Map<String, dynamic> json) {
    return PreviewFocusRect(
      x: (json['x'] as num?)?.toDouble() ?? 0,
      y: (json['y'] as num?)?.toDouble() ?? 0,
      width: (json['width'] as num?)?.toDouble() ?? 0,
      height: (json['height'] as num?)?.toDouble() ?? 0,
      label: json['label']?.toString(),
      source: json['source']?.toString() ?? 'maker_note',
    );
  }
}
