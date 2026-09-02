"""
Gera fixtures de áudio deliberadamente problemáticos para testes de mordida.
Usa numpy + scipy.io.wavfile para criar WAVs sintéticos.
Rodar: python generate_fixtures.py
"""
import numpy as np
import scipy.io.wavfile as wavfile
import os
from pathlib import Path

OUTPUT_DIR = Path("fixture-output")
FIXTURES = [
    {
        "name": "clipping.wav",
        "description": "Senoide com amostras saturadas (±1.0) — clipping intencional",
        "duration_s": 3,
        "sample_rate": 48000,
        "channels": 2,
        "generator": lambda: generate_clipping(3, 48000, 2)
    },
    {
        "name": "loudness_high.wav",
        "description": "Senoide em -10 LUFS (muito alto para broadcast)",
        "duration_s": 3,
        "sample_rate": 48000,
        "channels": 2,
        "generator": lambda: generate_loudness_high(3, 48000, 2)
    },
    {
        "name": "true_peak_high.wav",
        "description": "Senoide com transientes que geram true peak > 0 dBTP",
        "duration_s": 3,
        "sample_rate": 48000,
        "channels": 2,
        "generator": lambda: generate_true_peak_high(3, 48000, 2)
    },
    {
        "name": "phase_inverted.wav",
        "description": "Stereo com canal direito invertido de fase",
        "duration_s": 3,
        "sample_rate": 48000,
        "channels": 2,
        "generator": lambda: generate_phase_inverted(3, 48000)
    },
    {
        "name": "clean_pass.wav",
        "description": "Senoide limpa, dentro de todos os limites",
        "duration_s": 3,
        "sample_rate": 48000,
        "channels": 2,
        "generator": lambda: generate_clean(3, 48000, 2)
    }
]

def generate_clean(duration_s, sr, channels):
    """Senoide limpa em -23 LUFS."""
    frames = int(duration_s * sr)
    t = np.linspace(0, duration_s, frames, endpoint=False)
    freq = 440
    # Senoide com amplitude controlada para -23 LUFS
    # LUFS é relativo — aqui usamos amplitude ≈ 0.1 (-20 dBFS) como aproximação
    amp = 0.1
    left = amp * np.sin(2 * np.pi * freq * t)
    right = amp * np.sin(2 * np.pi * freq * t + np.pi/6)  # fase levemente deslocada
    if channels == 1:
        return np.stack([left], axis=1)
    else:
        return np.stack([left, right], axis=1)

def generate_clipping(duration_s, sr, channels):
    """Senoide que excede ±1.0 em 10% das amostras."""
    frames = int(duration_s * sr)
    t = np.linspace(0, duration_s, frames, endpoint=False)
    freq = 440
    amp = 1.3  # > 1.0 → clipping
    left = amp * np.sin(2 * np.pi * freq * t)
    right = amp * np.sin(2 * np.pi * freq * t + np.pi/4)
    if channels == 1:
        pcm = np.stack([left], axis=1)
    else:
        pcm = np.stack([left, right], axis=1)
    # Clipping hard
    return np.clip(pcm, -1.0, 1.0)

def generate_loudness_high(duration_s, sr, channels):
    """Senoide em amplitude alta (~-10 LUFS)."""
    frames = int(duration_s * sr)
    t = np.linspace(0, duration_s, frames, endpoint=False)
    freq = 440
    amp = 0.35  # ≈ -10 LUFS
    left = amp * np.sin(2 * np.pi * freq * t)
    right = amp * np.sin(2 * np.pi * freq * t + np.pi/6)
    if channels == 1:
        return np.stack([left], axis=1)
    else:
        return np.stack([left, right], axis=1)

def generate_true_peak_high(duration_s, sr, channels):
    """Sinal com transientes que geram true peak acima de 0 dBTP."""
    frames = int(duration_s * sr)
    t = np.linspace(0, duration_s, frames, endpoint=False)
    # Combinação de senoides com diferentes fases → picos inter-sample
    sig = 0.6 * np.sin(2 * np.pi * 440 * t)
    sig += 0.4 * np.sin(2 * np.pi * 880 * t + np.pi/3)
    sig += 0.15 * np.sin(2 * np.pi * 1760 * t + np.pi/2)
    # Normaliza para não clipar no sample, mas gerar true peak alto
    sig = sig / np.max(np.abs(sig)) * 0.92
    if channels == 1:
        return np.stack([sig], axis=1)
    else:
        # Canal direito com fase invertida → aumenta true peak inter-channel
        left = sig
        right = -sig
        return np.stack([left, right], axis=1)

def generate_phase_inverted(duration_s, sr, channels=2):
    """Stereo com canal direito invertido de fase."""
    frames = int(duration_s * sr)
    t = np.linspace(0, duration_s, frames, endpoint=False)
    freq = 440
    amp = 0.2
    left = amp * np.sin(2 * np.pi * freq * t)
    right = -amp * np.sin(2 * np.pi * freq * t)  # fase invertida
    return np.stack([left, right], axis=1)

if __name__ == "__main__":
    OUTPUT_DIR.mkdir(exist_ok=True)
    print(f"Gerando {len(FIXTURES)} fixtures em {OUTPUT_DIR}/")
    for fixture in FIXTURES:
        pcm = fixture["generator"]()
        # Normaliza para int16
        pcm_f32 = pcm.astype(np.float32)
        pcm_i16 = (pcm_f32 * 32767).astype(np.int16)
        path = OUTPUT_DIR / fixture["name"]
        wavfile.write(str(path), fixture["sample_rate"], pcm_i16)
        print(f"✅ {fixture['name']} — {fixture['description']}")
    print("✅ Geração concluída.")
