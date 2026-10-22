from typing import Annotated

import typer


def register(app: typer.Typer) -> None:
    @app.command()
    def greetings(
        npcs: Annotated[
            list[str] | None, typer.Argument(help="Resident ids. Defaults to all of them.")
        ] = None,
        force: Annotated[
            bool, typer.Option(help="Make greetings that are up to date too.")
        ] = False,
    ) -> None:
        """Record each resident's greetings into content/voices/greetings/.

        Says each line in content/voices/greetings/lines.json in the resident's own voice, with
        V1's model. Makes only the greetings that are missing or out of date, unless --force.
        Needs the voice extra (`uv run --extra voice simile greetings`) and macOS's afconvert.
        """
        import importlib.util
        import shutil

        from simile.npc import NPCS_DIR, load_npcs
        from simile.voicing import gpu
        from simile.voicing import greetings as recorded
        from simile.voicing.greetings import (
            Made,
            digest,
            load_lines,
            load_made,
            outdated,
            save_made,
        )

        residents = {npc.id: npc for npc in load_npcs(NPCS_DIR)}
        if unknown := sorted(set(npcs or ()) - residents.keys()):
            raise typer.BadParameter(f"no such resident: {', '.join(unknown)}", param_hint="NPCS")
        lines = load_lines()
        before = load_made()
        made = {id: entry for id, entry in before.items() if id in residents}
        chosen = [residents[id] for id in npcs] if npcs else list(residents.values())
        if missing := [npc.id for npc in chosen if npc.id not in lines]:
            typer.echo(f"No lines in {recorded.LINES.name}, so no greetings: {', '.join(missing)}")
        voiced = [npc for npc in chosen if npc.voice.reference_clip and npc.id in lines]
        todo = voiced if force else outdated(voiced, lines, made)
        if not todo:
            if made != before:
                save_made(made)
            typer.echo("Every greeting is up to date. --force makes them again.")
            return
        if importlib.util.find_spec("mlx_audio") is None:
            typer.echo("Making greetings needs the voice extra: uv sync --extra voice", err=True)
            raise typer.Exit(1)
        if shutil.which("afconvert") is None:
            typer.echo("Making greetings needs afconvert, which comes with macOS", err=True)
            raise typer.Exit(1)
        from simile.voicing import speak

        gpu.wait_for_gpu(typer.echo)
        model = speak.load()
        folder = recorded.GREETINGS
        for npc in todo:
            assert npc.voice.reference_clip is not None
            said = [(line.text, line.take) for line in lines[npc.id]]
            recorded.remove(folder, npc.id)
            clip = recorded.REPO_ROOT / npc.voice.reference_clip
            seconds = speak.speak(model, npc.id, clip, npc.voice.reference_line, said, folder)
            made[npc.id] = Made(digest=digest(npc.voice, lines[npc.id]), seconds=seconds)
            save_made(made)
            for (text, _), length in zip(said, seconds, strict=True):
                typer.echo(f"{npc.id}: {text!r} {length:.2f} s")
        total = sum(path.stat().st_size for path in folder.glob("*.m4a"))
        typer.echo(f"Wrote content/voices/greetings/, {total / 1024:.0f} KB in all")
