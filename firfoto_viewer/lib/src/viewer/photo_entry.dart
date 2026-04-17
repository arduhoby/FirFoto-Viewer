import 'dart:io';

import 'package:path/path.dart' as p;

const supportedPhotoExtensions = <String>{
  '.jpg',
  '.jpeg',
  '.png',
  '.tif',
  '.tiff',
  '.webp',
  '.nef',
  '.dng',
  '.cr2',
  '.cr3',
  '.arw',
  '.raf',
  '.orf',
  '.rw2',
};

const previewableExtensions = <String>{
  '.jpg',
  '.jpeg',
  '.png',
  '.tif',
  '.tiff',
  '.webp',
};

class PhotoEntry {
  PhotoEntry({required this.file, required this.index})
    : extension = p.extension(file.path).toLowerCase(),
      name = p.basename(file.path),
      modifiedAt = file.statSync().modified;

  final File file;
  final int index;
  final String name;
  final String extension;
  final DateTime modifiedAt;

  bool get isPreviewable => previewableExtensions.contains(extension);
  bool get isRawLike =>
      supportedPhotoExtensions.contains(extension) && !isPreviewable;
}
