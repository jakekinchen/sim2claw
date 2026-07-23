// swift-tools-version: 6.2
import PackageDescription

let package = Package(
    name: "Sim2ClawDemoControl",
    platforms: [.macOS(.v14)],
    products: [
        .executable(name: "Sim2ClawDemoControl", targets: ["Sim2ClawDemoControl"]),
    ],
    targets: [
        .executableTarget(
            name: "Sim2ClawDemoControl",
            path: "Sources/Sim2ClawDemoControl"
        ),
        .testTarget(
            name: "Sim2ClawDemoControlTests",
            dependencies: ["Sim2ClawDemoControl"],
            path: "Tests/Sim2ClawDemoControlTests"
        ),
    ]
)
