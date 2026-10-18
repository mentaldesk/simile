from simile.characters.tables import Tables, load_tables
from simile.characters.tables.load import Job

RETIRED = "retired "


def job_of(occupation: str, tables: Tables | None = None) -> Job | None:
    """Their job in occupations.toml or makers.toml, or the one they retired from."""
    t = tables or load_tables()
    return t.job(occupation.casefold().removeprefix(RETIRED))


def retired(occupation: str) -> bool:
    return occupation.casefold().startswith(RETIRED)


def student(occupation: str, tables: Tables | None = None) -> bool:
    t = tables or load_tables()
    title = occupation.casefold()
    return any(
        title == study.casefold().removeprefix("an ").removeprefix("a ")
        for row in t.occupations.study
        for study in row.titles
    )


def family(occupation: str, tables: Tables | None = None) -> str:
    """The makers.toml family or ISCO-08 sub-major group of their job, past or present, else
    `student`, else their occupation as it is."""
    t = tables or load_tables()
    if job := job_of(occupation, t):
        return job.group
    return "student" if student(occupation, t) else occupation.casefold()


def maker(occupation: str, tables: Tables | None = None) -> bool:
    """Whether they work at a job from makers.toml."""
    job = job_of(occupation, tables)
    return job is not None and job.maker and not retired(occupation)


def trade(occupation: str, tables: Tables | None = None) -> bool:
    """Whether they work at, or retired from, a job in occupations.toml."""
    job = job_of(occupation, tables)
    return job is not None and not job.maker


def makes_or_studies(occupation: str, tables: Tables | None = None) -> bool:
    """A job from makers.toml, one in occupations.toml marked `makes`, past or present, or a
    student."""
    job = job_of(occupation, tables)
    return job.makes if job else student(occupation, tables)
