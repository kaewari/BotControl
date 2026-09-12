"""Adversarial stress test suite for UI Graph routing, connectivity, and persistence.

Evaluates:
1. Graph connectivity: Complete two-way reachability between Overworld and all 56 nodes.
2. Latency stress: 1,000 Dijkstra queries and 1,000 BFS queries (< 5ms avg, p95, p99).
3. Persistence stress: 100 consecutive loads and 100 saves of bot/cache/ui_graph.json (< 20ms).
4. Edge cases & concurrency: Multithreaded routing, corrupt cache recovery, invalid inputs.
"""
import os
import json
import time
import random
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Tuple, Any

import numpy as np

from bot.core.ui_graph import UIStateGraph, UINode, UIEdge, DEFAULT_GRAPH_PATH
from bot.core.resource_guard import CONFIRMATION_ZONE


class TestGraphRoutingStress(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.graph_path = DEFAULT_GRAPH_PATH
        cls.graph = UIStateGraph(filepath=cls.graph_path)

    def test_01_graph_node_count(self):
        """Verify graph has exactly 56 nodes as specified."""
        self.assertEqual(len(self.graph.nodes), 56, f"Expected 56 nodes, found {len(self.graph.nodes)}")
        self.assertGreaterEqual(self.graph.edge_count, 140, f"Expected >= 140 edges, found {self.graph.edge_count}")

    def test_02_graph_connectivity_all_56_nodes(self):
        """Verify paths exist from Overworld to every node, and return paths exist from every node to Overworld."""
        all_nodes = sorted(list(self.graph.nodes.keys()))
        unreachable_from_overworld_dijkstra = []
        unreachable_to_overworld_dijkstra = []
        unreachable_from_overworld_bfs = []
        unreachable_to_overworld_bfs = []

        path_lengths_from_ow = {}
        path_lengths_to_ow = {}

        for nid in all_nodes:
            # Dijkstra Forward (Overworld -> Node)
            p_fw_d = self.graph.find_shortest_path("Overworld", nid, algorithm="dijkstra")
            if p_fw_d is None:
                unreachable_from_overworld_dijkstra.append(nid)
            else:
                path_lengths_from_ow[nid] = len(p_fw_d)
                # Verify path continuity
                if len(p_fw_d) > 0:
                    self.assertEqual(p_fw_d[0].from_node, "Overworld")
                    self.assertEqual(p_fw_d[-1].to_node, nid)
                    for i in range(len(p_fw_d) - 1):
                        self.assertEqual(p_fw_d[i].to_node, p_fw_d[i + 1].from_node)

            # BFS Forward (Overworld -> Node)
            p_fw_b = self.graph.find_shortest_path("Overworld", nid, algorithm="bfs")
            if p_fw_b is None:
                unreachable_from_overworld_bfs.append(nid)

            # Dijkstra Return (Node -> Overworld)
            p_rt_d = self.graph.find_shortest_path(nid, "Overworld", algorithm="dijkstra")
            if p_rt_d is None:
                unreachable_to_overworld_dijkstra.append(nid)
            else:
                path_lengths_to_ow[nid] = len(p_rt_d)
                # Verify path continuity
                if len(p_rt_d) > 0:
                    self.assertEqual(p_rt_d[0].from_node, nid)
                    self.assertEqual(p_rt_d[-1].to_node, "Overworld")
                    for i in range(len(p_rt_d) - 1):
                        self.assertEqual(p_rt_d[i].to_node, p_rt_d[i + 1].from_node)

            # BFS Return (Node -> Overworld)
            p_rt_b = self.graph.find_shortest_path(nid, "Overworld", algorithm="bfs")
            if p_rt_b is None:
                unreachable_to_overworld_bfs.append(nid)

        # Assert zero reachability failures
        self.assertEqual(
            unreachable_from_overworld_dijkstra,
            [],
            f"Nodes unreachable from Overworld (Dijkstra): {unreachable_from_overworld_dijkstra}"
        )
        self.assertEqual(
            unreachable_from_overworld_bfs,
            [],
            f"Nodes unreachable from Overworld (BFS): {unreachable_from_overworld_bfs}"
        )
        self.assertEqual(
            unreachable_to_overworld_dijkstra,
            [],
            f"Nodes cannot return to Overworld (Dijkstra): {unreachable_to_overworld_dijkstra}"
        )
        self.assertEqual(
            unreachable_to_overworld_bfs,
            [],
            f"Nodes cannot return to Overworld (BFS): {unreachable_to_overworld_bfs}"
        )

        max_fw_hops = max(path_lengths_from_ow.values())
        max_rt_hops = max(path_lengths_to_ow.values())
        print(f"\n[Connectivity] 56/56 nodes 100% reachable from & to Overworld.")
        print(f"[Connectivity] Max hops from Overworld: {max_fw_hops}, Max hops to Overworld: {max_rt_hops}")

    def test_03_dijkstra_latency_stress_1000_queries(self):
        """Execute 1,000 random Dijkstra queries. Assert avg latency < 5ms (and report p95/p99)."""
        nodes = list(self.graph.nodes.keys())
        random.seed(42)
        pairs = [(random.choice(nodes), random.choice(nodes)) for _ in range(1000)]

        latencies_ms = []
        for src, dst in pairs:
            t0 = time.perf_counter()
            path = self.graph.find_shortest_path(src, dst, algorithm="dijkstra")
            t1 = time.perf_counter()
            latencies_ms.append((t1 - t0) * 1000.0)
            if src == dst:
                self.assertEqual(path, [])
            elif path is not None:
                self.assertEqual(path[0].from_node, src)
                self.assertEqual(path[-1].to_node, dst)

        lat_arr = np.array(latencies_ms)
        avg_lat = float(np.mean(lat_arr))
        p50 = float(np.percentile(lat_arr, 50))
        p95 = float(np.percentile(lat_arr, 95))
        p99 = float(np.percentile(lat_arr, 99))
        max_lat = float(np.max(lat_arr))
        min_lat = float(np.min(lat_arr))

        print(f"\n[Dijkstra Stress (1000 queries)] Avg: {avg_lat:.4f}ms | p50: {p50:.4f}ms | p95: {p95:.4f}ms | p99: {p99:.4f}ms | Max: {max_lat:.4f}ms | Min: {min_lat:.4f}ms")

        self.assertLess(avg_lat, 5.0, f"Dijkstra average latency {avg_lat:.4f}ms >= 5.0ms requirement")
        self.assertLess(p95, 5.0, f"Dijkstra p95 latency {p95:.4f}ms >= 5.0ms")
        self.assertLess(p99, 5.0, f"Dijkstra p99 latency {p99:.4f}ms >= 5.0ms")

    def test_04_bfs_latency_stress_1000_queries(self):
        """Execute 1,000 random BFS queries. Assert avg latency < 5ms (and report p95/p99)."""
        nodes = list(self.graph.nodes.keys())
        random.seed(1337)
        pairs = [(random.choice(nodes), random.choice(nodes)) for _ in range(1000)]

        latencies_ms = []
        for src, dst in pairs:
            t0 = time.perf_counter()
            path = self.graph.find_shortest_path(src, dst, algorithm="bfs")
            t1 = time.perf_counter()
            latencies_ms.append((t1 - t0) * 1000.0)
            if src == dst:
                self.assertEqual(path, [])
            elif path is not None:
                self.assertEqual(path[0].from_node, src)
                self.assertEqual(path[-1].to_node, dst)

        lat_arr = np.array(latencies_ms)
        avg_lat = float(np.mean(lat_arr))
        p50 = float(np.percentile(lat_arr, 50))
        p95 = float(np.percentile(lat_arr, 95))
        p99 = float(np.percentile(lat_arr, 99))
        max_lat = float(np.max(lat_arr))
        min_lat = float(np.min(lat_arr))

        print(f"\n[BFS Stress (1000 queries)] Avg: {avg_lat:.4f}ms | p50: {p50:.4f}ms | p95: {p95:.4f}ms | p99: {p99:.4f}ms | Max: {max_lat:.4f}ms | Min: {min_lat:.4f}ms")

        self.assertLess(avg_lat, 5.0, f"BFS average latency {avg_lat:.4f}ms >= 5.0ms requirement")
        self.assertLess(p95, 5.0, f"BFS p95 latency {p95:.4f}ms >= 5.0ms")
        self.assertLess(p99, 5.0, f"BFS p99 latency {p99:.4f}ms >= 5.0ms")

    def test_05_persistence_stress_load_100_times(self):
        """Load bot/cache/ui_graph.json 100 times. Assert load latency < 20ms."""
        load_latencies_ms = []
        for i in range(100):
            t0 = time.perf_counter()
            ret_ms = self.graph.load(self.graph_path)
            t1 = time.perf_counter()
            elapsed_ms = (t1 - t0) * 1000.0
            load_latencies_ms.append(elapsed_ms)
            self.assertEqual(len(self.graph.nodes), 56)
            self.assertEqual(self.graph.edge_count, 145)

        lat_arr = np.array(load_latencies_ms)
        avg_lat = float(np.mean(lat_arr))
        p50 = float(np.percentile(lat_arr, 50))
        p95 = float(np.percentile(lat_arr, 95))
        p99 = float(np.percentile(lat_arr, 99))
        max_lat = float(np.max(lat_arr))
        min_lat = float(np.min(lat_arr))

        print(f"\n[Persistence Load 100x] Avg: {avg_lat:.4f}ms | p50: {p50:.4f}ms | p95: {p95:.4f}ms | p99: {p99:.4f}ms | Max: {max_lat:.4f}ms | Min: {min_lat:.4f}ms")

        self.assertLess(avg_lat, 20.0, f"Load average latency {avg_lat:.4f}ms >= 20.0ms requirement")
        self.assertLess(p95, 20.0, f"Load p95 latency {p95:.4f}ms >= 20.0ms")
        self.assertLess(p99, 20.0, f"Load p99 latency {p99:.4f}ms >= 20.0ms")

    def test_06_persistence_stress_save_100_times(self):
        """Save graph 100 times to temporary file. Assert save latency < 20ms."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp_file:
            tmp_save_path = tmp_file.name

        try:
            save_latencies_ms = []
            for i in range(100):
                t0 = time.perf_counter()
                self.graph.save(tmp_save_path)
                t1 = time.perf_counter()
                elapsed_ms = (t1 - t0) * 1000.0
                save_latencies_ms.append(elapsed_ms)

            lat_arr = np.array(save_latencies_ms)
            avg_lat = float(np.mean(lat_arr))
            p50 = float(np.percentile(lat_arr, 50))
            p95 = float(np.percentile(lat_arr, 95))
            p99 = float(np.percentile(lat_arr, 99))
            max_lat = float(np.max(lat_arr))
            min_lat = float(np.min(lat_arr))

            print(f"\n[Persistence Save 100x] Avg: {avg_lat:.4f}ms | p50: {p50:.4f}ms | p95: {p95:.4f}ms | p99: {p99:.4f}ms | Max: {max_lat:.4f}ms | Min: {min_lat:.4f}ms")

            self.assertLess(avg_lat, 20.0, f"Save average latency {avg_lat:.4f}ms >= 20.0ms requirement")
            self.assertLess(p95, 20.0, f"Save p95 latency {p95:.4f}ms >= 20.0ms")
            self.assertLess(p99, 20.0, f"Save p99 latency {p99:.4f}ms >= 20.0ms")

            # Verify integrity of saved JSON file after 100 saves
            with open(tmp_save_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.assertIn("nodes", data)
            self.assertIn("edges", data)
            self.assertEqual(len(data["nodes"]), 56)
            self.assertEqual(len(data["edges"]), 145)
        finally:
            if os.path.exists(tmp_save_path):
                os.remove(tmp_save_path)

    def test_07_adversarial_invalid_inputs(self):
        """Test routing behavior with non-existent nodes, invalid types, empty strings."""
        # Non-existent source
        res = self.graph.find_shortest_path("GhostNode_X", "Overworld")
        self.assertIsNone(res)

        # Non-existent target
        res = self.graph.find_shortest_path("Overworld", "GhostNode_Y")
        self.assertIsNone(res)

        # Both non-existent
        res = self.graph.find_shortest_path("Ghost_A", "Ghost_B")
        self.assertIsNone(res)

        # Empty strings
        res = self.graph.find_shortest_path("", "")
        self.assertIsNone(res)

    def test_08_multithreaded_concurrent_queries(self):
        """Stress test concurrency: 10 worker threads performing 100 Dijkstra and BFS queries simultaneously."""
        nodes = list(self.graph.nodes.keys())
        errors = []

        def worker_task(worker_id: int):
            try:
                rnd = random.Random(worker_id * 100)
                for _ in range(100):
                    src = rnd.choice(nodes)
                    dst = rnd.choice(nodes)
                    # Alternate Dijkstra and BFS
                    p1 = self.graph.find_shortest_path(src, dst, algorithm="dijkstra")
                    p2 = self.graph.find_shortest_path(src, dst, algorithm="bfs")
                    if src == dst:
                        assert p1 == [], "Expected empty path for src == dst"
                        assert p2 == [], "Expected empty path for src == dst"
            except Exception as e:
                errors.append((worker_id, e))

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(worker_task, i) for i in range(10)]
            for f in futures:
                f.result()

        self.assertEqual(errors, [], f"Thread worker encountered errors: {errors}")
        print("\n[Concurrency Stress] 10 threads x 200 queries (2,000 total) completed with 0 errors.")

    def test_09_corrupt_cache_graceful_recovery(self):
        """Adversarially corrupt cache file and verify UIStateGraph recovers default graph without crash."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            tmp.write(b"CORRUPT_NOT_JSON_DATA_!@#$%^&*()")
            tmp_path = tmp.name

        try:
            broken_graph = UIStateGraph(filepath=tmp_path)
            self.assertEqual(len(broken_graph.nodes), 56)
            self.assertEqual(broken_graph.edge_count, 145)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)


if __name__ == "__main__":
    unittest.main()
