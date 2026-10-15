from collections.abc import Callable

from typer.testing import CliRunner

from simile.cli import create_cli

MakePackage = Callable[[dict[str, str]], str]

runner = CliRunner()


def test_help_lists_serve() -> None:
    result = runner.invoke(create_cli(), ["--help"])

    assert result.exit_code == 0
    assert "serve" in result.output


def test_registers_commands_from_module_cli(make_package: MakePackage) -> None:
    package = make_package(
        {
            "alpha/cli.py": (
                "import typer\n"
                "def register(app: typer.Typer) -> None:\n"
                "    @app.command()\n"
                "    def hello() -> None:\n"
                "        print('hello from alpha')\n"
            ),
            "beta/__init__.py": "",
        }
    )

    result = runner.invoke(create_cli(package), ["hello"])

    assert result.exit_code == 0, result.output
    assert "hello from alpha" in result.output
