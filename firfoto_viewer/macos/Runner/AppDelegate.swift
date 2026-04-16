import Cocoa
import FlutterMacOS

@main
class AppDelegate: FlutterAppDelegate {
  private var openFileChannel: FlutterMethodChannel?
  private var pendingOpenFiles: [String] = []
  private var startupOpenFiles = AppDelegate.detectStartupOpenFiles()
  private var isOpenFileClientReady = false

  override func applicationDidFinishLaunching(_ notification: Notification) {
    super.applicationDidFinishLaunching(notification)
    NSAppleEventManager.shared().setEventHandler(
      self,
      andSelector: #selector(handleOpenDocumentsEvent(_:withReplyEvent:)),
      forEventClass: AEEventClass(kCoreEventClass),
      andEventID: AEEventID(kAEOpenDocuments)
    )
  }

  override func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
    return true
  }

  override func applicationSupportsSecureRestorableState(_ app: NSApplication) -> Bool {
    return true
  }

  override func application(_ sender: NSApplication, openFiles filenames: [String]) {
    enqueueOpenFiles(filenames)
    sender.reply(toOpenOrPrint: .success)
  }

  override func application(_ sender: NSApplication, openFile filename: String) -> Bool {
    enqueueOpenFiles([filename])
    return true
  }

  override func application(_ application: NSApplication, open urls: [URL]) {
    enqueueOpenFiles(urls.filter(\.isFileURL).map(\.path))
  }

  func configureOpenFileBridge(flutterViewController: FlutterViewController) {
    let channel = FlutterMethodChannel(
      name: "firfoto/open_file",
      binaryMessenger: flutterViewController.engine.binaryMessenger
    )
    openFileChannel = channel
    channel.setMethodCallHandler { [weak self] (call: FlutterMethodCall, result: @escaping FlutterResult) in
      guard let self else {
        result(FlutterMethodNotImplemented)
        return
      }

      switch call.method {
      case "consumePendingOpenFiles":
        result(self.consumePendingOpenFiles())
      case "markOpenFileClientReady":
        self.isOpenFileClientReady = true
        self.flushPendingOpenFiles()
        result(NSNull())
      default:
        result(FlutterMethodNotImplemented)
      }
    }
  }

  private func enqueueOpenFiles(_ filenames: [String]) {
    let normalized = filenames
      .map { URL(fileURLWithPath: NSString(string: $0).expandingTildeInPath).standardizedFileURL.path }
      .filter { FileManager.default.fileExists(atPath: $0) }
    guard !normalized.isEmpty else {
      return
    }

    pendingOpenFiles.append(contentsOf: normalized)
    pendingOpenFiles = Array(NSOrderedSet(array: pendingOpenFiles)) as? [String] ?? pendingOpenFiles
    flushPendingOpenFiles()
  }

  private func consumePendingOpenFiles() -> [String] {
    let files = Array(NSOrderedSet(array: startupOpenFiles + pendingOpenFiles)) as? [String]
      ?? (startupOpenFiles + pendingOpenFiles)
    startupOpenFiles.removeAll()
    pendingOpenFiles.removeAll()
    return files
  }

  private func flushPendingOpenFiles() {
    guard let openFileChannel, isOpenFileClientReady, !pendingOpenFiles.isEmpty else {
      return
    }

    let files = consumePendingOpenFiles()
    openFileChannel.invokeMethod("openFiles", arguments: files)
  }

  private static func detectStartupOpenFiles() -> [String] {
    ProcessInfo.processInfo.arguments
      .dropFirst()
      .filter { !$0.hasPrefix("-") }
      .map { URL(fileURLWithPath: NSString(string: $0).expandingTildeInPath).standardizedFileURL.path }
      .filter { FileManager.default.fileExists(atPath: $0) }
  }

  @objc private func handleOpenDocumentsEvent(
    _ event: NSAppleEventDescriptor,
    withReplyEvent replyEvent: NSAppleEventDescriptor
  ) {
    guard let documents = event.paramDescriptor(forKeyword: AEKeyword(keyDirectObject)) else {
      return
    }

    let itemCount = documents.numberOfItems
    guard itemCount > 0 else {
      return
    }

    var paths: [String] = []
    for index in 1...itemCount {
      guard
        let item = documents.atIndex(index),
        let rawValue = item.stringValue,
        let url = URL(string: rawValue), url.isFileURL
      else {
        continue
      }
      paths.append(url.standardizedFileURL.path)
    }

    enqueueOpenFiles(paths)
  }
}
