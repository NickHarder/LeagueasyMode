import Foundation

/// The request for a problem report, which the engine makes and sends with the games
/// (`problem_report.py`): the player's note, if they wrote one, and the app's own lines from its
/// menu, which the engine cannot see.
public enum ProblemReportRequest {
    public static let headerValue = "report"

    /// Returns the request that posts a report's note and the app's lines to `/report`.
    ///
    /// - Parameters:
    ///   - overlayURL: The overlay page's address, as the engine announced it.
    ///   - note: What the player wrote; empty when nothing.
    ///   - appFacts: The app's lines, by name.
    /// - Returns: The request.
    /// - Throws: An error of the JSON encoder, which strings never cause.
    public static func make(overlayURL: URL, note: String, appFacts: [String: String]) throws -> URLRequest {
        var request = URLRequest(url: overlayURL.appendingPathComponent("report"))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue(headerValue, forHTTPHeaderField: MarkRequest.headerName)
        request.httpBody = try JSONSerialization.data(withJSONObject: ["note": note, "app": appFacts])
        return request
    }
}

/// When the app starts a stopped engine again: at once, but at most five times in ten minutes, so
/// that an engine that cannot start does not start over and over. Before, an engine that stopped
/// ("Engine: stopped (exit 1)") left the overlay empty until the app was quit and opened again.
public struct EngineRestartPolicy: Sendable {
    public static let mostRestarts = 5
    public static let window: TimeInterval = 10 * 60

    private var restartTimes: [Date] = []

    public init() {}

    /// Returns whether to start the engine again now, and counts it if so.
    ///
    /// - Parameter now: The time.
    /// - Returns: Whether to start it.
    public mutating func shouldRestart(at now: Date) -> Bool {
        restartTimes = restartTimes.filter { now.timeIntervalSince($0) < Self.window }
        guard restartTimes.count < Self.mostRestarts else {
            return false
        }
        restartTimes.append(now)
        return true
    }
}
