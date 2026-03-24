import AppKit
import Foundation

struct Arguments {
    let title: String
    let message: String
    let identifier: String
    let actionTitle: String
    let command: String
    let timeoutSeconds: TimeInterval

    static func parse(_ argv: [String]) throws -> Arguments {
        var values: [String: String] = [:]
        var index = 1
        while index < argv.count {
            let key = argv[index]
            guard key.hasPrefix("--") else {
                throw NotifierError("Unexpected argument: \(key)")
            }
            let name = String(key.dropFirst(2))
            index += 1
            guard index < argv.count else {
                throw NotifierError("Missing value for --\(name)")
            }
            values[name] = argv[index]
            index += 1
        }

        guard let title = values["title"], !title.isEmpty else {
            throw NotifierError("Missing --title")
        }
        let message = values["message"] ?? ""
        guard let identifier = values["identifier"], !identifier.isEmpty else {
            throw NotifierError("Missing --identifier")
        }
        let actionTitle = values["action-title"] ?? "Jump"
        guard let command = values["command"], !command.isEmpty else {
            throw NotifierError("Missing --command")
        }

        let timeoutSeconds = TimeInterval(values["timeout-seconds"] ?? "600") ?? 600
        return Arguments(
            title: title,
            message: message,
            identifier: identifier,
            actionTitle: actionTitle,
            command: command,
            timeoutSeconds: timeoutSeconds
        )
    }
}

struct NotifierError: Error, CustomStringConvertible {
    let description: String

    init(_ description: String) {
        self.description = description
    }
}

final class CodexNotifier: NSObject, NSUserNotificationCenterDelegate {
    private let arguments: Arguments
    private let center = NSUserNotificationCenter.default
    private var currentNotification: NSUserNotification?
    private var hasExited = false

    init(arguments: Arguments) {
        self.arguments = arguments
    }

    func run() {
        center.delegate = self
        deliverNotification()
        NSApplication.shared.run()
    }

    func userNotificationCenter(
        _ center: NSUserNotificationCenter,
        shouldPresent notification: NSUserNotification
    ) -> Bool {
        true
    }

    func userNotificationCenter(
        _ center: NSUserNotificationCenter,
        didDeliver notification: NSUserNotification
    ) {
        currentNotification = notification
        startDismissalPolling(for: notification)
        startTimeoutIfNeeded(for: notification)
    }

    func userNotificationCenter(
        _ center: NSUserNotificationCenter,
        didActivate notification: NSUserNotification
    ) {
        guard notification.identifier == arguments.identifier else {
            return
        }

        let shouldExecute: Bool
        switch notification.activationType {
        case .actionButtonClicked, .additionalActionClicked, .contentsClicked:
            shouldExecute = true
        default:
            shouldExecute = false
        }

        if shouldExecute {
            executeCommand()
        }

        cleanup()
        finish()
    }

    private func deliverNotification() {
        cleanup()

        let notification = NSUserNotification()
        notification.identifier = arguments.identifier
        notification.title = arguments.title
        notification.informativeText = arguments.message
        notification.userInfo = ["identifier": arguments.identifier]
        notification.soundName = NSUserNotificationDefaultSoundName
        notification.actionButtonTitle = arguments.actionTitle
        notification.setValue(true, forKey: "_showsButtons")
        notification.hasActionButton = true

        center.deliver(notification)
    }

    private func startDismissalPolling(for notification: NSUserNotification) {
        let identifier = arguments.identifier
        DispatchQueue.global().async { [weak self] in
            while true {
                let stillPresent = NSUserNotificationCenter.default.deliveredNotifications.contains {
                    $0.identifier == identifier
                }
                if !stillPresent {
                    DispatchQueue.main.async {
                        self?.finish()
                    }
                    return
                }
                Thread.sleep(forTimeInterval: 0.2)
            }
        }
    }

    private func startTimeoutIfNeeded(for notification: NSUserNotification) {
        guard arguments.timeoutSeconds > 0 else {
            return
        }

        DispatchQueue.main.asyncAfter(deadline: .now() + arguments.timeoutSeconds) { [weak self] in
            guard let self else { return }
            self.center.removeDeliveredNotification(notification)
            self.finish()
        }
    }

    private func executeCommand() {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/bin/zsh")
        process.arguments = ["-lc", arguments.command]
        process.standardInput = nil
        process.standardOutput = nil
        process.standardError = nil

        do {
            try process.run()
            process.waitUntilExit()
        } catch {
            fputs("Failed to execute click command: \(error.localizedDescription)\n", stderr)
        }
    }

    private func cleanup() {
        if let currentNotification {
            center.removeDeliveredNotification(currentNotification)
        }
        for notification in center.deliveredNotifications where notification.identifier == arguments.identifier {
            center.removeDeliveredNotification(notification)
        }
    }

    private func finish() {
        guard !hasExited else {
            return
        }
        hasExited = true
        NSApplication.shared.stop(nil)
        exit(0)
    }
}

do {
    let arguments = try Arguments.parse(CommandLine.arguments)
    let notifier = CodexNotifier(arguments: arguments)
    notifier.run()
} catch {
    fputs("\(error)\n", stderr)
    exit(1)
}
