import json
import sys
import warnings

from mlx_audio.stt.utils import load_model
from transformers import WhisperProcessor

MODEL = "mlx-community/whisper-large-v3-turbo"


def load():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model = load_model(MODEL)
    # The MLX conversion ships without tokenizer files, so take them from the original.
    model._processor = WhisperProcessor.from_pretrained("openai/whisper-large-v3-turbo")
    return model


def transcribe(model, path: str) -> str:
    return model.generate(path, language="en").text.strip()


if __name__ == "__main__":
    model = load()
    print(json.dumps({path: transcribe(model, path) for path in sys.argv[1:]}))
