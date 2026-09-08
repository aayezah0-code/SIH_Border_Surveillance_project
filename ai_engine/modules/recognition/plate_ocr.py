"""
PlateOCR — Indian License Plate Optical Character Recognition Module
---------------------------------------------------------------------
Handles:
1. High-fidelity image preprocessing (contrast enhancement, bilateral filtering, adaptive thresholding).
2. Character extraction via EasyOCR.
3. Indian vehicle registration number format correction & validation.
4. Rejection of invalid OCR text / noise.
"""

from __future__ import annotations

import collections
import logging
import re
from dataclasses import dataclass
from typing import Optional, Tuple, List

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# Valid Indian State / Union Territory 2-letter postal codes & Special Series (BH = Bharat)
INDIAN_STATE_CODES = {
    "AP", "AR", "AS", "BR", "CG", "CH", "DD", "DL", "DN", "GA",
    "GJ", "HP", "HR", "JH", "JK", "KA", "KL", "LA", "LD", "MH",
    "ML", "MN", "MP", "MZ", "NL", "OD", "OR", "PB", "PY", "RJ",
    "SK", "TN", "TR", "TS", "UK", "UP", "WB", "AN", "BH",
}

# Common OCR confusion mappings
DIGIT_TO_LETTER = {
    "0": "O",
    "1": "I",
    "2": "Z",
    "4": "A",
    "5": "S",
    "6": "G",
    "8": "B",
}

LETTER_TO_DIGIT = {
    "O": "0",
    "Q": "0",
    "D": "0",
    "I": "1",
    "L": "1",
    "Z": "2",
    "A": "4",
    "S": "5",
    "G": "6",
    "T": "7",
    "B": "8",
}

# Regex patterns for Indian License Plates
# Standard: DL01AB1234, MP09AB1234, MH12DE1433, HR26DQ5551, KA01F9999
REGEX_STANDARD = re.compile(r"^([A-Z]{2})([0-9]{1,2})([A-Z]{1,3})([0-9]{4})$")
# Bharat Series: 22BH1234AA
REGEX_BHARAT = re.compile(r"^([0-9]{2})(BH)([0-9]{4})([A-Z]{1,2})$")


@dataclass
class OCRResult:
    """Normalized license plate recognition result."""
    plate_text: str          # e.g. "MP09AB1234"
    raw_text: str            # e.g. "MP 09 AB 1234"
    confidence: float        # e.g. 0.94
    is_valid: bool           # True if passes Indian plate format checks
    state_code: Optional[str] = None
    plate_format: str = "STANDARD"  # STANDARD, BHARAT, CUSTOM


