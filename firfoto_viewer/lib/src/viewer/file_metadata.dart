class FileMetadataSnapshot {
  FileMetadataSnapshot({
    required this.path,
    required this.sizeBytes,
    required this.suffix,
    required this.categoryHint,
    required this.notes,
    this.width,
    this.height,
    this.cameraMaker,
    this.cameraModel,
    this.cameraSerial,
    this.lensMaker,
    this.lensModel,
    this.focalLengthMm,
    this.apertureF,
    this.exposureTimeS,
    this.iso,
    this.afPointLabel,
    this.afAreaMode,
    this.afDetectionMethod,
    this.afAreaX,
    this.afAreaY,
    this.afAreaWidth,
    this.afAreaHeight,
  });

  final String path;
  final int sizeBytes;
  final String suffix;
  final int? width;
  final int? height;
  final String? cameraMaker;
  final String? cameraModel;
  final String? cameraSerial;
  final String? lensMaker;
  final String? lensModel;
  final double? focalLengthMm;
  final double? apertureF;
  final double? exposureTimeS;
  final int? iso;
  final String? afPointLabel;
  final String? afAreaMode;
  final String? afDetectionMethod;
  final int? afAreaX;
  final int? afAreaY;
  final int? afAreaWidth;
  final int? afAreaHeight;
  final String categoryHint;
  final List<String> notes;

  factory FileMetadataSnapshot.fromJson(Map<String, dynamic> json) {
    final camera = (json['camera'] as Map?)?.cast<String, dynamic>() ?? const {};
    final lens = (json['lens'] as Map?)?.cast<String, dynamic>() ?? const {};
    final capture = (json['capture'] as Map?)?.cast<String, dynamic>() ?? const {};
    final af = (json['af'] as Map?)?.cast<String, dynamic>() ?? const {};
    final notes = (json['notes'] as List?)?.map((item) => item.toString()).toList() ?? const <String>[];

    return FileMetadataSnapshot(
      path: json['path']?.toString() ?? '',
      sizeBytes: (json['size_bytes'] as num?)?.toInt() ?? 0,
      suffix: json['suffix']?.toString() ?? '',
      width: (json['width'] as num?)?.toInt(),
      height: (json['height'] as num?)?.toInt(),
      cameraMaker: camera['maker']?.toString(),
      cameraModel: camera['model']?.toString(),
      cameraSerial: camera['serial_number']?.toString(),
      lensMaker: lens['maker']?.toString(),
      lensModel: lens['model']?.toString(),
      focalLengthMm: (capture['focal_length_mm'] as num?)?.toDouble(),
      apertureF: (capture['aperture_f'] as num?)?.toDouble(),
      exposureTimeS: (capture['exposure_time_s'] as num?)?.toDouble(),
      iso: (capture['iso'] as num?)?.toInt(),
      afPointLabel: af['point_label']?.toString(),
      afAreaMode: af['area_mode']?.toString(),
      afDetectionMethod: af['detection_method']?.toString(),
      afAreaX: (af['area_x'] as num?)?.toInt(),
      afAreaY: (af['area_y'] as num?)?.toInt(),
      afAreaWidth: (af['area_width'] as num?)?.toInt(),
      afAreaHeight: (af['area_height'] as num?)?.toInt(),
      categoryHint: json['category_hint']?.toString() ?? 'general',
      notes: notes,
    );
  }
}
