import Foundation
import XCTest
@testable import Sim2ClawDemoControl

final class StudioClientTests: XCTestCase {
    func testSnapshotDecodesDemoReadinessAndProgress() throws {
        let data = Data(
            #"{"state":"OBSERVING","main_status":"executing","mode":"demo_physical","physical_authority":true,"source":{"ready":true,"device_name":"C922 Pro Stream Webcam","registration_state":"demo_visual_feedback"},"demo_loop":{"status":"running","action":"base_to_inverse","current_move":"c2_to_c1","completed_moves":1,"total_moves":6,"ready":true,"physical_authority":true,"error":null}}"#.utf8
        )
        let snapshot = try JSONDecoder().decode(StudioSnapshot.self, from: data)
        XCTAssertTrue(snapshot.physicalAuthority)
        XCTAssertEqual(snapshot.source.registrationState, "demo_visual_feedback")
        XCTAssertEqual(snapshot.demoLoop.currentMove, "c2_to_c1")
        XCTAssertEqual(snapshot.demoLoop.completedMoves, 1)
        XCTAssertEqual(snapshot.demoLoop.totalMoves, 6)
        XCTAssertTrue(snapshot.demoLoop.isRunning)
    }

    func testFourButtonCommandsHaveStableControllerActions() {
        XCTAssertEqual(DemoAction.baseToInverse.rawValue, "base_to_inverse")
        XCTAssertEqual(DemoAction.inverseToBase.rawValue, "inverse_to_base")
        XCTAssertEqual(DemoAction.loop.rawValue, "loop")
        XCTAssertEqual(DemoAction.allCases.count, 3)
    }
}