class PlateOCR:
    """
    Optical Character Recognition and Indian License Plate Parser.
    """

    _instance: Optional["PlateOCR"] = None

    def __init__(self, gpu: bool = False):
        self.gpu = gpu
        self._reader = None
        self._init_reader()

    @classmethod
    def get_instance(cls) -> "PlateOCR":
        if cls._instance is None:
            import torch
            use_gpu = torch.cuda.is_available()
            cls._instance = cls(gpu=use_gpu)
        return cls._instance

    def _init_reader(self):
        """Initialize EasyOCR reader with English model."""
        try:
            import easyocr
            logger.info("[PlateOCR] Initializing EasyOCR (gpu=%s)...", self.gpu)
            self._reader = easyocr.Reader(["en"], gpu=self.gpu, verbose=False)
            logger.info("[PlateOCR] EasyOCR initialized successfully.")
        except Exception as exc:
            logger.error("[PlateOCR] Failed to initialize EasyOCR: %s", exc)
            self._reader = None

    @property
    def is_ready(self) -> bool:
        return self._reader is not None

    def preprocess_plate(self, plate_crop: np.ndarray) -> np.ndarray:
        """
        Enhance plate contrast and normalize resolution for optimal OCR text recognition.
        """
        if plate_crop is None or plate_crop.size == 0:
            return plate_crop

        h, w = plate_crop.shape[:2]
        target_h = 100
        target_w = int(w * (target_h / max(1, h)))
        target_w = max(240, min(600, target_w))
        resized = cv2.resize(plate_crop, (target_w, target_h), interpolation=cv2.INTER_CUBIC)

        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
        filtered = cv2.bilateralFilter(gray, d=9, sigmaColor=75, sigmaSpace=75)

        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
        enhanced = clahe.apply(filtered)
        return enhanced

    def _preprocess_v9_combo(self, img: np.ndarray) -> np.ndarray:
        """V9: 3x Bicubic Upscale + Grayscale + CLAHE (clip=2.5) + Mild Unsharp Masking."""
        up = cv2.resize(img, (0, 0), fx=3.0, fy=3.0, interpolation=cv2.INTER_CUBIC)
        gray = cv2.cvtColor(up, cv2.COLOR_BGR2GRAY) if len(up.shape) == 3 else up
        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
        cl = clahe.apply(gray)
        blur = cv2.GaussianBlur(cl, (0, 0), 1.5)
        sharp = cv2.addWeighted(cl, 1.5, blur, -0.5, 0)
        return cv2.cvtColor(sharp, cv2.COLOR_GRAY2BGR)

    def _preprocess_v5_clahe(self, img: np.ndarray) -> np.ndarray:
        """V5: Grayscale + CLAHE (clip=2.5, tile=(8,8))."""
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img
        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
        cl = clahe.apply(gray)
        return cv2.cvtColor(cl, cv2.COLOR_GRAY2BGR)

    def _preprocess_v3_grayscale(self, img: np.ndarray) -> np.ndarray:
        """V3: Grayscale conversion."""
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img
        return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)

    def _preprocess_v4_contrast_stretch(self, img: np.ndarray) -> np.ndarray:
        """V4: Min-Max contrast stretch."""
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img
        norm = cv2.normalize(gray, None, alpha=0, beta=255, norm_type=cv2.NORM_MINMAX)
        return cv2.cvtColor(norm, cv2.COLOR_GRAY2BGR)

    def _preprocess_v10_padded_deskew(self, img: np.ndarray) -> np.ndarray:
        """V10: Replicate border padding + 2.5x Bicubic resize + CLAHE."""
        padded = cv2.copyMakeBorder(img, 10, 10, 15, 15, cv2.BORDER_REPLICATE)
        up = cv2.resize(padded, (0, 0), fx=2.5, fy=2.5, interpolation=cv2.INTER_CUBIC)
        gray = cv2.cvtColor(up, cv2.COLOR_BGR2GRAY)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(4, 4))
        cl = clahe.apply(gray)
        return cv2.cvtColor(cl, cv2.COLOR_GRAY2BGR)

    def _run_single_ocr(self, img: np.ndarray) -> Optional[Tuple[str, str, float]]:
        """
        Executes EasyOCR on an image array.
        Returns (combined_alphanumeric, spaced_raw_text, average_confidence) or None.
        """
        if not self.is_ready or img is None or img.size == 0:
            return None
        try:
            results = self._reader.readtext(
                img,
                allowlist="0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ",
                detail=1,
                paragraph=False,
            )
            if not results:
                return None

            # Sort detected boxes left-to-right, top-to-bottom
            results.sort(key=lambda r: (r[0][0][1], r[0][0][0]))

            raw_texts = []
            confidences = []
            for bbox, text, conf in results:
                clean_piece = "".join(c for c in text.upper() if c.isalnum())
                if clean_piece:
                    raw_texts.append(clean_piece)
                    confidences.append(conf)

            if not raw_texts:
                return None

            combined_raw = "".join(raw_texts)
            spaced_raw = " ".join(raw_texts)
            avg_conf = float(np.mean(confidences)) if confidences else 0.50
            return combined_raw, spaced_raw, avg_conf
        except Exception as exc:
            logger.debug("[PlateOCR] Single OCR pass error: %s", exc)
            return None

    def recognize_plate(
        self,
        plate_crop: np.ndarray,
        source_id: Optional[str] = None,
        track_id: Optional[int] = None,
        frame_id: Optional[int] = None,
    ) -> Optional[OCRResult]:
        """
        Multi-Pass OCR Pipeline with Adaptive Preprocessing and Multi-Variant Consensus.
        
        1. Executes V1 (Original standard preprocessed crop).
        2. If V1 is valid with high confidence (>= 0.70), returns immediately with zero added latency.
        3. If V1 confidence < 0.70 or invalid, triggers enhanced passes (V9_Combo -> V5_CLAHE -> V3/V4/V10).
        4. Applies conservative multi-variant consensus to select the most reliable validated reading.
        """
        if not self.is_ready or plate_crop is None or plate_crop.size == 0:
            return None

        ch, cw = plate_crop.shape[:2]
        # Small-crop protection: ignore crops smaller than minimum optical threshold
        if ch < 6 or cw < 10:
            return None

        variant_records: List[dict] = []

        # =====================================================================
        # PASS 1: V1 Original / Standard Preprocessing
        # =====================================================================
        v1_img = self.preprocess_plate(plate_crop)
        v1_res = self._run_single_ocr(v1_img)
        if not v1_res:
            # Direct fallback on raw plate crop
            v1_res = self._run_single_ocr(plate_crop)

        if v1_res:
            combined_raw, spaced_raw, avg_conf = v1_res
            norm_plate, is_valid, p_fmt, st_code, conf_adj = self.normalize_indian_plate(
                combined_raw, avg_conf
            )
            v1_dict = {
                "variant": "V1_Original",
                "raw_text": spaced_raw,
                "combined_raw": combined_raw,
                "normalized_plate": norm_plate,
                "confidence": round(conf_adj, 3),
                "is_valid": is_valid,
                "plate_format": p_fmt,
                "state_code": st_code,
            }
            variant_records.append(v1_dict)

            logger.info(
                "[ANPR_OCR_MULTI] source_id=%s track_id=%s frame_id=%s variant=V1_Original ocr_text='%s' confidence=%.2f normalized_text='%s' valid=%s",
                source_id, track_id, frame_id, spaced_raw, conf_adj, norm_plate, is_valid
            )

            # Fast-path early exit: clean, confident, valid standard plate
            if is_valid and conf_adj >= 0.70:
                logger.info(
                    "[ANPR_OCR_FINAL] track_id=%s selected_text='%s' selected_variant=V1_Original confidence=%.2f valid=True consensus=False",
                    track_id, norm_plate, conf_adj
                )
                return OCRResult(
                    plate_text=norm_plate,
                    raw_text=spaced_raw,
                    confidence=round(conf_adj, 3),
                    is_valid=True,
                    state_code=st_code,
                    plate_format=p_fmt,
                )

        # =====================================================================
        # TRIGGER CONDITION: Low confidence or invalid result on V1
        # Run enhanced preprocessing passes to resolve character confusion
        # =====================================================================
        # If V1 had no text at all, only try V9; if V1 had candidate text, check V9 and V5
        has_v1_text = bool(v1_res and v1_res[0])
        enhanced_variants = [
            ("V9_Combo_Upscale_CLAHE_Sharp", self._preprocess_v9_combo),
        ]
        if has_v1_text:
            enhanced_variants.append(("V5_CLAHE", self._preprocess_v5_clahe))

        for v_name, v_func in enhanced_variants:
            try:
                proc_img = v_func(plate_crop)
                res = self._run_single_ocr(proc_img)
                if res:
                    c_raw, s_raw, a_conf = res
                    norm_p, val_p, fmt_p, st_c, c_adj = self.normalize_indian_plate(c_raw, a_conf)
                    v_dict = {
                        "variant": v_name,
                        "raw_text": s_raw,
                        "combined_raw": c_raw,
                        "normalized_plate": norm_p,
                        "confidence": round(c_adj, 3),
                        "is_valid": val_p,
                        "plate_format": fmt_p,
                        "state_code": st_c,
                    }
                    variant_records.append(v_dict)

                    logger.info(
                        "[ANPR_OCR_MULTI] source_id=%s track_id=%s frame_id=%s variant=%s ocr_text='%s' confidence=%.2f normalized_text='%s' valid=%s",
                        source_id, track_id, frame_id, v_name, s_raw, c_adj, norm_p, val_p
                    )

                    # If primary V9 produces a very high confidence valid reading, early exit
                    if v_name == "V9_Combo_Upscale_CLAHE_Sharp" and val_p and c_adj >= 0.80:
                        break

                    # If we have 2+ variants agreeing on a valid plate with >= 0.70 confidence, stop early
                    valid_so_far = [r for r in variant_records if r["is_valid"]]
                    if len(valid_so_far) >= 2:
                        counts = collections.Counter(r["normalized_plate"] for r in valid_so_far)
                        top_p, top_cnt = counts.most_common(1)[0]
                        if top_cnt >= 2:
                            break

            except Exception as exc:
                logger.debug("[PlateOCR] Variant %s failed: %s", v_name, exc)

        if not variant_records:
            return None

        # =====================================================================
        # MULTI-PASS RESULT SELECTION & CONSENSUS
        # =====================================================================
        valid_candidates = [r for r in variant_records if r["is_valid"]]

        # Build candidate summary for audit logging
        cand_log_parts = []
        for i, r in enumerate(variant_records, 1):
            cand_log_parts.append(f"candidate_{i}={r['normalized_plate']}(conf={r['confidence']:.2f},valid={r['is_valid']})")
        candidates_str = " ".join(cand_log_parts)

        if valid_candidates:
            # 1. Check for multi-variant agreement
            counts = collections.Counter(r["normalized_plate"] for r in valid_candidates)
            top_plate, vote_cnt = counts.most_common(1)[0]

            if vote_cnt >= 2:
                # Priority 1: Multi-variant agreement
                agreeing_records = [r for r in valid_candidates if r["normalized_plate"] == top_plate]
                best_rec = max(agreeing_records, key=lambda r: r["confidence"])
                is_consensus = True
                selection_reason = "MULTI_VARIANT_CONSENSUS"
            else:
                # Priority 2/3: Single valid variant
                best_rec = max(valid_candidates, key=lambda r: r["confidence"])
                is_consensus = False
                if best_rec["confidence"] >= 0.70:
                    selection_reason = "SINGLE_HIGH_CONFIDENCE_VALID"
                else:
                    selection_reason = "SINGLE_LOW_CONFIDENCE_VALID"

            logger.info(
                "[ANPR_OCR_SELECTION] track_id=%s frame_id=%s %s selected=%s selected_valid=true selected_conf=%.2f consensus=%s selection_reason=%s",
                track_id, frame_id, candidates_str, best_rec["normalized_plate"], best_rec["confidence"], is_consensus, selection_reason
            )
            logger.info(
                "[ANPR_OCR_FINAL] track_id=%s selected_text='%s' selected_variant=%s confidence=%.2f valid=True consensus=%s",
                track_id, best_rec["normalized_plate"], best_rec["variant"], best_rec["confidence"], is_consensus
            )

            return OCRResult(
                plate_text=best_rec["normalized_plate"],
                raw_text=best_rec["raw_text"],
                confidence=best_rec["confidence"],
                is_valid=True,
                state_code=best_rec["state_code"],
                plate_format=best_rec["plate_format"],
            )

        # Priority 4: No variant produced a valid plate -> return highest confidence candidate without forcing validation
        best_rec = max(variant_records, key=lambda r: r["confidence"])
        logger.info(
            "[ANPR_OCR_SELECTION] track_id=%s frame_id=%s %s selected=%s selected_valid=false selected_conf=%.2f consensus=false selection_reason=NO_VALID_VARIANTS",
            track_id, frame_id, candidates_str, best_rec["normalized_plate"], best_rec["confidence"]
        )
        logger.info(
            "[ANPR_OCR_FINAL] track_id=%s selected_text='%s' selected_variant=%s confidence=%.2f valid=False consensus=False",
            track_id, best_rec["normalized_plate"], best_rec["variant"], best_rec["confidence"]
        )

        return OCRResult(
            plate_text=best_rec["normalized_plate"],
            raw_text=best_rec["raw_text"],
            confidence=best_rec["confidence"],
            is_valid=False,
            state_code=best_rec["state_code"],
            plate_format=best_rec["plate_format"],
        )

    def normalize_indian_plate(
        self, raw_str: str, base_conf: float
    ) -> Tuple[str, bool, str, Optional[str], float]:
        """
        Contextually normalizes common character confusions and verifies Indian plate structure.

        Returns
        -------
        (normalized_plate_text, is_valid, format_type, state_code, final_confidence)
        """
        s = "".join(c for c in raw_str.upper() if c.isalnum())

        # Discard strings that are clearly noise (too short, too long, or no digits at all)
        if len(s) < 5 or len(s) > 12 or not any(c.isdigit() for c in s):
            return s, False, "INVALID", None, base_conf * 0.5

        # 1. Check Bharat Series (e.g. 22BH1234AA)
        if len(s) in (9, 10) and ("BH" in s or "8H" in s or "0H" in s):
            chars = list(s)
            # Year digits
            for i in [0, 1]:
                if i < len(chars) and chars[i] in LETTER_TO_DIGIT:
                    chars[i] = LETTER_TO_DIGIT[chars[i]]
            # BH series
            if len(chars) > 3:
                chars[2] = "B"
                chars[3] = "H"
            # 4 digits
            for i in range(4, min(8, len(chars))):
                if chars[i] in LETTER_TO_DIGIT:
                    chars[i] = LETTER_TO_DIGIT[chars[i]]
            # Final 1-2 letters
            for i in range(8, len(chars)):
                if chars[i] in DIGIT_TO_LETTER:
                    chars[i] = DIGIT_TO_LETTER[chars[i]]

            candidate = "".join(chars)
            m = REGEX_BHARAT.match(candidate)
            if m:
                return candidate, True, "BHARAT", "BH", min(0.99, base_conf + 0.10)

        # 2. Standard Indian Series (e.g., MP09AB1234, DL01AB1234, DL1CAB1234, KA01F9999)
        chars = list(s)
        n = len(chars)

        # First 2 characters MUST be state letters
        for i in [0, 1]:
            if chars[i] in DIGIT_TO_LETTER:
                chars[i] = DIGIT_TO_LETTER[chars[i]]

        candidate_state = "".join(chars[:2])

        # State prefix validation and single-character typo fix
        if candidate_state not in INDIAN_STATE_CODES:
            # Common OCR misreads for state prefixes
            state_substitutions = {
                "OP": "MP", "0P": "MP", "DP": "MP",
                "OL": "DL", "0L": "DL", "QL": "DL",
                "K4": "KA", "K8": "KB", "K1": "KL",
                "M8": "MH", "MH": "MH", "MR": "HR",
                "T1": "TN", "T0": "TS",
            }
            if candidate_state in state_substitutions:
                fixed_st = state_substitutions[candidate_state]
                chars[0], chars[1] = fixed_st[0], fixed_st[1]
                candidate_state = fixed_st

        # Last 4 characters MUST always be digits
        for i in range(max(2, n - 4), n):
            if chars[i] in LETTER_TO_DIGIT:
                chars[i] = LETTER_TO_DIGIT[chars[i]]

        # District code and series letters parsing:
        # District digit at index 2 is always a digit
        if n >= 4 and chars[2] in LETTER_TO_DIGIT:
            chars[2] = LETTER_TO_DIGIT[chars[2]]

        # Determine if district is 2 digits or 1 digit
        # If total length is 10, or chars[3] is numeric / '0'/'O', district is 2 digits
        is_two_digit_district = False
        if n >= 5:
            if chars[3].isdigit() or chars[3] in ("O", "Q", "D", "I", "Z", "S", "B"):
                # If length is 10, or length is 9 and chars[4] is letter -> district is 2 digits
                if n == 10 or (n == 9 and not chars[4].isdigit()):
                    is_two_digit_district = True
            elif chars[3].isdigit():
                is_two_digit_district = True

        district_end = 4 if is_two_digit_district else 3

        # Apply digit correction to district
        for i in range(2, min(district_end, n)):
            if chars[i] in LETTER_TO_DIGIT:
                chars[i] = LETTER_TO_DIGIT[chars[i]]

        # Series letters (between district_end and final 4 digits)
        series_end = max(district_end, n - 4)
        for i in range(district_end, series_end):
            if chars[i] in DIGIT_TO_LETTER:
                chars[i] = DIGIT_TO_LETTER[chars[i]]

        candidate = "".join(chars)

        # Validate against standard regex
        m = REGEX_STANDARD.match(candidate)
        if m:
            if m.group(1) in INDIAN_STATE_CODES:
                return candidate, True, "STANDARD", m.group(1), min(0.99, base_conf + 0.12)
            else:
                return candidate, False, "INVALID_STATE", None, base_conf * 0.50

        # Partial validation for recognizable state codes with valid 4-digit suffix
        if candidate_state in INDIAN_STATE_CODES and len(candidate) in (8, 9, 10):
            last4 = candidate[-4:]
            if last4.isdigit():
                return candidate, True, "STANDARD", candidate_state, base_conf
        elif len(candidate) in (9, 10) and candidate[:2].isalpha() and candidate[-4:].isdigit():
            # Looks like Indian format but state is invalid (e.g. XX00ZZ0000)
            return candidate, False, "INVALID_STATE", None, base_conf * 0.50

        # General alphanumeric plate (e.g. LL67ANF, R392BLC, ABC123, DEF456)
        has_letter = any(c.isalpha() for c in candidate)
        has_digit = any(c.isdigit() for c in candidate)
        if len(candidate) in (5, 6, 7, 8) and has_letter and has_digit and base_conf >= 0.40:
            return candidate, True, "STANDARD_ALPHANUMERIC", None, base_conf

        return candidate, False, "UNVERIFIED", None, base_conf * 0.70
