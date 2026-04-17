class AnalysisSummary {
  const AnalysisSummary({
    required this.path,
    required this.decision,
    required this.category,
    required this.overallQuality,
    required this.sharpness,
    required this.exposure,
    required this.contrast,
    required this.noise,
    required this.motionBlurProbability,
    required this.reasons,
    required this.reasonSeverities,
    required this.notes,
    this.tags = const <String>[],
    this.isDecisionOverridden = false,
    this.isCategoryOverridden = false,
  });

  final String path;
  final String decision;
  final String category;
  final double? overallQuality;
  final double? sharpness;
  final double? exposure;
  final double? contrast;
  final double? noise;
  final double? motionBlurProbability;
  final List<String> reasons;
  final List<String> reasonSeverities;
  final List<String> notes;
  final List<String> tags;
  final bool isDecisionOverridden;
  final bool isCategoryOverridden;

  factory AnalysisSummary.placeholder({
    required String path,
    String decision = 'candidate',
    String category = 'general',
  }) {
    return AnalysisSummary(
      path: path,
      decision: decision,
      category: category,
      overallQuality: null,
      sharpness: null,
      exposure: null,
      contrast: null,
      noise: null,
      motionBlurProbability: null,
      reasons: const <String>[],
      reasonSeverities: const <String>[],
      notes: const <String>[],
      tags: const <String>[],
    );
  }

  factory AnalysisSummary.fromJson(Map<String, dynamic> json) {
    final metrics = (json['metrics'] as Map<String, dynamic>?) ?? const <String, dynamic>{};
    final hints = (json['hints'] as Map<String, dynamic>?) ?? const <String, dynamic>{};
    final reasonsJson = (json['reasons'] as List<dynamic>?) ?? const <dynamic>[];
    return AnalysisSummary(
      path: json['path']?.toString() ?? '',
      decision: json['decision']?.toString() ?? 'candidate',
      category: hints['category']?.toString() ?? 'general',
      overallQuality: (metrics['overall_quality'] as num?)?.toDouble(),
      sharpness: (metrics['sharpness'] as num?)?.toDouble(),
      exposure: (metrics['exposure'] as num?)?.toDouble(),
      contrast: (metrics['contrast'] as num?)?.toDouble(),
      noise: (metrics['noise'] as num?)?.toDouble(),
      motionBlurProbability: (metrics['motion_blur_probability'] as num?)?.toDouble(),
      reasons: reasonsJson
          .whereType<Map<String, dynamic>>()
          .map((item) => item['message']?.toString() ?? '')
          .where((value) => value.isNotEmpty)
          .toList(),
      reasonSeverities: reasonsJson
          .whereType<Map<String, dynamic>>()
          .map((item) => item['severity']?.toString() ?? 'info')
          .toList(),
      notes: ((metrics['notes'] as List<dynamic>?) ?? const <dynamic>[])
          .map((item) => item.toString())
          .toList(),
    );
  }

  AnalysisSummary copyWith({
    String? decision,
    String? category,
    bool? isDecisionOverridden,
    bool? isCategoryOverridden,
    List<String>? tags,
  }) {
    return AnalysisSummary(
      path: path,
      decision: decision ?? this.decision,
      category: category ?? this.category,
      overallQuality: overallQuality,
      sharpness: sharpness,
      exposure: exposure,
      contrast: contrast,
      noise: noise,
      motionBlurProbability: motionBlurProbability,
      reasons: reasons,
      reasonSeverities: reasonSeverities,
      notes: notes,
      tags: tags ?? this.tags,
      isDecisionOverridden: isDecisionOverridden ?? this.isDecisionOverridden,
      isCategoryOverridden: isCategoryOverridden ?? this.isCategoryOverridden,
    );
  }
}
