import Foundation
import Capacitor
import Security

/// Only the rotating refresh credential is persisted; no OTP or profile data.
///
/// Mirrors android/app/src/main/java/com/dhashu/app/SessionVault.java exactly in
/// observable behaviour — method names, the `value` parameter/result key,
/// resolve/reject shapes, the 32-128 char validation on write, and every reject
/// message string. The secure store itself differs by necessity: Android hand-
/// rolls AES/GCM against an AndroidKeyStore key over SharedPreferences, while
/// here the iOS Keychain already provides equivalent at-rest, non-exportable
/// encryption, so there's no separate cipher step on this side.
@objc(SessionVaultPlugin)
public class SessionVaultPlugin: CAPPlugin {
    private let service = "dhashu.session.v1"
    private let account = "dhashu.session.v1"

    /// Class + service + account only — the stable identity of the Keychain
    /// item, used to find it for read/update/delete. Attributes that describe
    /// how to store a *new* value (accessibility, the value itself) are added
    /// on top of this for add, never included when searching for update/delete.
    private func baseQuery() -> [String: Any] {
        return [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
        ]
    }

    @objc func write(_ call: CAPPluginCall) {
        guard let value = call.getString("value"), value.count >= 32, value.count <= 128 else {
            call.reject("Invalid credential.")
            return
        }
        guard let data = value.data(using: .utf8) else {
            call.reject("Secure storage unavailable.")
            return
        }

        var addQuery = baseQuery()
        // AfterFirstUnlockThisDeviceOnly: readable in the background once the
        // device has been unlocked after boot, never included in an iCloud/
        // iTunes backup and never synced to another device — the iOS
        // equivalent of the Android side's key never leaving that device
        // either (AndroidKeyStore keys are non-exportable by design).
        addQuery[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        addQuery[kSecValueData as String] = data

        let addStatus = SecItemAdd(addQuery as CFDictionary, nil)

        if addStatus == errSecSuccess {
            call.resolve()
            return
        }

        if addStatus == errSecDuplicateItem {
            // Update-vs-add: an item is already there for this service/account,
            // so overwrite its value in place instead of failing. The search
            // query for update must NOT carry kSecValueData/kSecAttrAccessible
            // — only the attributes below are what gets changed.
            let updateStatus = SecItemUpdate(baseQuery() as CFDictionary, [kSecValueData as String: data] as CFDictionary)
            if updateStatus == errSecSuccess {
                call.resolve()
            } else {
                call.reject("Secure storage unavailable.")
            }
            return
        }

        call.reject("Secure storage unavailable.")
    }

    @objc func read(_ call: CAPPluginCall) {
        var query = baseQuery()
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne

        var item: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &item)

        if status == errSecItemNotFound {
            call.resolve(["value": NSNull()])
            return
        }

        guard status == errSecSuccess, let data = item as? Data, let value = String(data: data, encoding: .utf8) else {
            // Mirrors the Java side's self-heal on a decrypt/read failure: an
            // entry that can't be read back cleanly is discarded rather than
            // left behind for the next call to trip over again.
            SecItemDelete(baseQuery() as CFDictionary)
            call.reject("Stored session is unavailable. Sign in again.")
            return
        }

        call.resolve(["value": value])
    }

    @objc func clear(_ call: CAPPluginCall) {
        let status = SecItemDelete(baseQuery() as CFDictionary)
        if status == errSecSuccess || status == errSecItemNotFound {
            call.resolve()
        } else {
            call.reject("Could not clear secure storage.")
        }
    }
}
