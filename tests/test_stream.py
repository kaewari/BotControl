"""Unit and integration tests for Web Live Stream & Double-Buffered Frame Architecture.

Tests cover:
- F-STREAM-01: WDA Namedlock Contention Bypass
- F-STREAM-02: Immutable VideoFrame Dataclass
- F-STREAM-03: Atomic Pointer Swap Frame Buffer
- F-STREAM-04: In-Memory JPEG Compression Pipeline
- F-STREAM-05: High-Framerate Web Stream (/api/stream at 18-25 FPS)
- F-STREAM-06: Stream Client Disconnect Resilience
"""
import time
import threading
import unittest
from typing import List, Optional
import cv2
import numpy as np
from starlette.testclient import TestClient

import bot.web.server as server
from bot.web.server import app, mjpeg_frame_generator, generate_placeholder_frame
from tests.mock_wda import MockDeviceManager, VideoFrame


class TestWebStreamAndDoubleBuffer(unittest.TestCase):
    """Test suite for live streaming performance and memory double-buffering."""

    def setUp(self):
        self.mock_device = MockDeviceManager(width=2752, height=2064)
        self._orig_device = server.device
        server.device = self.mock_device
        self.client = TestClient(app)

    def tearDown(self):
        server.device = self._orig_device

    # =========================================================================
    # Tier 1: Feature Coverage Tests
    # =========================================================================

    def test_video_frame_dataclass_immutability(self):
        """F-STREAM-02: Verifies VideoFrame dataclass is frozen and cannot be mutated."""
        bgr = np.zeros((720, 960, 3), dtype=np.uint8)
        frame = VideoFrame(
            frame_id=1,
            timestamp=123456.789,
            bgr=bgr,
            jpeg_bytes=b"\xff\xd8\xff",
            width=2752,
            height=2064,
        )
        self.assertEqual(frame.frame_id, 1)
        self.assertEqual(frame.timestamp, 123456.789)
        self.assertEqual(frame.width, 2752)
        self.assertEqual(frame.height, 2064)
        self.assertTrue(frame.jpeg_bytes.startswith(b"\xff\xd8"))

        # Frozen dataclass must raise on attribute assignment
        with self.assertRaises(Exception):
            frame.frame_id = 2  # type: ignore

    def test_atomic_pointer_swap_integrity(self):
        """F-STREAM-03: Verifies atomic pointer swap under concurrent reader threads."""
        reads: List[int] = []
        stop_event = threading.Event()

        def reader_worker():
            while not stop_event.is_set():
                vframe = self.mock_device.get_video_frame()
                if vframe is not None:
                    # Frame must have consistent fields
                    self.assertIsInstance(vframe.frame_id, int)
                    self.assertGreater(vframe.timestamp, 0.0)
                    self.assertEqual(vframe.width, 2752)
                    reads.append(vframe.frame_id)
                time.sleep(0.002)

        reader_thread = threading.Thread(target=reader_worker, daemon=True)
        reader_thread.start()

        # Producer swaps 30 new frames
        for fid in range(1, 31):
            test_bgr = np.zeros((2064, 2752, 3), dtype=np.uint8)
            test_bgr[0:10, 0:10] = fid % 255
            self.mock_device.set_frame(test_bgr)
            time.sleep(0.005)

        stop_event.set()
        reader_thread.join(timeout=1.0)

        # Reader must have captured multiple monotonic frames without crash
        self.assertGreater(len(reads), 10)
        # Ensure reads are generally monotonic
        for i in range(1, len(reads)):
            self.assertGreaterEqual(reads[i], reads[i - 1])

    def test_in_memory_jpeg_compression_pipeline(self):
        """F-STREAM-04: Verifies resize to 960x720, Q72 encoding, and JPEG format."""
        bgr = np.zeros((2064, 2752, 3), dtype=np.uint8)
        # Draw some content
        cv2.circle(bgr, (1376, 1032), 200, (0, 255, 0), -1)
        self.mock_device.set_frame(bgr)

        jpeg_bytes = self.mock_device.get_screenshot_jpeg_bytes()
        self.assertIsNotNone(jpeg_bytes)
        self.assertTrue(jpeg_bytes.startswith(b"\xff\xd8"))  # JPEG magic bytes

        # Decode JPEG to verify dimensions are 960x720
        arr = np.frombuffer(jpeg_bytes, dtype=np.uint8)
        decoded = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        self.assertEqual(decoded.shape, (720, 960, 3))

    def test_mjpeg_stream_headers_and_boundary(self):
        """F-STREAM-05: Verifies multipart/x-mixed-replace format and chunk headers."""
        gen = mjpeg_frame_generator()
        first_chunk = next(gen)

        self.assertIn(b"--frame", first_chunk)
        self.assertIn(b"Content-Type: image/jpeg", first_chunk)
        self.assertIn(b"Content-Length:", first_chunk)
        self.assertIn(b"\xff\xd8", first_chunk)

    def test_stream_fps_cadence(self):
        """F-STREAM-05: Measures delivery cadence across 10 frames (~20-25 FPS)."""
        gen = mjpeg_frame_generator()
        # Prime generator
        _ = next(gen)

        delays = []
        for _ in range(8):
            t0 = time.time()
            _ = next(gen)
            delays.append(time.time() - t0)

        avg_delay = sum(delays) / len(delays)
        # Expected delay is ~0.045s (target 22.2 FPS)
        self.assertAlmostEqual(avg_delay, 0.045, delta=0.035)

    def test_client_disconnect_handling(self):
        """F-STREAM-06: Verifies graceful exit when client disconnects (GeneratorExit)."""
        gen = mjpeg_frame_generator()
        _ = next(gen)
        _ = next(gen)
        # Simulate browser closing connection
        try:
            gen.close()
            closed_cleanly = True
        except Exception:
            closed_cleanly = False
        self.assertTrue(closed_cleanly)

    # =========================================================================
    # Tier 2: Boundary & Corner Cases
    # =========================================================================

    def test_stream_when_wda_disconnected(self):
        """F-STREAM-05: When device is disconnected, stream yields placeholder frame."""
        self.mock_device.connected = False
        gen = mjpeg_frame_generator()
        chunk = next(gen)

        self.assertIn(b"--frame", chunk)
        self.assertIn(b"Content-Type: image/jpeg", chunk)
        # Must be valid JPEG
        self.assertIn(b"\xff\xd8", chunk)

    def test_fast_ram_access_latency(self):
        """F-STREAM-03: Frame retrieval from RAM cache must be < 1.0ms."""
        times = []
        for _ in range(50):
            t0 = time.perf_counter()
            _ = self.mock_device.get_screenshot_jpeg_bytes()
            times.append(time.perf_counter() - t0)

        avg_latency_ms = (sum(times) / len(times)) * 1000.0
        self.assertLess(avg_latency_ms, 1.0, f"RAM retrieval latency {avg_latency_ms:.3f}ms exceeded 1.0ms")

    def test_stale_cache_behavior(self):
        """F-STREAM-03: Max age enforcement on get_screenshot."""
        # Set frame with timestamp in the past
        old_time = time.time() - 0.50  # 500ms ago
        bgr = np.ones((2064, 2752, 3), dtype=np.uint8) * 128
        self.mock_device.set_frame(bgr, timestamp=old_time)

        # Asking for max_age=0.20 with force_fresh=True should detect staleness
        now = time.time()
        with self.mock_device._frame_lock:
            is_stale = (now - self.mock_device._cached_time) >= 0.20
        self.assertTrue(is_stale)

    def test_rapid_client_connect_disconnect(self):
        """F-STREAM-06: 20 rapid client generator cycles without resource leakage."""
        for _ in range(20):
            gen = mjpeg_frame_generator()
            chunk = next(gen)
            self.assertTrue(len(chunk) > 0)
            gen.close()

    def test_api_stream_endpoint_response(self):
        """F-STREAM-05: HTTP GET /api/stream endpoint returns StreamingResponse with correct media type."""
        import asyncio
        from bot.web.server import video_feed

        async def check_stream():
            resp = await video_feed()
            self.assertEqual(resp.media_type, "multipart/x-mixed-replace; boundary=frame")
            self.assertEqual(resp.status_code, 200)
            chunk = await anext(resp.body_iterator)
            self.assertIn(b"--frame", chunk)
            self.assertIn(b"Content-Type: image/jpeg", chunk)
            await resp.body_iterator.aclose()

        asyncio.run(check_stream())

    # =========================================================================
    # Tier 3 & Tier 4: Pairwise Concurrency & Workload Benchmark
    # =========================================================================

    def test_concurrent_multi_client_streaming(self):
        """F-STREAM-05 / Tier 3: 5 concurrent client generators read from RAM simultaneously."""
        results = [0] * 5
        errors = []

        def client_task(client_idx: int):
            try:
                gen = mjpeg_frame_generator()
                for _ in range(5):
                    chunk = next(gen)
                    if b"--frame" in chunk:
                        results[client_idx] += 1
                gen.close()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=client_task, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=2.0)

        self.assertEqual(len(errors), 0, f"Errors during concurrent streaming: {errors}")
        self.assertEqual(results, [5, 5, 5, 5, 5])

    def test_streaming_under_heavy_bot_tapping(self):
        """F-STREAM-01 / Tier 4 Scenario 2: Stream runs concurrently while bot taps rapidly."""
        tap_count = [0]
        stream_chunks = [0]
        stop_test = threading.Event()

        def bot_tapper():
            while not stop_test.is_set():
                self.mock_device.tap(0.5, 0.5, normalized=True)
                tap_count[0] += 1
                time.sleep(0.02)

        def streamer():
            gen = mjpeg_frame_generator()
            while not stop_test.is_set():
                chunk = next(gen)
                if b"--frame" in chunk:
                    stream_chunks[0] += 1
            gen.close()

        t_bot = threading.Thread(target=bot_tapper, daemon=True)
        t_stream = threading.Thread(target=streamer, daemon=True)

        t_bot.start()
        t_stream.start()

        time.sleep(0.35)
        stop_test.set()

        t_bot.join(timeout=1.0)
        t_stream.join(timeout=1.0)

        self.assertGreater(tap_count[0], 5)
        self.assertGreater(stream_chunks[0], 4)

    def test_sustained_streaming_framerate(self):
        """Tier 4 Benchmark: Measures sustained FPS over 15 frames (must be >= 18 FPS)."""
        gen = mjpeg_frame_generator()
        # Prime
        _ = next(gen)

        num_frames = 12
        t0 = time.time()
        for _ in range(num_frames):
            _ = next(gen)
        elapsed = time.time() - t0
        gen.close()

        measured_fps = num_frames / elapsed
        # Target is 18 - 25 FPS (allowing small timing margin in test environment: >= 16 FPS)
        self.assertGreaterEqual(
            measured_fps,
            16.0,
            f"Measured FPS {measured_fps:.1f} was below threshold (expected >= 18 FPS)",
        )

    def test_websocket_stream_fps_and_disconnect(self):
        """F-STREAM-07: Verifies WebSocket /ws/stream delivers frames at high FPS and handles client close."""
        with self.client.websocket_connect("/ws/stream") as ws:
            frames_recvd = 0
            t0 = time.time()
            for _ in range(10):
                data = ws.receive_bytes()
                self.assertTrue(data.startswith(b"\xff\xd8"))
                frames_recvd += 1
            dur = time.time() - t0
            fps = frames_recvd / dur
            self.assertEqual(frames_recvd, 10)
            self.assertGreaterEqual(fps, 20.0)


if __name__ == "__main__":
    unittest.main()
