import SwiftUI

@main
struct Sim2ClawDemoControlApp: App {
    @State private var store = DemoControlStore()

    var body: some Scene {
        WindowGroup("sim2claw Demo Control") {
            ContentView()
                .environment(store)
        }
        .windowResizability(.contentSize)
        .commands {
            CommandGroup(replacing: .newItem) {}
        }
    }
}
