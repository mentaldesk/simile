import io
import struct
import wave
import zipfile
import zlib

from pydantic import ValidationError

from simile.schema import Character

CHARACTER = "character.json"
CLIP = "voice.wav"
MAX_FILE = 12 * 1024 * 1024
MAX_CHARACTER = 256 * 1024
MAX_CLIP = 10 * 1024 * 1024
MAX_SECONDS = 60
ENCRYPTED = 0x1
LIMITS = {CHARACTER: MAX_CHARACTER, CLIP: MAX_CLIP}


class Refused(ValueError):
    """Input the library won't take, with the reason."""


def reasons(error: ValidationError) -> str:
    return "; ".join(
        f"{'.'.join(map(str, e['loc']))}: {e['msg']}" if e["loc"] else e["msg"]
        for e in error.errors(include_url=False)
    )


def pack(character: Character, clip: bytes | None) -> bytes:
    """One zip: the character as `character.json`, and its reference clip as `voice.wav`."""
    voice = character.voice.model_copy(update={"reference_clip": CLIP if clip else None})
    exported = character.model_copy(update={"voice": voice})
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(CHARACTER, exported.model_dump_json(indent=2) + "\n")
        if clip is not None:
            archive.writestr(CLIP, clip)
    return buffer.getvalue()


def unpack(data: bytes) -> tuple[Character, bytes | None]:
    """The character and clip in an exported file. Raises `Refused` for anything else."""
    if len(data) > MAX_FILE:
        raise Refused(f"A character file can be at most {MAX_FILE // 2**20} MB")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            members = archive.infolist()
            names = [member.filename for member in members]
            if unexpected := [name for name in names if name not in LIMITS]:
                raise Refused(
                    f"A character file holds only {CHARACTER} and {CLIP}, not "
                    f"{unexpected[0][:80]!r}"
                )
            if len(set(names)) < len(names):
                raise Refused("The character file has the same name in it twice")
            if CHARACTER not in names:
                raise Refused(f"The character file has no {CHARACTER}")
            files = {member.filename: _read(archive, member) for member in members}
    except (zipfile.BadZipFile, zlib.error, EOFError, NotImplementedError) as error:
        raise Refused(f"That isn't a character file: {error}") from None
    try:
        character = Character.model_validate_json(files[CHARACTER])
    except ValidationError as error:
        raise Refused(f"{CHARACTER} isn't a valid character: {reasons(error)}") from None
    clip = files.get(CLIP)
    if clip is not None:
        check_clip(clip)
    return character, clip


def check_clip(clip: bytes) -> None:
    """Raises `Refused` unless `clip` is a WAV file that decodes in full."""
    try:
        with wave.open(io.BytesIO(clip)) as audio:
            frames, rate = audio.getnframes(), audio.getframerate()
            size = frames * audio.getnchannels() * audio.getsampwidth()
            decoded = len(audio.readframes(frames))
    except (wave.Error, EOFError, struct.error, ValueError) as error:
        raise Refused(f"The voice clip isn't a WAV file that decodes: {error}") from None
    if frames == 0 or rate == 0:
        raise Refused("The voice clip is empty")
    if decoded < size:
        raise Refused("The voice clip is cut short")
    if frames / rate > MAX_SECONDS:
        raise Refused(f"The voice clip can be at most {MAX_SECONDS} seconds long")


def _read(archive: zipfile.ZipFile, member: zipfile.ZipInfo) -> bytes:
    limit = LIMITS[member.filename]
    if member.flag_bits & ENCRYPTED:
        raise Refused(f"{member.filename} is encrypted")
    if member.file_size > limit:
        raise Refused(f"{member.filename} can be at most {limit // 1024} KB")
    with archive.open(member) as file:
        content = file.read(limit + 1)
    if len(content) > limit:
        raise Refused(f"{member.filename} can be at most {limit // 1024} KB")
    return content
