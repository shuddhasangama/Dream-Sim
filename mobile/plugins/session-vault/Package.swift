// swift-tools-version: 5.9
import PackageDescription

// iOS-only local Capacitor plugin — mirrors android/app/src/main/java/com/dhashu/app/
// SessionVault.java in observable behaviour. There is no Android target here on
// purpose: the Android side stays registered directly in MainActivity.java, outside
// this package, and this file's job is only to get the iOS half compiled into the
// app's Xcode target via SPM (which copying loose files into ios/App/App/ after
// `cap add ios` never did — nothing referenced them in the generated project).
let package = Package(
    name: "SessionVault",
    platforms: [.iOS(.v14)],
    products: [
        .library(
            name: "SessionVault",
            targets: ["SessionVaultPlugin"])
    ],
    dependencies: [
        .package(url: "https://github.com/ionic-team/capacitor-swift-pm.git", from: "8.0.0")
    ],
    targets: [
        .target(
            name: "SessionVaultPlugin",
            dependencies: [
                .product(name: "Capacitor", package: "capacitor-swift-pm")
            ],
            path: "ios/Sources/SessionVaultPlugin")
    ]
)
