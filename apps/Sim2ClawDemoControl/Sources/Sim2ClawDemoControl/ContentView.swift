import SwiftUI

struct ContentView: View {
    @Environment(DemoControlStore.self) private var store

    private let columns = [
        GridItem(.flexible(), spacing: 14),
        GridItem(.flexible(), spacing: 14),
    ]

    var body: some View {
        VStack(alignment: .leading, spacing: 22) {
            header
            LazyVGrid(columns: columns, spacing: 14) {
                powerButton
                ForEach(DemoAction.allCases, id: \.rawValue) { action in
                    commandButton(action)
                }
            }
            statusPanel
        }
        .padding(24)
        .frame(minWidth: 620, minHeight: 470)
        .background(
            LinearGradient(
                colors: [Color(nsColor: .windowBackgroundColor), Color.accentColor.opacity(0.08)],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
        )
        .task {
            await store.refresh()
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(1))
                await store.refresh()
            }
        }
    }

    private var header: some View {
        HStack(alignment: .top) {
            VStack(alignment: .leading, spacing: 6) {
                Text("sim2claw")
                    .font(.system(size: 13, weight: .semibold, design: .rounded))
                    .foregroundStyle(.secondary)
                Text("Demo Control")
                    .font(.system(size: 30, weight: .bold, design: .rounded))
                Text("One follower. One overhead camera. Fixed recorded motion.")
                    .foregroundStyle(.secondary)
            }
            Spacer()
            Label(store.motionReady ? "DEMO OPEN" : "DEMO CLOSED", systemImage: store.motionReady ? "bolt.fill" : "bolt.slash")
                .font(.caption.weight(.bold))
                .foregroundStyle(store.motionReady ? .green : .secondary)
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
                .background(.thinMaterial, in: Capsule())
        }
    }

    private var powerButton: some View {
        Button {
            Task { await store.togglePower() }
        } label: {
            ControlTile(
                title: store.isPowered ? "Power Off" : "Power On",
                subtitle: store.isPowered ? "Stop Studio and close authority" : "Start Studio and initialize motion",
                systemImage: "power",
                tint: store.isPowered ? .red : .green
            )
        }
        .buttonStyle(.plain)
        .disabled(store.activity != .idle)
        .accessibilityIdentifier("power-button")
    }

    private func commandButton(_ action: DemoAction) -> some View {
        Button {
            Task { await store.run(action) }
        } label: {
            ControlTile(
                title: action.title,
                subtitle: action.subtitle,
                systemImage: action.systemImage,
                tint: action == .loop ? .orange : .accentColor
            )
        }
        .buttonStyle(.plain)
        .disabled(!store.motionReady || store.isBusy)
        .accessibilityIdentifier("demo-\(action.rawValue)-button")
    }

    private var statusPanel: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Circle()
                    .fill(store.errorMessage == nil ? (store.motionReady ? Color.green : Color.secondary) : Color.red)
                    .frame(width: 9, height: 9)
                Text(store.activity == .idle ? store.message : store.activity.label)
                    .font(.system(.body, design: .rounded, weight: .medium))
                Spacer()
                if store.isBusy { ProgressView().controlSize(.small) }
            }
            if let error = store.errorMessage {
                Text(error)
                    .font(.callout)
                    .foregroundStyle(.red)
                    .textSelection(.enabled)
            } else if let snapshot = store.snapshot {
                Text("\(snapshot.source.deviceName ?? "Overhead") · \(snapshot.demoLoop.completedMoves)/\(snapshot.demoLoop.totalMoves) moves · \(snapshot.demoLoop.status.replacingOccurrences(of: "_", with: " "))")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(16)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
    }
}

private struct ControlTile: View {
    let title: String
    let subtitle: String
    let systemImage: String
    let tint: Color

    var body: some View {
        HStack(spacing: 14) {
            Image(systemName: systemImage)
                .font(.system(size: 24, weight: .semibold))
                .foregroundStyle(tint)
                .frame(width: 34)
            VStack(alignment: .leading, spacing: 4) {
                Text(title).font(.headline)
                Text(subtitle)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.leading)
            }
            Spacer(minLength: 0)
        }
        .padding(17)
        .frame(maxWidth: .infinity, minHeight: 92, alignment: .leading)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .strokeBorder(tint.opacity(0.24), lineWidth: 1)
        }
        .contentShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
    }
}
