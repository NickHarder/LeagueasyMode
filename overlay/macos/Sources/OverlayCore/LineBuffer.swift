import Foundation

/// Gathers the bytes a pipe hands over, in whatever pieces they come, into whole lines.
public struct LineBuffer {
    private var pendingBytes = Data()

    /// Starts with nothing pending.
    public init() {}

    /// Adds bytes read from a pipe and returns each line they complete.
    ///
    /// - Parameter newBytes: The bytes just read.
    /// - Returns: The completed lines, oldest first, without their newlines. A line still
    ///   waiting for its newline stays pending.
    public mutating func append(_ newBytes: Data) -> [String] {
        pendingBytes.append(newBytes)
        var completedLines: [String] = []
        while let newlineIndex = pendingBytes.firstIndex(of: UInt8(ascii: "\n")) {
            let lineBytes = pendingBytes[pendingBytes.startIndex..<newlineIndex]
            completedLines.append(String(decoding: lineBytes, as: UTF8.self))
            pendingBytes.removeSubrange(pendingBytes.startIndex...newlineIndex)
        }
        return completedLines
    }
}
