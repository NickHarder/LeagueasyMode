import Foundation

/// A spell the player marks an enemy as having used.
public enum MarkedSpell: String, Sendable, CaseIterable {
    /// Their Flash, or their first summoner spell when they have no Flash.
    case flash
    /// Their other summoner spell.
    case summoner
    /// Their ultimate.
    case ultimate
}

/// One mark: an enemy, by their place in role order (1 top to 5 support), and the spell they used.
public struct CooldownMark: Equatable, Sendable {
    public let enemySlot: Int
    public let spell: MarkedSpell

    public init(enemySlot: Int, spell: MarkedSpell) {
        self.enemySlot = enemySlot
        self.spell = spell
    }
}

/// The two presses of a mark: ⌃⌥ and a digit picks an enemy, then ⌃⌥ and F, D or R names the spell.
///
/// Every key carries ⌃⌥, so that marking never takes a key League uses. A pick waits a few
/// seconds for its spell; a spell with no pick waiting marks nothing, and each pick makes at most
/// one mark.
public struct MarkSequence: Sendable {
    /// How long a picked enemy waits for its spell.
    public static let pickWaitSeconds: Double = 3
    /// The places an enemy can have in role order.
    public static let enemySlots = 1...5

    private var pickedSlot: Int?
    private var pickedAtSeconds: Double = 0

    public init() {}

    /// Picks an enemy; a later pick replaces an earlier one.
    ///
    /// - Parameters:
    ///   - slot: The enemy's place in role order, 1 for top to 5 for support.
    ///   - atSeconds: When the key was pressed, on any steady clock.
    public mutating func pickEnemy(slot: Int, atSeconds: Double) {
        guard Self.enemySlots.contains(slot) else {
            pickedSlot = nil
            return
        }
        pickedSlot = slot
        pickedAtSeconds = atSeconds
    }

    /// Names the spell of the waiting pick.
    ///
    /// - Parameters:
    ///   - spell: The spell.
    ///   - atSeconds: When the key was pressed, on the same clock as the pick.
    /// - Returns: The mark, or nil when no pick is waiting or it waited too long.
    public mutating func markSpell(_ spell: MarkedSpell, atSeconds: Double) -> CooldownMark? {
        let waitingSlot = pickedSlot
        pickedSlot = nil
        guard
            let waitingSlot,
            atSeconds >= pickedAtSeconds,
            atSeconds - pickedAtSeconds <= Self.pickWaitSeconds
        else {
            return nil
        }
        return CooldownMark(enemySlot: waitingSlot, spell: spell)
    }
}

/// The request that carries a mark to the engine's local server.
public enum MarkRequest {
    /// The header the engine requires on a mark, which a web page cannot send it.
    public static let headerName = "X-LeagueasyMode-Request"
    public static let headerValue = "mark"

    /// Returns the request that posts a mark to `/marks` beside the overlay page.
    ///
    /// - Parameters:
    ///   - overlayURL: The overlay page's address, as the engine announced it.
    ///   - mark: The mark.
    /// - Returns: The request.
    public static func make(overlayURL: URL, mark: CooldownMark) -> URLRequest {
        var request = URLRequest(url: overlayURL.appendingPathComponent("marks"))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue(headerValue, forHTTPHeaderField: headerName)
        // Both values are the app's own, a number and a fixed word, so the JSON is written out.
        request.httpBody = Data(
            "{\"enemy_slot\":\(mark.enemySlot),\"spell\":\"\(mark.spell.rawValue)\"}".utf8
        )
        return request
    }
}
