"""
Тестовый скрипт для проверки влияния SNR на eye diagram.
"""

import numpy as np
import matplotlib.pyplot as plt
from scipy.special import erf

def generate_eye_diagram_with_snr(osnr_db=None, sigma_out_ps=50, t_bit_ps=100, peak_out=0.5):
    """
    Генерирует eye diagram с учетом SNR.

    Args:
        osnr_db: OSNR в дБ (если None, шум не добавляется)
        sigma_out_ps: RMS ширина выходного импульса в пс
        t_bit_ps: Битовый интервал в пс
        peak_out: Пиковая амплитуда выходного сигнала
    """
    # Временная ось
    n_samples = 5000
    t_axis = np.linspace(-2.5 * t_bit_ps, 2.5 * t_bit_ps, n_samples)

    # Генерируем трассы для всех 5-битовых последовательностей
    traces_high = []
    traces_low = []

    for a in [0, 1]:
        for b in [0, 1]:
            for c in [0, 1]:  # центральный бит
                for d in [0, 1]:
                    for e in [0, 1]:
                        y_out = np.zeros_like(t_axis)

                        bit_sequence = [a, b, c, d, e]
                        for bit_idx, bit_val in enumerate(bit_sequence):
                            t_start = (bit_idx - 2) * t_bit_ps
                            t_end = (bit_idx - 1) * t_bit_ps

                            if bit_val == 1:
                                sigma_eff_out = max(sigma_out_ps, t_bit_ps * 0.02)
                                y_out += 0.5 * peak_out * (1 + erf((t_axis - t_start) / (sigma_eff_out * np.sqrt(2))))
                                y_out -= 0.5 * peak_out * (1 + erf((t_axis - t_end) / (sigma_eff_out * np.sqrt(2))))

                        if c == 1:
                            traces_high.append(y_out)
                        else:
                            traces_low.append(y_out)

    # Вычисляем уровень шума
    noise_std = 0.0
    snr_linear = None
    if osnr_db is not None and osnr_db > 0:
        snr_linear = 10 ** (osnr_db / 10.0)
        noise_std = peak_out / np.sqrt(snr_linear)
        print(f"OSNR = {osnr_db:.2f} дБ")
        print(f"SNR (linear) = {snr_linear:.2f}")
        print(f"Noise std = {noise_std:.6f}")
        print(f"Peak signal = {peak_out:.3f}")
        print(f"SNR (signal/noise) = {peak_out / noise_std:.2f}")

    # Создаем фигуру
    fig, axes = plt.subplots(1, 2, figsize=(16, 6))

    # Без шума
    ax1 = axes[0]
    for y_out in traces_high:
        ax1.plot(t_axis, y_out, color="#E53935", linewidth=2, alpha=0.7)
    for y_out in traces_low:
        ax1.plot(t_axis, y_out, color="#FF9800", linewidth=2, alpha=0.7)

    ax1.set_title("Eye Diagram БЕЗ шума", fontsize=14, fontweight="bold")
    ax1.set_xlabel("Время (пс)", fontsize=12)
    ax1.set_ylabel("Амплитуда", fontsize=12)
    ax1.grid(True, linestyle="--", alpha=0.3)
    ax1.axhline(0.5 * peak_out, color="green", linestyle="--", alpha=0.8, linewidth=2)
    ax1.set_xlim(-t_bit_ps * 1.5, t_bit_ps * 1.5)

    # С шумом
    ax2 = axes[1]
    for y_out in traces_high:
        if noise_std > 0:
            noise = np.random.normal(0, noise_std, len(y_out))
            y_out_noisy = y_out + noise
        else:
            y_out_noisy = y_out
        ax2.plot(t_axis, y_out_noisy, color="#E53935", linewidth=2, alpha=0.7)

    for y_out in traces_low:
        if noise_std > 0:
            noise = np.random.normal(0, noise_std, len(y_out))
            y_out_noisy = y_out + noise
        else:
            y_out_noisy = y_out
        ax2.plot(t_axis, y_out_noisy, color="#FF9800", linewidth=2, alpha=0.7)

    title_snr = f"Eye Diagram С шумом (OSNR = {osnr_db:.1f} дБ)" if osnr_db else "Eye Diagram БЕЗ шума"
    ax2.set_title(title_snr, fontsize=14, fontweight="bold")
    ax2.set_xlabel("Время (пс)", fontsize=12)
    ax2.set_ylabel("Амплитуда", fontsize=12)
    ax2.grid(True, linestyle="--", alpha=0.3)
    ax2.axhline(0.5 * peak_out, color="green", linestyle="--", alpha=0.8, linewidth=2)
    ax2.set_xlim(-t_bit_ps * 1.5, t_bit_ps * 1.5)

    plt.tight_layout()
    return fig


if __name__ == "__main__":
    # Тест с разными уровнями OSNR
    print("=" * 60)
    print("Тест 1: Высокий OSNR (30 дБ) - хорошее качество")
    print("=" * 60)
    fig1 = generate_eye_diagram_with_snr(osnr_db=30, sigma_out_ps=50, t_bit_ps=100, peak_out=0.5)
    plt.savefig("eye_diagram_osnr_30db.png", dpi=150)
    print()

    print("=" * 60)
    print("Тест 2: Средний OSNR (20 дБ) - приемлемое качество")
    print("=" * 60)
    fig2 = generate_eye_diagram_with_snr(osnr_db=20, sigma_out_ps=50, t_bit_ps=100, peak_out=0.5)
    plt.savefig("eye_diagram_osnr_20db.png", dpi=150)
    print()

    print("=" * 60)
    print("Тест 3: Низкий OSNR (10 дБ) - плохое качество")
    print("=" * 60)
    fig3 = generate_eye_diagram_with_snr(osnr_db=10, sigma_out_ps=50, t_bit_ps=100, peak_out=0.5)
    plt.savefig("eye_diagram_osnr_10db.png", dpi=150)
    print()

    print("Графики сохранены:")
    print("  - eye_diagram_osnr_30db.png")
    print("  - eye_diagram_osnr_20db.png")
    print("  - eye_diagram_osnr_10db.png")

    plt.show()
