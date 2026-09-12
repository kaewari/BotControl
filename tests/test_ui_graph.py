"""Unit tests for UI State Graph & Fast Route Planning Module."""
import os
import re
import tempfile
import time
import unittest
import numpy as np

from bot.core.coordinates import Point, BoundingBox
from bot.core.resource_guard import ResourceGuard, CONFIRMATION_ZONE
from bot.core.ui_graph import (
    UIStateGraph,
    UINode,
    UIEdge,
    compute_dhash,
    hamming_distance,
    STANDARD_NODES,
    STANDARD_EDGES,
)
from tests.mock_wda import MockDeviceManager


class TestUIGraph(unittest.TestCase):

    def setUp(self):
        self.temp_file = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self.temp_file.close()
        self.graph = UIStateGraph(filepath=self.temp_file.name)

    def tearDown(self):
        if os.path.exists(self.temp_file.name):
            try:
                os.remove(self.temp_file.name)
            except Exception:
                pass

    def test_standard_nodes_initialization(self):
        """Tests that baseline graph initializes with all 6 required standard screens."""
        expected_nodes = {
            "Overworld",
            "PhoneMenu",
            "Guidebook",
            "SurvivalIndex",
            "DivergentUniverse",
            "Battle",
        }
        self.assertTrue(expected_nodes.issubset(set(self.graph.nodes.keys())))
        for nid in expected_nodes:
            node = self.graph.nodes[nid]
            self.assertEqual(node.node_id, nid)
            self.assertTrue(len(node.name) > 0)
            self.assertTrue(isinstance(node.anchor_texts, list))

    def test_node_and_edge_serialization(self):
        """Tests UINode and UIEdge to_dict and from_dict conversions."""
        node = UINode(
            node_id="CustomScreen",
            name="Màn hình thử nghiệm",
            anchor_texts=["Thử nghiệm", "Test"],
            visual_fingerprint="abcdef0123456789",
            metadata={"test_key": 42},
        )
        d = node.to_dict()
        reconstructed_node = UINode.from_dict(d)
        self.assertEqual(node.node_id, reconstructed_node.node_id)
        self.assertEqual(node.name, reconstructed_node.name)
        self.assertEqual(node.anchor_texts, reconstructed_node.anchor_texts)
        self.assertEqual(node.visual_fingerprint, reconstructed_node.visual_fingerprint)
        self.assertEqual(node.metadata, reconstructed_node.metadata)

        edge = UIEdge(
            from_node="A",
            to_node="B",
            action_type="tap",
            x=0.5,
            y=0.6,
            box=BoundingBox(0.4, 0.5, 0.6, 0.7),
            label="Chuyển A sang B",
            cost=1.5,
            post_wait=0.4,
            element_key="elem_a_b",
        )
        ed = edge.to_dict()
        reconstructed_edge = UIEdge.from_dict(ed)
        self.assertEqual(edge.from_node, reconstructed_edge.from_node)
        self.assertEqual(edge.to_node, reconstructed_edge.to_node)
        self.assertEqual(edge.action_type, reconstructed_edge.action_type)
        self.assertAlmostEqual(edge.x, reconstructed_edge.x, places=4)
        self.assertAlmostEqual(edge.y, reconstructed_edge.y, places=4)
        self.assertIsNotNone(reconstructed_edge.box)
        self.assertAlmostEqual(reconstructed_edge.box.x1, 0.4, places=4)
        self.assertEqual(edge.label, reconstructed_edge.label)
        self.assertEqual(edge.cost, reconstructed_edge.cost)
        self.assertEqual(edge.post_wait, reconstructed_edge.post_wait)
        self.assertEqual(edge.element_key, reconstructed_edge.element_key)

    def test_disk_load_latency_benchmark(self):
        """Tests that loading graph from disk takes < 20ms (Acceptance Criteria)."""
        self.graph.save()
        load_times = []
        for _ in range(50):
            t0 = time.perf_counter()
            self.graph.load()
            load_times.append((time.perf_counter() - t0) * 1000.0)

        min_time = min(load_times)
        avg_time = sum(load_times) / len(load_times)
        max_time = max(load_times)
        self.assertLess(avg_time, 20.0, f"Average load time too slow: {avg_time:.2f}ms")
        self.assertLess(max_time, 20.0, f"Max load time too slow: {max_time:.2f}ms")

    def test_shortest_path_routing(self):
        """Tests shortest path calculation between core screens."""
        # 1. Overworld -> DivergentUniverse should route: Overworld -> Guidebook -> DivergentUniverse
        path = self.graph.find_shortest_path("Overworld", "DivergentUniverse")
        self.assertIsNotNone(path)
        self.assertEqual(len(path), 2)
        self.assertEqual(path[0].from_node, "Overworld")
        self.assertEqual(path[0].to_node, "Guidebook")
        self.assertEqual(path[1].from_node, "Guidebook")
        self.assertEqual(path[1].to_node, "DivergentUniverse")

        # 2. Overworld -> SurvivalIndex: Overworld -> Guidebook -> SurvivalIndex
        path_si = self.graph.find_shortest_path("Overworld", "SurvivalIndex")
        self.assertIsNotNone(path_si)
        self.assertEqual(len(path_si), 2)
        self.assertEqual(path_si[0].to_node, "Guidebook")
        self.assertEqual(path_si[1].to_node, "SurvivalIndex")

        # 3. Direct transition: Overworld -> PhoneMenu
        path_pm = self.graph.find_shortest_path("Overworld", "PhoneMenu")
        self.assertIsNotNone(path_pm)
        self.assertEqual(len(path_pm), 1)
        self.assertEqual(path_pm[0].to_node, "PhoneMenu")

        # 4. Multi-hop: PhoneMenu -> DivergentUniverse (PhoneMenu -> Overworld -> Guidebook -> DivergentUniverse)
        path_pm_du = self.graph.find_shortest_path("PhoneMenu", "DivergentUniverse")
        self.assertIsNotNone(path_pm_du)
        self.assertEqual(len(path_pm_du), 3)
        self.assertEqual([e.to_node for e in path_pm_du], ["Overworld", "Guidebook", "DivergentUniverse"])

    def test_pathfinding_latency_benchmark(self):
        """Tests that route planning executes in < 5ms (Acceptance Criteria)."""
        times = []
        for _ in range(1000):
            t0 = time.perf_counter()
            self.graph.find_shortest_path("PhoneMenu", "DivergentUniverse")
            times.append((time.perf_counter() - t0) * 1000.0)

        avg_time = sum(times) / len(times)
        max_time = max(times)
        self.assertLess(avg_time, 1.0, f"Average pathfinding too slow: {avg_time:.4f}ms")
        self.assertLess(max_time, 5.0, f"Max pathfinding took >= 5ms: {max_time:.4f}ms")

    def test_pathfinding_edge_cases(self):
        """Tests pathfinding edge cases: same source/destination, unreachable target, invalid nodes."""
        # 1. Source == Destination
        path = self.graph.find_shortest_path("Overworld", "Overworld")
        self.assertEqual(path, [])

        # 2. Invalid source or destination
        self.assertIsNone(self.graph.find_shortest_path("NonExistent", "Overworld"))
        self.assertIsNone(self.graph.find_shortest_path("Overworld", "NonExistent"))

        # 3. Unreachable isolated node
        self.graph.add_node("IsolatedScreen", "Màn hình cô lập")
        path_isolated = self.graph.find_shortest_path("Overworld", "IsolatedScreen")
        self.assertIsNone(path_isolated)

    def test_dynamic_node_and_edge_modification(self):
        """Tests adding and removing nodes and edges dynamically."""
        # 1. Add new node and connect edge
        self.graph.add_node("EventBanner", "Sự Kiện Giới Hạn", anchor_texts=["Bước Nhảy Sự Kiện"])
        self.assertIn("EventBanner", self.graph.nodes)

        edge = self.graph.add_edge(
            from_node="Overworld",
            to_node="EventBanner",
            action_type="tap",
            x=0.88,
            y=0.12,
            label="Mở Banner Sự Kiện",
        )
        self.assertIn("EventBanner", [e.to_node for e in self.graph.adjacency["Overworld"]])

        # Verify new shortest route exists
        path = self.graph.find_shortest_path("Overworld", "EventBanner")
        self.assertIsNotNone(path)
        self.assertEqual(len(path), 1)
        self.assertEqual(path[0].to_node, "EventBanner")

        # 2. Remove edge
        removed_edge = self.graph.remove_edge("Overworld", "EventBanner")
        self.assertTrue(removed_edge)
        self.assertIsNone(self.graph.find_shortest_path("Overworld", "EventBanner"))

        # 3. Remove node
        removed_node = self.graph.remove_node("EventBanner")
        self.assertTrue(removed_node)
        self.assertNotIn("EventBanner", self.graph.nodes)

    def test_visual_fingerprint_and_dhash(self):
        """Tests visual perceptual fingerprint generation and Hamming distance comparison."""
        img1 = np.ones((600, 800, 3), dtype=np.uint8) * 128
        img2 = img1.copy()
        img2[100:200, 100:200] = 0  # slight variation

        h1 = compute_dhash(img1)
        h2 = compute_dhash(img2)
        self.assertTrue(len(h1) > 0)
        self.assertTrue(len(h2) > 0)

        # Identical images have 0 Hamming distance
        self.assertEqual(hamming_distance(h1, h1), 0)

        # Very different image
        img_noisy = np.random.randint(0, 256, (600, 800, 3), dtype=np.uint8)
        h_noisy = compute_dhash(img_noisy)
        self.assertGreater(hamming_distance(h1, h_noisy), 0)

    def test_screen_classification(self):
        """Tests screen classification via anchor texts and visual fingerprints."""
        # 1. Anchor text classification for Guidebook
        texts = ["Huấn Luyện Thường Ngày", "Hướng Dẫn Sinh Tồn", "Điểm Năng Động: 400/500"]
        classified, conf = self.graph.classify_screen(ocr_texts=texts)
        self.assertEqual(classified, "Guidebook")
        self.assertGreater(conf, 0.5)

        # 2. Anchor text classification for PhoneMenu
        pm_texts = ["Ủy Thác", "Tin Nhắn", "Cài Đặt"]
        classified_pm, conf_pm = self.graph.classify_screen(ocr_texts=pm_texts)
        self.assertEqual(classified_pm, "PhoneMenu")
        self.assertGreater(conf_pm, 0.5)

        # 3. Visual fingerprint classification
        frame = np.zeros((200, 300, 3), dtype=np.uint8)
        frame[50:150, 50:150] = (200, 50, 50)
        self.graph.register_node_fingerprint("Battle", frame)
        c_node, c_conf = self.graph.classify_screen(frame=frame)
        self.assertEqual(c_node, "Battle")
        self.assertGreaterEqual(c_conf, 0.8)

    def test_safe_navigation_execution(self):
        """Tests complete end-to-end multi-step navigation along UI State Graph with MockDevice."""
        device = MockDeviceManager()
        self.graph.device = device

        # Navigate Overworld -> DivergentUniverse (Overworld -> Guidebook -> DivergentUniverse)
        success = self.graph.navigate("Overworld", "DivergentUniverse", device=device)
        self.assertTrue(success)
        self.assertEqual(len(device.tap_history), 2)
        labels = [t["label"] for t in device.tap_history]
        self.assertEqual(labels, ["Mở Sổ Tay", "Tab Vũ Trụ Mô Phỏng"])

    def test_resource_guard_zero_spend_guarantee(self):
        """Confirms ResourceGuard blocks 100% of dangerous confirmation taps and halts navigation."""
        device = MockDeviceManager()
        guard = ResourceGuard(device=device)
        device.resource_guard = guard

        # Add an adversarial transition that attempts to click 'Xác Nhận' in CONFIRMATION_ZONE
        self.graph.add_edge(
            from_node="Guidebook",
            to_node="SpendJadePrompt",
            action_type="tap",
            x=CONFIRMATION_ZONE.center.x,
            y=CONFIRMATION_ZONE.center.y,
            box=CONFIRMATION_ZONE,
            label="Xác Nhận Mua Vé",
        )

        device.clear_history()
        # Attempt to navigate into SpendJadePrompt
        success = self.graph.navigate(
            "Guidebook",
            "SpendJadePrompt",
            device=device,
            resource_guard=guard,
        )

        # Must fail and dispatch 0 taps
        self.assertFalse(success, "ResourceGuard must reject dangerous route")
        self.assertEqual(len(device.tap_history), 0, "No tap should have been sent to device")
        self.assertGreaterEqual(len(guard.security_violations), 1)

    def test_swipe_edge_navigation(self):
        """Tests that edges with action_type='swipe' execute swipe gestures instead of taps."""
        device = MockDeviceManager()
        self.graph.add_node("Page1")
        self.graph.add_node("Page2")
        self.graph.add_edge(
            from_node="Page1",
            to_node="Page2",
            action_type="swipe",
            x=0.5,
            y=0.8,
            swipe_end_x=0.5,
            swipe_end_y=0.2,
            label="Vuốt chuyển trang",
        )

        device.clear_history()
        success = self.graph.navigate("Page1", "Page2", device=device)
        self.assertTrue(success)
        self.assertEqual(len(device.tap_history), 0)
        self.assertEqual(len(device.swipe_history), 1)
        swipe = device.swipe_history[0]
        self.assertAlmostEqual(swipe["x1"], 0.5, places=2)
        self.assertAlmostEqual(swipe["y1"], 0.8, places=2)
        self.assertAlmostEqual(swipe["x2"], 0.5, places=2)
        self.assertAlmostEqual(swipe["y2"], 0.2, places=2)

    def test_dry_run_cached_element_veto(self):
        """Verifies dry_run detects and blocks dangerous coordinates when updated via UICoordinateCache."""
        from bot.core.cache import ui_cache, UIElement
        original_elem = ui_cache.elements.get("danger_cached_btn")
        try:
            # Inject element in-memory without persisting to data/ui_cache.json
            ui_cache.elements["danger_cached_btn"] = UIElement(
                key="danger_cached_btn",
                x=CONFIRMATION_ZONE.center.x,
                y=CONFIRMATION_ZONE.center.y,
                label="Dangerous",
            )

            device = MockDeviceManager()
            guard = ResourceGuard(device=device)

            self.graph.add_node("ScreenA", auto_save=False)
            self.graph.add_node("ScreenB", auto_save=False)
            self.graph.add_edge(
                from_node="ScreenA",
                to_node="ScreenB",
                action_type="tap",
                x=0.1,  # Base coordinate is safe
                y=0.1,
                element_key="danger_cached_btn",  # Cached coordinate is dangerous
                label="SafeEdgeLabel",
                auto_save=False,
            )

            # dry_run must detect the threat through the cache and return False
            dry_run_res = self.graph.navigate("ScreenA", "ScreenB", device=device, resource_guard=guard, dry_run=True)
            self.assertFalse(dry_run_res, "dry_run must reject route when element_key resolves to CONFIRMATION_ZONE")
        finally:
            if original_elem is None:
                ui_cache.elements.pop("danger_cached_btn", None)
            else:
                ui_cache.elements["danger_cached_btn"] = original_elem
            ui_cache.elements.pop("dangerous_elem", None)

    def test_auto_screen_identification_navigation(self):
        """Tests that navigate(None, target) auto-identifies screen from frame and navigates."""
        import cv2
        device = MockDeviceManager()
        # Set real Guidebook frame into mock device
        img = cv2.imread("assets/screenshots/real_ipad_screen.png")
        if img is not None:
            device.set_frame(img)
            device.clear_history()

            success = self.graph.navigate(None, "DivergentUniverse", device=device)
            self.assertTrue(success)
            self.assertEqual(len(device.tap_history), 1)
            self.assertEqual(device.tap_history[0]["label"], "Tab Vũ Trụ Mô Phỏng")

    def test_concurrency_thread_safety(self):
        """Tests that concurrent graph mutations, traversals, and saves do not raise race conditions."""
        import threading
        errors = []

        def worker_add():
            for i in range(30):
                try:
                    self.graph.add_edge(from_node="Overworld", to_node=f"ConcNode_{i}", label=f"ConcL_{i}", auto_save=True)
                except Exception as e:
                    errors.append(e)

        def worker_save():
            for _ in range(30):
                try:
                    self.graph.save()
                except Exception as e:
                    errors.append(e)

        def worker_read():
            for _ in range(30):
                try:
                    self.graph.find_shortest_path("Overworld", "DivergentUniverse")
                    _ = [e.to_dict() for edges in self.graph.adjacency.values() for e in edges]
                except Exception as e:
                    errors.append(e)

        threads = [
            threading.Thread(target=worker_add),
            threading.Thread(target=worker_save),
            threading.Thread(target=worker_read),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0, f"Thread safety errors occurred: {errors}")

    def test_swipe_zero_spend_end_veto(self):
        """Verifies that swipe edges ending inside CONFIRMATION_ZONE are blocked by ResourceGuard."""
        device = MockDeviceManager()
        guard = ResourceGuard(device=device)
        self.graph.add_node("SafeScreenA", auto_save=False)
        self.graph.add_node("SafeScreenB", auto_save=False)
        self.graph.add_edge(
            from_node="SafeScreenA",
            to_node="SafeScreenB",
            action_type="swipe",
            x=0.10,
            y=0.10,
            swipe_end_x=CONFIRMATION_ZONE.center.x,
            swipe_end_y=CONFIRMATION_ZONE.center.y,
            label="BenignScrollUp",
            auto_save=False,
        )

        # 1. dry_run must block the swipe ending in confirmation zone
        dry_res = self.graph.navigate("SafeScreenA", "SafeScreenB", device=device, resource_guard=guard, dry_run=True)
        self.assertFalse(dry_res, "dry_run must reject route when swipe_end is in CONFIRMATION_ZONE")

        # 2. Live navigation must block and execute 0 swipes
        device.clear_history()
        live_res = self.graph.navigate("SafeScreenA", "SafeScreenB", device=device, resource_guard=guard, dry_run=False)
        self.assertFalse(live_res, "Live navigation must reject route when swipe_end is in CONFIRMATION_ZONE")
        self.assertEqual(len(device.swipe_history), 0, "No swipe should be dispatched into confirmation zone")

    def test_unexpected_overlay_modal_interruption_recovery(self):
        """Verifies closed-loop navigation handles and dismisses unexpected overlay modals mid-route."""
        device = MockDeviceManager()
        self.graph.add_node("ModalScreenA", auto_save=False)
        self.graph.add_node("ModalScreenB", auto_save=False)
        self.graph.add_node("ModalScreenC", auto_save=False)

        self.graph.add_edge(from_node="ModalScreenA", to_node="ModalScreenB", action_type="tap", x=0.2, y=0.2, label="GoToB", auto_save=False)
        self.graph.add_edge(from_node="ModalScreenB", to_node="ModalScreenC", action_type="tap", x=0.8, y=0.8, label="GoToC", auto_save=False)

        def make_texture(seed):
            rng = np.random.RandomState(seed)
            return rng.randint(0, 256, (200, 200, 3), dtype=np.uint8)

        frame_a = make_texture(101)
        frame_b = make_texture(202)
        frame_c = make_texture(303)
        frame_modal = make_texture(404)

        self.graph.register_node_fingerprint("ModalScreenA", frame_a, auto_save=False)
        self.graph.register_node_fingerprint("ModalScreenB", frame_b, auto_save=False)
        self.graph.register_node_fingerprint("ModalScreenC", frame_c, auto_save=False)

        device.set_frame(frame_a)

        real_tap_hold = device.tap_hold
        def mock_tap_hold_with_modal(x, y, **kwargs):
            label = kwargs.get("label", "")
            if label == "GoToB":
                # Unexpected modal appears after Step 1!
                device.set_frame(frame_modal)
            elif "Dialog" in label or "Đóng" in label or "Hủy" in label:
                # Modal dismissed!
                device.set_frame(frame_b)
            elif label == "GoToC":
                # Step 2 reached destination!
                device.set_frame(frame_c)
            real_tap_hold(x, y, **kwargs)

        device.tap_hold = mock_tap_hold_with_modal
        device.clear_history()

        success = self.graph.navigate("ModalScreenA", "ModalScreenC", device=device, verify_steps=True)
        self.assertTrue(success, "Navigation must recover from unexpected overlay modal and reach target")
        labels = [t["label"] for t in device.tap_history]
        self.assertIn("GoToB", labels)
        self.assertTrue(any("Dialog" in l or "Đóng" in l for l in labels), "Must tap close/dismiss on modal")
        self.assertIn("GoToC", labels)

    def test_dhash_single_channel_grayscale(self):
        """Tests that compute_dhash safely processes (H, W, 1) single-channel images."""
        img_single = np.zeros((100, 100, 1), dtype=np.uint8)
        img_single[20:60, 20:60, 0] = 255
        h = compute_dhash(img_single)
        self.assertTrue(len(h) > 0)
        self.assertEqual(len(h), 16)

    def test_empty_frame_does_not_wipe_fingerprint(self):
        """Verifies that passing an empty/corrupted frame does not erase existing fingerprints."""
        orig_fp = self.graph.nodes["Overworld"].visual_fingerprint
        self.assertTrue(len(orig_fp) > 0)
        self.graph.register_node_fingerprint("Overworld", np.zeros((0, 0, 3), dtype=np.uint8))
        self.assertEqual(self.graph.nodes["Overworld"].visual_fingerprint, orig_fp)

    def test_record_transition_and_auto_edge_discovery(self):
        """Tests recording and discovering new transitions between screens."""
        edge = self.graph.record_transition(
            from_node="Guidebook",
            to_node="PhoneMenu",
            action_type="tap",
            x=0.04,
            y=0.05,
            label="Phím tắt Menu",
            cost=1.0,
        )
        self.assertIsNotNone(edge)
        self.assertEqual(edge.from_node, "Guidebook")
        self.assertEqual(edge.to_node, "PhoneMenu")

        # Verify path finding now uses the new shortcut
        path = self.graph.find_shortest_path("Guidebook", "PhoneMenu")
        self.assertEqual(len(path), 1)
        self.assertEqual(path[0].label, "Phím tắt Menu")

    def test_max_reroutes_loop_prevention(self):
        """Verifies navigate terminates with False when oscillating diversion exceeds max_reroutes."""
        device = MockDeviceManager()
        self.graph.add_node("OscA", auto_save=False)
        self.graph.add_node("OscB", auto_save=False)
        self.graph.add_node("OscC", auto_save=False)
        self.graph.add_edge(from_node="OscA", to_node="OscB", label="AtoB", auto_save=False)
        self.graph.add_edge(from_node="OscB", to_node="OscC", label="BtoC", auto_save=False)

        frame_a = np.ones((100, 100, 3), dtype=np.uint8) * 50
        frame_b = np.ones((100, 100, 3), dtype=np.uint8) * 150
        self.graph.register_node_fingerprint("OscA", frame_a, auto_save=False)
        self.graph.register_node_fingerprint("OscB", frame_b, auto_save=False)

        # Oscillate between OscA and OscB indefinitely
        state = {"curr": "OscA"}
        def mock_tap_hold(x, y, **kwargs):
            state["curr"] = "OscA" if state["curr"] == "OscB" else "OscB"
            device.set_frame(frame_a if state["curr"] == "OscA" else frame_b)

        device.tap_hold = mock_tap_hold
        device.set_frame(frame_a)

        success = self.graph.navigate("OscA", "OscC", device=device, verify_steps=True, max_reroutes=3)
        self.assertFalse(success, "Navigation must abort when max_reroutes is exceeded")

    def test_expanded_standard_nodes_count_and_attributes(self):
        """Verifies expanded graph has >= 35 discrete nodes (now 56) with valid attributes."""
        self.assertGreaterEqual(len(STANDARD_NODES), 35)
        self.assertGreaterEqual(len(self.graph.nodes), 35)

        hex_pattern = re.compile(r"^[0-9a-fA-F]{16}$")
        seen_ids = set()

        for nd in STANDARD_NODES:
            nid = nd["node_id"]
            self.assertNotIn(nid, seen_ids, f"Duplicate node_id: {nid}")
            seen_ids.add(nid)

            # Vietnamese name
            self.assertTrue(len(nd["name"]) > 0, f"Empty name for {nid}")

            # Anchor texts with accented and unaccented variants
            anchors = nd["anchor_texts"]
            self.assertIsInstance(anchors, list)
            self.assertGreaterEqual(len(anchors), 2, f"Too few anchor texts for {nid}")

            # Visual fingerprint dHash (16 hex chars)
            fp = nd["visual_fingerprint"]
            self.assertTrue(bool(hex_pattern.match(fp)), f"Invalid dHash: {fp} for {nid}")

            # Category metadata
            meta = nd.get("metadata", {})
            self.assertIn("category", meta, f"Missing category metadata for {nid}")

    def test_zero_spend_resource_guard_all_standard_edges(self):
        """Confirms 100% of standard edges strictly avoid CONFIRMATION_ZONE and veto keywords."""
        cz = CONFIRMATION_ZONE
        veto_keywords = ["xac nhan", "dong y", "confirm", "agree", "ngoc anh sao", "ve tinh cau", "buoc nhay", "warp"]

        self.assertGreaterEqual(len(STANDARD_EDGES), 100)

        for ed in STANDARD_EDGES:
            fn, tn = ed["from_node"], ed["to_node"]
            px, py = ed["x"], ed["y"]

            # Target point must not lie in CONFIRMATION_ZONE
            self.assertFalse(
                cz.x1 <= px <= cz.x2 and cz.y1 <= py <= cz.y2,
                f"Edge {fn}->{tn} target ({px:.4f}, {py:.4f}) touches CONFIRMATION_ZONE!"
            )

            # Bounding box must not overlap CONFIRMATION_ZONE
            if "box" in ed and ed["box"]:
                bx1, by1, bx2, by2 = ed["box"]
                overlaps = not (bx2 < cz.x1 or bx1 > cz.x2 or by2 < cz.y1 or by1 > cz.y2)
                self.assertFalse(overlaps, f"Edge {fn}->{tn} box {ed['box']} overlaps CONFIRMATION_ZONE!")

            # Action label must not contain veto / gacha keywords
            lbl = ed.get("label", "").lower()
            for vkw in veto_keywords:
                self.assertNotIn(vkw, lbl, f"Edge {fn}->{tn} label '{lbl}' contains veto keyword '{vkw}'!")

    def test_dijkstra_and_bfs_reachability_all_content_modes(self):
        """Verifies Dijkstra and BFS find valid paths between Overworld and all content modes in < 5ms."""
        required_targets = [
            # Story
            "QuestLog", "NPCDialogue", "DialogueChoices", "DialogueSkipConfirm", "Cutscene", "StoryRewardModal",
            # Puzzles & Exploration
            "CompassPuzzle", "ClockworkDial", "AbacusCircuitry", "LaserReflectorPuzzle", "DreamTickerPuzzle",
            "TreasureChestPopup", "MapMinigameHanu", "MapMinigameOrigami",
            # SU / DU
            "DivergentUniverse", "SUClassicDashboard", "SUDifficultySelect", "SUDomainMap", "SUOverworldRoom",
            "SUBlessingSelect", "SUCurioSelect", "DUEquationSelect", "SUOccurrenceDialog", "SURunTally",
            "DUSynchronicityTree", "SUAbilityTree",
            # Resin Farming
            "Farming_CalyxGolden", "Farming_CalyxCrimson", "Farming_CavernOfCorrosion", "Farming_StagnantShadow",
            "Farming_EchoOfWar", "Farming_PlanarOrnament", "DungeonDetailModal", "ResinReplenishModal",
            "TeamFormation", "BattleResult",
            # End-game Modes
            "EndGameHub", "MoC_StageSelect", "PF_StageSelect", "PF_BuffSelection", "AS_StageSelect",
            "AS_BuffSelection", "EndGame_TeamFormation", "EndGame_Battle_Node1", "EndGame_Battle_Node2",
            "EndGame_BattleResult",
            # Daily & Phone Routines
            "DailyTraining", "Assignments", "PhoneMessages", "DailyCheckinModal", "GameSettings"
        ]

        for target in required_targets:
            # Dijkstra pathfinding and latency
            t0 = time.perf_counter()
            path_dijkstra = self.graph.find_shortest_path("Overworld", target, algorithm="dijkstra")
            lat_dijkstra = (time.perf_counter() - t0) * 1000.0
            self.assertIsNotNone(path_dijkstra, f"Overworld -> {target} unreachable via Dijkstra!")
            self.assertLess(lat_dijkstra, 5.0, f"Dijkstra to {target} took {lat_dijkstra:.2f}ms >= 5ms!")

            # BFS pathfinding and latency
            t0 = time.perf_counter()
            path_bfs = self.graph.find_shortest_path("Overworld", target, algorithm="bfs")
            lat_bfs = (time.perf_counter() - t0) * 1000.0
            self.assertIsNotNone(path_bfs, f"Overworld -> {target} unreachable via BFS!")
            self.assertLess(lat_bfs, 5.0, f"BFS to {target} took {lat_bfs:.2f}ms >= 5ms!")

            # Return path to Overworld
            ret_dijkstra = self.graph.find_shortest_path(target, "Overworld", algorithm="dijkstra")
            self.assertIsNotNone(ret_dijkstra, f"{target} -> Overworld unreachable via Dijkstra!")

    def test_atomic_disk_save_and_load_latencies(self):
        """Verifies graph save and load execution latencies are < 20ms with 56 nodes."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
            temp_path = tf.name

        try:
            # Benchmark save latency
            save_times = []
            for _ in range(20):
                t0 = time.perf_counter()
                dur = self.graph.save(temp_path)
                save_times.append((time.perf_counter() - t0) * 1000.0)
                self.assertIsInstance(dur, float)
                self.assertGreater(dur, 0.0)

            avg_save = sum(save_times) / len(save_times)
            max_save = max(save_times)
            self.assertLess(avg_save, 20.0, f"Avg save latency too slow: {avg_save:.2f}ms")
            self.assertLess(max_save, 20.0, f"Max save latency too slow: {max_save:.2f}ms")

            # Benchmark load latency
            load_times = []
            for _ in range(20):
                t0 = time.perf_counter()
                self.graph.load(temp_path)
                load_times.append((time.perf_counter() - t0) * 1000.0)

            avg_load = sum(load_times) / len(load_times)
            max_load = max(load_times)
            self.assertLess(avg_load, 20.0, f"Avg load latency too slow: {avg_load:.2f}ms")
            self.assertLess(max_load, 20.0, f"Max load latency too slow: {max_load:.2f}ms")

            self.assertGreaterEqual(len(self.graph.nodes), 56)
            self.assertGreaterEqual(self.graph.edge_count, 140)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_screen_classification_expanded_modes(self):
        """Verifies screen classification via OCR anchor texts and perceptual fingerprints."""
        # 1. MoC stage select via unaccented text
        classified, conf = self.graph.classify_screen(ocr_texts=["hoi uc hon don", "tang 12", "so vong tieu hao"])
        self.assertEqual(classified, "MoC_StageSelect")
        self.assertGreaterEqual(conf, 0.3)

        # 2. Compass puzzle via unaccented text
        classified, conf = self.graph.classify_screen(ocr_texts=["la ban thien cau", "xoay"])
        self.assertEqual(classified, "CompassPuzzle")
        self.assertGreaterEqual(conf, 0.3)

        # 3. Calyx Crimson via Vietnamese text
        classified, conf = self.graph.classify_screen(ocr_texts=["Đài Hoa Nhân Tạo (Đỏ)", "Hủy Diệt", "10/Đợt"])
        self.assertEqual(classified, "Farming_CalyxCrimson")
        self.assertGreaterEqual(conf, 0.3)

        # 4. Apocalyptic shadow
        classified, conf = self.graph.classify_screen(ocr_texts=["Ảo Ảnh Tận Thế", "Độ Khó 4", "Điểm Hành Động"])
        self.assertEqual(classified, "AS_StageSelect")
        self.assertGreaterEqual(conf, 0.3)

        # 5. Assignments via Vietnamese text
        classified, conf = self.graph.classify_screen(ocr_texts=["Quản Lý Ủy Thác", "Phái Lại Tất Cả", "Nhận Tất Cả"])
        self.assertEqual(classified, "Assignments")
        self.assertGreaterEqual(conf, 0.3)

        # 6. Perceptual dHash classification
        test_frame = np.zeros((128, 128, 3), dtype=np.uint8)
        test_frame[:, 64:] = 255
        self.graph.register_node_fingerprint("CompassPuzzle", test_frame, auto_save=False)
        c_node, c_conf = self.graph.classify_screen(frame=test_frame)
        self.assertEqual(c_node, "CompassPuzzle")
        self.assertGreaterEqual(c_conf, 0.8)


if __name__ == "__main__":
    unittest.main()
