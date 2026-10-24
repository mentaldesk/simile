from typing import Annotated

import typer

KEY_PROMPT = 60.0
"""Seconds to wait for the Keychain here, where someone can answer its prompt."""


def register(app: typer.Typer) -> None:
    @app.command()
    def greetings(
        npcs: Annotated[
            list[str] | None, typer.Argument(help="Resident ids. Defaults to all of them.")
        ] = None,
        force: Annotated[
            bool, typer.Option(help="Make greetings that are up to date too.")
        ] = False,
        audition: Annotated[
            bool, typer.Option(help="Say only each one's first line, to hear the voice first.")
        ] = False,
        local: Annotated[
            bool,
            typer.Option(help="Use V1's model, even over greetings made with ElevenLabs."),
        ] = False,
    ) -> None:
        """Record each resident's greetings into content/voices/greetings/ (see its README)."""
        import importlib.util
        import shutil
        from contextlib import ExitStack

        from simile.clinic.doctor import load_doctor
        from simile.npc import NPCS_DIR, load_npcs
        from simile.schema import Npc
        from simile.voicing import eleven, gpu, speak
        from simile.voicing import greetings as recorded
        from simile.voicing.greetings import (
            Engine,
            Say,
            load_chosen,
            load_lines,
            load_made,
            outdated,
            record,
            save_made,
        )

        residents = {npc.id: npc for npc in [*load_npcs(NPCS_DIR), load_doctor()]}
        if unknown := sorted(set(npcs or ()) - residents.keys()):
            raise typer.BadParameter(f"no such resident: {', '.join(unknown)}", param_hint="NPCS")
        lines, chosen = load_lines(), load_chosen()
        before = load_made()
        made = {id: entry for id, entry in before.items() if id in residents}
        picked = [residents[id] for id in npcs] if npcs else list(residents.values())
        if missing := [npc.id for npc in picked if npc.id not in lines]:
            typer.echo(f"No lines in {recorded.LINES.name}, so no greetings: {', '.join(missing)}")
        keyed = not local and any(npc.id in chosen for npc in picked) and eleven.configured()

        def engine(npc: Npc) -> Engine:
            return Engine.ELEVENLABS if keyed and npc.id in chosen else Engine.LOCAL

        voiced = [
            npc
            for npc in picked
            if npc.id in lines and (npc.id in chosen or npc.voice.reference_clip)
        ]
        todo = voiced if force else outdated(voiced, lines, made, chosen, engine)
        if not todo:
            if made != before:
                save_made(made)
            typer.echo("Every greeting is up to date. --force makes them again.")
            return
        replacing = [
            npc.id
            for npc in todo
            if engine(npc) is Engine.LOCAL
            and npc.id in made
            and made[npc.id].engine is Engine.ELEVENLABS
        ]
        if replacing and not local:
            typer.echo(
                f"Without an ElevenLabs key ({eleven.ENV}), V1's model would replace greetings "
                f"made with ElevenLabs: {', '.join(replacing)}. --local replaces them anyway.",
                err=True,
            )
            raise typer.Exit(1)
        if not keyed and any(npc.id in chosen for npc in todo):
            typer.echo(f"No ElevenLabs key ({eleven.ENV}), so V1's model says them instead")
        local_todo = [npc for npc in todo if engine(npc) is Engine.LOCAL]
        if local_todo and importlib.util.find_spec("mlx_audio") is None:
            typer.echo("Making greetings needs the voice extra: uv sync --extra voice", err=True)
            raise typer.Exit(1)
        if shutil.which("afconvert") is None:
            typer.echo("Making greetings needs afconvert, which comes with macOS", err=True)
            raise typer.Exit(1)
        with_elevenlabs = len(local_todo) < len(todo)
        key = eleven.api_key(timeout=KEY_PROMPT) if with_elevenlabs else None
        if with_elevenlabs and key is None:
            typer.echo(
                f"No usable ElevenLabs key ({eleven.ENV} or the Keychain item {eleven.KEYCHAIN})",
                err=True,
            )
            raise typer.Exit(1)
        model = None
        if local_todo:
            gpu.wait_for_gpu(typer.echo)
            model = speak.load()
        folder = recorded.GREETINGS
        client = None
        try:
            with ExitStack() as stack:
                client = stack.enter_context(eleven.ElevenLabs(key)) if key else None
                for npc in todo:
                    say: Say
                    if client is not None and engine(npc) is Engine.ELEVENLABS:
                        say = eleven.speaking(client, chosen[npc.id].voice)
                    else:
                        assert npc.voice.reference_clip is not None
                        clip = recorded.REPO_ROOT / npc.voice.reference_clip
                        say = speak.cloning(model, clip, npc.voice.reference_line)
                    spoken = record(
                        npc,
                        lines[npc.id],
                        made,
                        engine(npc),
                        chosen.get(npc.id),
                        say,
                        folder,
                        force=force,
                        audition=audition,
                    )
                    for text, length in spoken:
                        typer.echo(f"{npc.id}: {text!r} {length:.2f} s")
        except Exception as error:
            if key is None:
                raise
            typer.echo(f"Stopped: {eleven.safely(error, key)}", err=True)
            typer.echo("The greetings said so far are kept, so a rerun says the rest.", err=True)
            if client is not None:
                typer.echo(f"ElevenLabs credits used: {client.credits}", err=True)
            raise typer.Exit(1) from None
        total = sum(path.stat().st_size for path in folder.glob("*.m4a"))
        typer.echo(f"Wrote content/voices/greetings/, {total / 1024:.0f} KB in all")
        if client is not None:
            typer.echo(f"ElevenLabs credits used: {client.credits}")
