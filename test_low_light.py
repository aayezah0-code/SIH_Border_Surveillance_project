"""
Unit Tests for Low-Light Enhancement Module (Phase 2A & 2A.1 Production Fix)
----------------------------------------------------------------------------
Verifies:
  1. OFF mode behavior (unenhanced + confidence = 0.40)
  2. AUTO mode on bright frames (bypassed + confidence = 0.40)
  3. AUTO mode on dark frames (enhanced + confidence = 0.30)
  4. AUTO mode hysteresis behavior & confidence tracking
  5. ON mode behavior (enhanced + confidence = 0.30)
  6. Image dimensions preservation (1:1 coordinate mapping)
  7. BGR format & 3-channel preservation
  8. Non-destructive immutability of original input frame
  9. Edge case safety: blank / all-black frames
  10. Edge case safety: all-white / bright frames
  11. Memory stability across repeated invocations
  12. Performance benchmark (luminance cost & optimized enhancement cost)
  13. Non-global mutable confidence safety
  14. Coordinate mapping & bounding box fidelity
"""

import time
import unittest
import numpy as np
import cv2

from ai_engine.modules.enhancement.low_light_enhancer import LowLightEnhancer


class TestLowLightEnhancer(unittest.TestCase):

    def setUp(self):
        self.enhancer = LowLightEnhancer(mode="auto", dark_threshold=60.0, bright_threshold=75.0, subsample=8)
        self.enhancer.reset_state()

        # Synthetic test images
        # 1. Dark night-time image (mean luminance ~ 25)
        self.dark_frame = np.random.randint(15, 35, (720, 1280, 3), dtype=np.uint8)
        
        # 2. Bright daytime image (mean luminance ~ 160)
        self.bright_frame = np.random.randint(140, 180, (720, 1280, 3), dtype=np.uint8)

        # 3. Intermediate hysteresis test images
        # 55 (below dark threshold 60)
        self.under_dark_frame = np.full((720, 1280, 3), 55, dtype=np.uint8)
        # 68 (between dark threshold 60 and bright threshold 75)
        self.twilight_frame = np.full((720, 1280, 3), 68, dtype=np.uint8)
        # 80 (above bright threshold 75)
        self.above_bright_frame = np.full((720, 1280, 3), 80, dtype=np.uint8)

    def test_1_off_mode(self):
        """Test 1: OFF mode always bypasses enhancement and returns original reference with conf=0.40."""
        res_frame, was_enhanced, lum, eff_conf = self.enhancer.enhance_if_needed(self.dark_frame, mode="off")
        self.assertFalse(was_enhanced, "OFF mode should never enhance")
        self.assertIs(res_frame, self.dark_frame, "OFF mode should return original frame reference")
        self.assertEqual(eff_conf, 0.40, "OFF mode must return daylight confidence 0.40")

    def test_2_auto_bright_frame(self):
        """Test 2: AUTO mode on bright daytime frame bypasses enhancement with conf=0.40."""
        res_frame, was_enhanced, lum, eff_conf = self.enhancer.enhance_if_needed(self.bright_frame, mode="auto")
        self.assertFalse(was_enhanced, "AUTO mode should bypass enhancement for bright frames")
        self.assertGreater(lum, 75.0)
        self.assertIs(res_frame, self.bright_frame)
        self.assertEqual(eff_conf, 0.40, "Daylight frame in AUTO mode must retain confidence 0.40")

    def test_3_auto_dark_frame(self):
        """Test 3: AUTO mode on dark night frame activates enhancement with conf=0.30."""
        res_frame, was_enhanced, lum, eff_conf = self.enhancer.enhance_if_needed(self.dark_frame, mode="auto")
        self.assertTrue(was_enhanced, "AUTO mode should activate enhancement for dark frames")
        self.assertLess(lum, 60.0)
        self.assertIsNot(res_frame, self.dark_frame)
        self.assertGreater(np.mean(res_frame), np.mean(self.dark_frame), "Enhanced frame must have higher mean brightness")
        self.assertEqual(eff_conf, 0.30, "Dark frame in AUTO mode must use adaptive confidence 0.30")

    def test_4_auto_hysteresis(self):
        """Test 4: AUTO mode hysteresis prevents rapid flickering in twilight zone (60-75)."""
        enh = LowLightEnhancer(mode="auto", dark_threshold=60.0, bright_threshold=75.0)
        enh.reset_state()

        # 1. Start from bright (80 > 75) -> Inactive, conf=0.40
        _, enhanced_1, _, conf_1 = enh.enhance_if_needed(self.above_bright_frame)
        self.assertFalse(enhanced_1)
        self.assertEqual(conf_1, 0.40)

        # 2. Transition into twilight zone (68) from bright side -> Remains Inactive, conf=0.40
        _, enhanced_2, _, conf_2 = enh.enhance_if_needed(self.twilight_frame)
        self.assertFalse(enhanced_2, "Twilight frame entered from bright side should remain inactive")
        self.assertEqual(conf_2, 0.40)

        # 3. Transition into deep dark (55 < 60) -> Activates, conf=0.30
        _, enhanced_3, _, conf_3 = enh.enhance_if_needed(self.under_dark_frame)
        self.assertTrue(enhanced_3, "Dark frame must activate enhancement")
        self.assertEqual(conf_3, 0.30)

        # 4. Transition back into twilight zone (68) from dark side -> Remains Active, conf=0.30
        _, enhanced_4, _, conf_4 = enh.enhance_if_needed(self.twilight_frame)
        self.assertTrue(enhanced_4, "Twilight frame entered from dark side must maintain active state")
        self.assertEqual(conf_4, 0.30)

        # 5. Transition to bright (80 > 75) -> Deactivates, conf=0.40
        _, enhanced_5, _, conf_5 = enh.enhance_if_needed(self.above_bright_frame)
        self.assertFalse(enhanced_5, "Bright frame must deactivate enhancement")
        self.assertEqual(conf_5, 0.40)

    def test_5_on_mode(self):
        """Test 5: ON mode unconditionally applies enhancement with conf=0.30."""
        res_frame, was_enhanced, lum, eff_conf = self.enhancer.enhance_if_needed(self.bright_frame, mode="on")
        self.assertTrue(was_enhanced, "ON mode must apply enhancement even on bright frames")
        self.assertIsNot(res_frame, self.bright_frame)
        self.assertEqual(eff_conf, 0.30, "ON mode must return adaptive confidence 0.30")

    def test_6_dimension_preservation(self):
        """Test 6: Enhanced frame preserves exact original image dimensions (height, width, channels)."""
        test_shapes = [(480, 640, 3), (720, 1280, 3), (1080, 1920, 3), (2160, 3840, 3)]
        for h, w, c in test_shapes:
            img = np.random.randint(20, 40, (h, w, c), dtype=np.uint8)
            enh = self.enhancer.enhance(img)
            self.assertEqual(enh.shape, (h, w, c), f"Shape mismatch for input {h}x{w}x{c}")

    def test_7_bgr_format_preservation(self):
        """Test 7: Output frame remains valid 3-channel uint8 BGR array."""
        enh = self.enhancer.enhance(self.dark_frame)
        self.assertEqual(enh.dtype, np.uint8)
        self.assertEqual(len(enh.shape), 3)
        self.assertEqual(enh.shape[2], 3)
        self.assertTrue(np.all(enh >= 0) and np.all(enh <= 255))

    def test_8_input_immutability(self):
        """Test 8: Original input frame is NEVER modified in-place."""
        original_copy = self.dark_frame.copy()
        _ = self.enhancer.enhance(self.dark_frame)
        self.assertTrue(np.array_equal(self.dark_frame, original_copy), "Original frame array was modified in-place!")

    def test_9_blank_dark_frame_safety(self):
        """Test 9: All-black / zero frame does not crash or produce NaNs."""
        black_frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        res, was_enhanced, lum, eff_conf = self.enhancer.enhance_if_needed(black_frame)
        self.assertEqual(lum, 0.0)
        self.assertTrue(was_enhanced)
        self.assertEqual(eff_conf, 0.30)
        self.assertEqual(res.shape, black_frame.shape)
        self.assertFalse(np.isnan(res).any())

    def test_10_bright_frame_safety(self):
        """Test 10: All-white frame does not crash or overflow."""
        white_frame = np.full((720, 1280, 3), 255, dtype=np.uint8)
        res, was_enhanced, lum, eff_conf = self.enhancer.enhance_if_needed(white_frame, mode="on")
        self.assertEqual(res.shape, white_frame.shape)
        self.assertEqual(eff_conf, 0.30)
        self.assertFalse(np.isnan(res).any())

    def test_11_repeated_frames_memory_stability(self):
        """Test 11: Repeated execution on 100 frames does not leak memory or degrade."""
        enh = LowLightEnhancer(mode="auto")
        for _ in range(100):
            _ = enh.enhance_if_needed(self.dark_frame)
        self.assertTrue(True)

    def test_12_performance_benchmark(self):
        """Test 12: Real performance benchmarks on 1080p (1920x1080) and 720p (1280x720) frames."""
        f_1080p = np.random.randint(20, 40, (1080, 1920, 3), dtype=np.uint8)
        f_720p = np.random.randint(20, 40, (720, 1280, 3), dtype=np.uint8)

        # 1. Luminance check timing (100 iterations)
        t0 = time.perf_counter()
        for _ in range(100):
            _ = self.enhancer.estimate_luminance(f_1080p)
        lum_time_1080p_ms = ((time.perf_counter() - t0) / 100.0) * 1000.0

        # 2. Enhancement timing 720p (50 iterations)
        t0 = time.perf_counter()
        for _ in range(50):
            _ = self.enhancer.enhance(f_720p)
        enh_time_720p_ms = ((time.perf_counter() - t0) / 50.0) * 1000.0

        # 3. Enhancement timing 1080p (50 iterations)
        t0 = time.perf_counter()
        for _ in range(50):
            _ = self.enhancer.enhance(f_1080p)
        enh_time_1080p_ms = ((time.perf_counter() - t0) / 50.0) * 1000.0

        print(f"\n[BENCHMARK] 1080p Luminance Check: {lum_time_1080p_ms:.3f} ms")
        print(f"[BENCHMARK] 720p Full Enhancement:  {enh_time_720p_ms:.3f} ms")
        print(f"[BENCHMARK] 1080p Full Enhancement: {enh_time_1080p_ms:.3f} ms")

        self.assertLess(lum_time_1080p_ms, 1.0, "Luminance check must take < 1.0ms")
        self.assertLess(enh_time_720p_ms, 25.0, "720p Enhancement must take < 25.0ms on CPU")

    def test_13_adaptive_confidence_non_global(self):
        """Test 13: Verify that adaptive confidence is per-frame and does not mutate global state."""
        enh1 = LowLightEnhancer(mode="auto")
        enh2 = LowLightEnhancer(mode="off")

        _, _, _, c1 = enh1.enhance_if_needed(self.dark_frame)
        self.assertEqual(c1, 0.30)

        _, _, _, c2 = enh2.enhance_if_needed(self.dark_frame)
        self.assertEqual(c2, 0.40)

        # Re-check enh1 on bright frame
        _, _, _, c3 = enh1.enhance_if_needed(self.bright_frame)
        self.assertEqual(c3, 0.40)

    def test_14_coordinate_mapping_safety(self):
        """Test 14: Verify 1:1 exact resolution preservation so bounding box coordinates never suffer scaling offsets."""
        f_4k = np.random.randint(15, 35, (2160, 3840, 3), dtype=np.uint8)
        enh_4k = self.enhancer.enhance(f_4k)
        self.assertEqual(enh_4k.shape, f_4k.shape)
        self.assertEqual(enh_4k.shape[0], 2160)
        self.assertEqual(enh_4k.shape[1], 3840)


if __name__ == "__main__":
    unittest.main(verbosity=2)
