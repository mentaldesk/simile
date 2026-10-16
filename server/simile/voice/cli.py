from typing import Annotated

import typer


def register(app: typer.Typer) -> None:
    voice = typer.Typer(no_args_is_help=True, help="The residents' voices.")

    @voice.command()
    def measure(
        npcs: Annotated[
            list[str] | None, typer.Argument(help="Resident ids. Defaults to all of them.")
        ] = None,
        force: Annotated[
            bool, typer.Option(help="Measure voices whose rate is up to date too.")
        ] = False,
    ) -> None:
        """Measure how fast each resident's voice speaks, into content/voices/rates.json.

        B2 and B5 pace their lines by it. Measures only the voices without an up-to-date rate,
        unless --force. Needs the voice extra (`uv sync --extra voice`), and takes a minute or
        two a voice.
        """
        from simile.npc import load_npcs
        from simile.voice.measure import measure as measure_voice
        from simile.voice.rates import load_rates, outdated, save_rates

        residents = {npc.id: npc for npc in load_npcs()}
        if unknown := sorted(set(npcs or ()) - residents.keys()):
            raise typer.BadParameter(f"no such resident: {', '.join(unknown)}", param_hint="NPCS")
        measured = load_rates()
        rates = {
            id: rate
            for id, rate in measured.items()
            if id in residents and residents[id].voice.reference_clip is not None
        }
        chosen = [residents[id] for id in npcs] if npcs else list(residents.values())
        voiced = [npc for npc in chosen if npc.voice.reference_clip is not None]
        todo = voiced if force else outdated(voiced, rates)
        if unvoiced := [npc.id for npc in chosen if npc.voice.reference_clip is None]:
            typer.echo(f"No voice yet, so no rate: {', '.join(unvoiced)}")
        if not todo:
            if rates != measured:
                save_rates(rates)
            typer.echo("Every rate is up to date. --force measures them again.")
            return
        try:
            from simile.voice.qwen import QwenSynthesiser
        except ImportError:
            typer.echo("Measuring needs the voice extra: uv sync --extra voice", err=True)
            raise typer.Exit(1) from None

        synthesiser = QwenSynthesiser(seed=0)
        synthesiser.load()
        for npc in todo:
            measurement = measure_voice(synthesiser, npc)
            rates[npc.id] = rate = measurement.rate
            save_rates(rates)
            typer.echo(
                f"{npc.id}: {rate.base_seconds:.2f} s + {rate.seconds_per_word:.3f} s a word "
                f"(rms error {measurement.error:.2f} s)"
            )
        typer.echo("Wrote content/voices/rates.json")

    app.add_typer(voice, name="voice")
