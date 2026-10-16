import json
import logging
import sys
import warnings
from pathlib import Path

import numpy as np
import soundfile as sf
import torch
from scipy.signal import resample_poly

MODEL = "Jzuluaga/accent-id-commonaccent_ecapa"
SAMPLE_RATE = 16_000
NORTH_AMERICAN = {"us", "canada"}
COSINE_SCALE = 30  # the AAM-softmax scale it was trained with
KNOWN = {
    "american": "us",
    "canadian": "canada",
    "australian": "australia",
    "new zealand": "newzealand",
    "kiwi": "newzealand",
    "indian": "indian",
    "scottish": "scotland",
    "scots": "scotland",
    "irish": "ireland",
    "welsh": "wales",
    "african": "african",
    "ghanaian": "african",
    "nigerian": "african",
    "malaysian": "malaysia",
    "filipino": "philippines",
    "hong kong": "hongkong",
    "singapore": "singapore",
}


def expected(description: str) -> str | None:
    """The accent the classifier should hear: the first one the description names that it knows."""
    named = [(found, label) for word, label in KNOWN.items() if (found := description.lower().find(word)) >= 0]
    return min(named)[1] if named else None


def load():
    logging.getLogger("speechbrain").setLevel(logging.ERROR)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from speechbrain.inference.classifiers import EncoderClassifier

        return EncoderClassifier.from_hparams(
            source=MODEL, savedir=Path(__file__).parent / "out" / "accent-model", run_opts={"device": "cpu"}
        )


def classify(model, wav: np.ndarray, sr: int) -> list[tuple[str, float]]:
    """Every accent the model knows, most likely first."""
    if wav.ndim > 1:
        wav = wav.mean(axis=1)
    audio = torch.tensor(resample_poly(wav, SAMPLE_RATE, sr), dtype=torch.float32)[None]
    scores = model.classify_batch(audio)[0].reshape(-1)
    probabilities = torch.softmax(COSINE_SCALE * scores, dim=-1).tolist()
    labels = model.hparams.label_encoder.ind2lab
    return sorted(((labels[i], p) for i, p in enumerate(probabilities)), key=lambda a: -a[1])


def miss(accents: list[tuple[str, float]], target: str | None) -> float:
    """How far the clip is from the target accent and, unless that's American, from not sounding North American."""
    p = dict(accents)
    if target in NORTH_AMERICAN:
        return 1 - p[target]
    return (1 - p[target] if target else 0) + sum(p[label] for label in NORTH_AMERICAN)


def problem(accents: list[tuple[str, float]], target: str | None) -> str | None:
    heard = accents[0][0]
    if target and heard != target:
        return f"sounds {describe(accents)}, not {target}"
    if not target and heard in NORTH_AMERICAN:
        return f"sounds North American ({describe(accents)})"
    return None


def describe(accents: list[tuple[str, float]]) -> str:
    return ", ".join(f"{label} {p:.0%}" for label, p in accents[:2] if p >= 0.01)


if __name__ == "__main__":
    model = load()
    print(json.dumps({path: describe(classify(model, *sf.read(path))) for path in sys.argv[1:]}))
