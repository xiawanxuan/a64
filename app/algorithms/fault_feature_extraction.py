import numpy as np
from typing import Dict, Any, List, Tuple, Optional
from dataclasses import dataclass, field
from loguru import logger

from app.core.hyperparams import load_hyperparams
from app.core.exceptions import BusinessException
from app.core.error_codes import ErrorCode
from app.algorithms.order_spectrum import find_spectral_peaks

hyperparams = load_hyperparams()


@dataclass
class GearFaultFeatures:
    gear_param_id: Optional[str] = None
    stage: int = 0
    gear_type: str = ""
    teeth_count: int = 0
    mesh_order: float = 0.0
    mesh_amplitude: float = 0.0
    sideband_orders: List[float] = field(default_factory=list)
    sideband_amplitudes: List[float] = field(default_factory=list)
    sideband_spacing: float = 0.0
    max_sideband_amp: float = 0.0
    sideband_energy: float = 0.0
    kurtosis: float = 0.0
    crest_factor: float = 0.0
    rms_value: float = 0.0
    peak_value: float = 0.0
    fault_severity: int = 0
    diagnosis_note: str = ""


def _estimate_noise_floor(
    spectrum: np.ndarray,
    method: str = "percentile",
    percentile: int = 10
) -> float:
    if len(spectrum) == 0:
        return 0.0
    if method == "percentile":
        return float(np.percentile(spectrum, percentile))
    if method == "mean_edges":
        n = len(spectrum)
        edge_n = max(10, n // 10)
        edges = np.concatenate([spectrum[:edge_n], spectrum[-edge_n:]])
        return float(np.mean(edges))
    return float(np.percentile(spectrum, 10))


def _locate_mesh_peak(
    order_axis: np.ndarray,
    spectrum: np.ndarray,
    target_order: float,
    tolerance: float = 0.15,
    noise_floor: float = 0.0
) -> Tuple[Optional[int], float, float]:
    if len(order_axis) < 3:
        return None, target_order, 0.0

    d_order = float(order_axis[1] - order_axis[0]) if len(order_axis) > 1 else 1.0
    tol_samples = max(1, int(tolerance / d_order))

    near = np.where(np.abs(order_axis - target_order) <= tolerance)[0]
    if len(near) == 0:
        search_left = max(0, int((target_order - tolerance - order_axis[0]) / d_order))
        search_right = min(len(order_axis) - 1, search_left + 2 * tol_samples)
        if search_left > len(order_axis) - 1 or search_right < 0:
            return None, target_order, 0.0
        near = np.arange(max(0, search_left), min(len(order_axis), search_right + 1))

    if len(near) == 0:
        return None, target_order, 0.0

    sub_spectrum = spectrum[near]
    peak_idx_in_sub = int(np.argmax(sub_spectrum))
    peak_idx = int(near[peak_idx_in_sub])
    peak_amp = float(spectrum[peak_idx])
    peak_order = float(order_axis[peak_idx])

    if noise_floor > 0 and peak_amp < noise_floor * 1.5:
        return None, peak_order, peak_amp

    return peak_idx, peak_order, peak_amp


def _extract_sidebands(
    order_axis: np.ndarray,
    spectrum: np.ndarray,
    mesh_order: float,
    mesh_amp: float,
    modulation_order: float,
    search_range: int = 5,
    tolerance: float = 0.05,
    significance_threshold: float = 2.5,
    noise_floor: float = 0.0,
    min_amplitude: float = 1e-6
) -> Tuple[List[float], List[float], float, float]:
    d_order = float(order_axis[1] - order_axis[0]) if len(order_axis) > 1 else 1.0
    tol_samples = max(1, int(tolerance / d_order))

    sb_orders: List[float] = []
    sb_amplitudes: List[float] = []
    sb_spacing_sum: List[float] = []

    for k in range(1, search_range + 1):
        for sign in [-1, 1]:
            target = mesh_order + sign * k * modulation_order
            if target < order_axis[0] or target > order_axis[-1]:
                continue

            near = np.where(np.abs(order_axis - target) <= tolerance)[0]
            if len(near) == 0:
                center = int(np.clip((target - order_axis[0]) / d_order, 0, len(order_axis) - 1))
                lo = max(0, center - tol_samples)
                hi = min(len(order_axis) - 1, center + tol_samples)
                near = np.arange(lo, hi + 1)

            if len(near) == 0:
                continue

            sub = spectrum[near]
            idx_in_sub = int(np.argmax(sub))
            peak_idx = int(near[idx_in_sub])
            peak_amp = float(spectrum[peak_idx])
            peak_order = float(order_axis[peak_idx])

            actual_spacing = abs(peak_order - mesh_order) / k if k > 0 else 0
            if actual_spacing > 0:
                sb_spacing_sum.append(actual_spacing)

            is_significant = (
                peak_amp >= min_amplitude
                and (noise_floor <= 0 or peak_amp >= noise_floor * significance_threshold)
            )

            if is_significant or peak_amp >= mesh_amp * 0.05:
                sb_orders.append(peak_order)
                sb_amplitudes.append(peak_amp)

    if sb_orders:
        sorted_idx = np.argsort(sb_orders)
        sb_orders = [sb_orders[i] for i in sorted_idx]
        sb_amplitudes = [sb_amplitudes[i] for i in sorted_idx]

    avg_spacing = float(np.mean(sb_spacing_sum)) if sb_spacing_sum else modulation_order
    max_sb = float(max(sb_amplitudes)) if sb_amplitudes else 0.0
    sb_energy = float(np.sum(np.array(sb_amplitudes) ** 2)) if sb_amplitudes else 0.0

    return sb_orders, sb_amplitudes, avg_spacing, max_sb, sb_energy


def compute_statistics(
    time_signal: np.ndarray,
    remove_dc: bool = True
) -> Dict[str, float]:
    if len(time_signal) == 0:
        return {"kurtosis": 0.0, "crest_factor": 0.0, "rms": 0.0, "peak": 0.0}

    sig = time_signal.copy()
    if remove_dc:
        sig = sig - np.mean(sig)

    rms = float(np.sqrt(np.mean(sig ** 2)))
    peak = float(np.max(np.abs(sig)))
    crest = float(peak / rms) if rms > 0 else 0.0

    std = float(np.std(sig))
    if std > 0:
        kurt = float(np.mean(((sig - np.mean(sig)) / std) ** 4))
    else:
        kurt = 0.0

    return {
        "kurtosis": kurt,
        "crest_factor": crest,
        "rms": rms,
        "peak": peak
    }


def _assess_severity(
    features: GearFaultFeatures,
    sev_cfg: Dict[str, Any]
) -> int:
    warn_energy = float(sev_cfg.get("warning_energy_ratio", 0.15))
    alarm_energy = float(sev_cfg.get("alarm_energy_ratio", 0.35))
    warn_amp = float(sev_cfg.get("warning_amp_ratio", 0.25))
    alarm_amp = float(sev_cfg.get("alarm_amp_ratio", 0.50))
    warn_kurt = float(sev_cfg.get("warning_kurtosis", 4.0))
    alarm_kurt = float(sev_cfg.get("alarm_kurtosis", 6.0))
    warn_crest = float(sev_cfg.get("warning_crest_factor", 3.5))
    alarm_crest = float(sev_cfg.get("alarm_crest_factor", 6.0))

    if features.mesh_amplitude <= 0:
        return 0

    energy_ratio = float(np.sqrt(features.sideband_energy)) / features.mesh_amplitude if features.mesh_amplitude > 0 else 0
    amp_ratio = features.max_sideband_amp / features.mesh_amplitude if features.mesh_amplitude > 0 else 0

    alarm_count = 0
    warning_count = 0

    if energy_ratio >= alarm_energy:
        alarm_count += 1
    elif energy_ratio >= warn_energy:
        warning_count += 1

    if amp_ratio >= alarm_amp:
        alarm_count += 1
    elif amp_ratio >= warn_amp:
        warning_count += 1

    if features.kurtosis >= alarm_kurt:
        alarm_count += 1
    elif features.kurtosis >= warn_kurt:
        warning_count += 1

    if features.crest_factor >= alarm_crest:
        alarm_count += 1
    elif features.crest_factor >= warn_crest:
        warning_count += 1

    if alarm_count >= 2 or (alarm_count >= 1 and warning_count >= 2):
        return 3
    if alarm_count >= 1 or warning_count >= 2:
        return 2
    if warning_count >= 1:
        return 1
    return 0


def extract_gear_fault_features(
    order_axis: np.ndarray,
    spectrum: np.ndarray,
    time_domain_signal: np.ndarray,
    gear_params_list: List[Dict[str, Any]],
    speed_modulation_order: float = 1.0,
    cfg_override: Optional[Dict[str, Any]] = None
) -> List[GearFaultFeatures]:
    cfg = (hyperparams.feature_extraction or {}).copy()
    if cfg_override:
        cfg.update(cfg_override)

    mesh_tol = float(cfg.get("mesh_order_tolerance", 0.15))
    sb_range = int(cfg.get("sideband_search_range", 5))
    mod_tol = float(cfg.get("modulation_order_tolerance", 0.05))
    sig_thresh = float(cfg.get("sideband_significance_threshold", 2.5))
    min_sb_amp = float(cfg.get("min_sideband_amplitude", 1e-6))
    noise_method = cfg.get("noise_floor_method", "percentile")
    noise_percentile = int(cfg.get("noise_floor_percentile", 10))
    sev_cfg = cfg.get("severity", {}) or {}
    stats_cfg = cfg.get("statistics", {}) or {}

    noise_floor = _estimate_noise_floor(spectrum, noise_method, noise_percentile)

    stats = compute_statistics(
        time_domain_signal,
        remove_dc=bool(stats_cfg.get("rms_remove_dc", True))
    )

    peak_orders, peak_amps, _ = find_spectral_peaks(
        order_axis, spectrum,
        prominence_ratio=0.01,
        min_distance=mesh_tol * 0.5,
        max_peaks=200
    )

    results: List[GearFaultFeatures] = []

    for gear in gear_params_list:
        teeth = int(gear.get("teeth_count", 0))
        if teeth <= 0:
            continue

        stage = int(gear.get("stage", 1))
        stage_ratio = float(gear.get("stage_speed_ratio", 1.0))
        target_mesh_order = float(teeth) * stage_ratio

        idx, actual_mesh_order, mesh_amp = _locate_mesh_peak(
            order_axis, spectrum,
            target_order=target_mesh_order,
            tolerance=mesh_tol,
            noise_floor=noise_floor
        )

        feat = GearFaultFeatures(
            gear_param_id=str(gear.get("gear_param_id", "")),
            stage=stage,
            gear_type=str(gear.get("gear_type", "")),
            teeth_count=teeth,
            mesh_order=actual_mesh_order,
            mesh_amplitude=mesh_amp,
            kurtosis=stats.get("kurtosis", 0.0),
            crest_factor=stats.get("crest_factor", 0.0),
            rms_value=stats.get("rms", 0.0),
            peak_value=stats.get("peak", 0.0),
        )

        if idx is None or mesh_amp <= 0:
            feat.diagnosis_note = (
                f"第{stage}级{feat.gear_type}(Z={teeth}): "
                f"啮合阶次{target_mesh_order:.2f}未检出显著谱峰"
            )
            results.append(feat)
            continue

        modulation_order = speed_modulation_order * stage_ratio
        if len(peak_orders) > 0:
            diffs = np.abs(peak_orders - modulation_order)
            best_i = int(np.argmin(diffs))
            if diffs[best_i] <= mod_tol * 2:
                modulation_order = float(peak_orders[best_i])

        sb_orders, sb_amps, spacing, max_sb, sb_energy = _extract_sidebands(
            order_axis, spectrum,
            mesh_order=actual_mesh_order,
            mesh_amp=mesh_amp,
            modulation_order=modulation_order,
            search_range=sb_range,
            tolerance=mod_tol,
            significance_threshold=sig_thresh,
            noise_floor=noise_floor,
            min_amplitude=min_sb_amp
        )

        feat.sideband_orders = sb_orders
        feat.sideband_amplitudes = sb_amps
        feat.sideband_spacing = spacing
        feat.max_sideband_amp = max_sb
        feat.sideband_energy = sb_energy
        feat.fault_severity = _assess_severity(feat, sev_cfg)

        if feat.fault_severity >= 2:
            severity_label = ["正常", "预警", "报警", "严重"][feat.fault_severity]
            amp_ratio = max_sb / mesh_amp if mesh_amp > 0 else 0
            feat.diagnosis_note = (
                f"第{stage}级{feat.gear_type}(Z={teeth}){severity_label}: "
                f"啮合阶次{actual_mesh_order:.2f}, "
                f"最大边频幅值比{amp_ratio:.2%}, "
                f"边频对数{len(sb_amps)//2}, "
                f"峭度={feat.kurtosis:.2f}, 峰值因子={feat.crest_factor:.2f}"
            )
        else:
            feat.diagnosis_note = (
                f"第{stage}级{feat.gear_type}(Z={teeth})正常: "
                f"啮合阶次{actual_mesh_order:.2f}, 边频特征不显著"
            )

        results.append(feat)

    if not results:
        raise BusinessException(
            ErrorCode.FEATURE_EXTRACT_FAILED,
            "未配置有效齿轮参数，无法提取特征"
        )

    return results
