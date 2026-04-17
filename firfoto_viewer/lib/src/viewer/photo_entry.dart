import 'dart:io';

import 'package:path/path.dart' as p;

const supportedPhotoExtensions = <String>{
  '.jpg',
  '.jpeg',
  '.png',
  '.tif',
  '.tiff',
  '.webp',
  '.heic',
  '.heif',
  '.avif',
  '.nef',
  '.nrw',
  '.cr2',
  '.cr3',
  '.arw',
  '.srf',
  '.sr2',
  '.raf',
  '.orf',
  '.rw2',
  '.pef',
  '.ptx',
  '.rwl',
  '.dng',
  '.3fr',
  '.fff',
  '.erf',
  '.mef',
  '.mos',
  '.mrw',
  '.iiq',
  '.srw',
  '.x3f',
  '.gpr',
  '.mpo',
  '.kdc',
  '.dcr',
  '.gif',
  '.mp4',
  '.mov',
  '.mkv',
};

const previewableExtensions = <String>{
  '.jpg',
  '.jpeg',
  '.png',
  '.tif',
  '.tiff',
  '.webp',
  '.gif',
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
