from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from simile.jobs import Busy, Finished, Job, Jobs, State, UnknownKind
from simile.jobs.runner import CONTENT

from .conftest import Fake, fake_kind, gone, until

pytestmark = pytest.mark.anyio


def jobs_with(root: Path, *kinds: str, **options: Any) -> Jobs:
    jobs = Jobs(root, {}, **options)
    for name in kinds or ("fake",):
        jobs.register(fake_kind(name))
    return jobs


def current(jobs: Jobs, job_id: str) -> Job:
    job = jobs.get(job_id)
    assert job is not None
    return job


def state(jobs: Jobs, job_id: str) -> State:
    return current(jobs, job_id).state


async def test_reports_progress_then_publishes_the_result(root: Path, tmp_path: Path) -> None:
    jobs = jobs_with(root)
    hold = tmp_path / "hold"
    job = jobs.submit("fake", {"name": "sheet", "hold": str(hold)})

    await until(lambda: current(jobs, job.id).progress == 0.5)
    running = current(jobs, job.id)
    hold.touch()
    seen = [update async for update in jobs.watch(job.id)]

    assert job.state is State.QUEUED
    assert running.state is State.RUNNING
    assert running.message == "Halfway" and running.started is not None
    assert seen[-1].state is State.SUCCEEDED
    assert seen[-1].progress == 1.0 and seen[-1].message == "Done"
    assert seen[-1].result == {"file": "/api/jobs/files/fake/sheet.txt"}
    assert (root / "fake" / "sheet.txt").read_text() == "sheet"
    assert jobs.file("fake", "sheet.txt") == root / "fake" / "sheet.txt"
    assert not any((root / "work").iterdir())


async def test_cancels_a_running_job_and_everything_it_started(root: Path, tmp_path: Path) -> None:
    jobs = jobs_with(root)
    pid, child = tmp_path / "pid", tmp_path / "child"
    job = jobs.submit(
        "fake", {"hold": str(tmp_path / "never"), "pid": str(pid), "child": str(child)}
    )
    await until(pid.exists)

    cancelled = await jobs.cancel(job.id)

    assert cancelled.state is State.CANCELLED and cancelled.finished is not None
    assert gone(int(pid.read_text())) and gone(int(child.read_text()))
    assert not (root / "fake" / "out.txt").exists()
    assert not any((root / "work").iterdir())


@pytest.mark.parametrize(
    ("detach", "stubborn"),
    [(True, False), (False, False), (False, True)],
    ids=["detached", "inherited", "ignores-sigterm"],
)
async def test_ends_what_a_job_leaves_behind(
    root: Path, tmp_path: Path, detach: bool, stubborn: bool
) -> None:
    jobs = jobs_with(root, grace=0.2)
    child = tmp_path / "child"

    job = jobs.submit("fake", {"child": str(child), "detach": detach, "stubborn": stubborn})
    await until(lambda: state(jobs, job.id).finished)

    assert state(jobs, job.id) is State.SUCCEEDED
    assert gone(int(child.read_text()))


async def test_kills_a_job_that_ignores_being_asked_to_stop(root: Path, tmp_path: Path) -> None:
    jobs = jobs_with(root, grace=0.2)
    pid = tmp_path / "pid"
    job = jobs.submit("fake", {"hold": str(tmp_path / "never"), "pid": str(pid), "stubborn": True})
    await until(pid.exists)

    cancelled = await jobs.cancel(job.id)

    assert cancelled.state is State.CANCELLED
    assert gone(int(pid.read_text()))


async def test_runs_one_job_at_a_time_per_kind(root: Path, tmp_path: Path) -> None:
    jobs = jobs_with(root, "fake", "other")
    hold, second_pid = tmp_path / "hold", tmp_path / "second"
    first = jobs.submit("fake", {"name": "first", "hold": str(hold)})
    second = jobs.submit("fake", {"name": "second", "pid": str(second_pid)})
    other = jobs.submit("other", {})

    await until(lambda: state(jobs, other.id) is State.SUCCEEDED)
    assert state(jobs, first.id) is State.RUNNING
    assert state(jobs, second.id) is State.QUEUED
    assert not second_pid.exists()

    hold.touch()
    await until(lambda: state(jobs, second.id) is State.SUCCEEDED)
    assert state(jobs, first.id) is State.SUCCEEDED


async def test_cancels_a_queued_job_before_it_starts(root: Path, tmp_path: Path) -> None:
    jobs = jobs_with(root)
    hold, pid = tmp_path / "hold", tmp_path / "pid"
    first = jobs.submit("fake", {"hold": str(hold)})
    queued = jobs.submit("fake", {"name": "queued", "pid": str(pid)})

    cancelled = await jobs.cancel(queued.id)
    hold.touch()
    await until(lambda: state(jobs, first.id) is State.SUCCEEDED)

    assert cancelled.state is State.CANCELLED and cancelled.started is None
    assert not pid.exists()


async def test_cancelling_a_finished_job_is_refused(root: Path) -> None:
    jobs = jobs_with(root)
    job = jobs.submit("fake", {})
    await until(lambda: state(jobs, job.id).finished)

    with pytest.raises(Finished):
        await jobs.cancel(job.id)
    with pytest.raises(KeyError):
        await jobs.cancel("nope")


async def test_fails_at_once_with_a_clear_reason_when_a_tool_is_missing(root: Path) -> None:
    jobs = Jobs(root, {"blender": False, "apple_silicon": True})

    def never(fake: Fake, work: Path) -> list[str]:
        raise AssertionError("started a job this machine can't run")

    jobs.register(fake_kind("render", requires=("blender", "apple_silicon"), command=never))

    job = jobs.submit("render", {})

    reason = (
        "render jobs need Blender (install it or set $BLENDER), which this machine doesn't have"
    )
    assert job.state is State.FAILED and job.error == reason
    assert jobs.capabilities() == {
        "machine": {"blender": False, "apple_silicon": True},
        "kinds": {"render": {"available": False, "reason": reason}},
    }
    assert not root.exists()


async def test_fails_clearly_when_the_tool_cant_start(root: Path) -> None:
    jobs = Jobs(root, {})
    jobs.register(fake_kind(command=lambda fake, work: ["/no/such/tool", str(work)]))

    job = jobs.submit("fake", {})
    await until(lambda: state(jobs, job.id).finished)

    failed = current(jobs, job.id)
    assert failed.state is State.FAILED
    assert failed.error == "couldn't start /no/such/tool: No such file or directory"


async def test_fails_with_the_tools_last_words(root: Path) -> None:
    jobs = jobs_with(root)
    noise = ["Traceback (most recent call last):", "JOB not json", 'JOB {"progress": NaN}', "Boom"]

    job = jobs.submit("fake", {"noise": noise, "exit": 3})
    await until(lambda: state(jobs, job.id).finished)

    failed = current(jobs, job.id)
    assert failed.state is State.FAILED
    assert failed.error == "the fake job exited with code 3\n" + "\n".join(noise)
    assert failed.result is None
    assert not (root / "fake" / "out.txt").exists()


async def test_keeps_only_the_start_of_a_long_line(root: Path) -> None:
    jobs = jobs_with(root)

    job = jobs.submit("fake", {"noise": ["x" * 200_000, "Boom"], "exit": 1})
    await until(lambda: state(jobs, job.id).finished)

    error = current(jobs, job.id).error
    assert error == "the fake job exited with code 1\n" + "x" * 4096 + "\nBoom"


async def test_refuses_bad_params_and_unknown_kinds(root: Path) -> None:
    jobs = jobs_with(root)

    with pytest.raises(ValidationError):
        jobs.submit("fake", {"exit": "lots"})
    with pytest.raises(UnknownKind):
        jobs.submit("nope", {})
    assert jobs.list() == []


async def test_limits_how_many_jobs_of_a_kind_wait(root: Path, tmp_path: Path) -> None:
    jobs = jobs_with(root, "fake", "other", waiting=1)
    hold = tmp_path / "hold"
    jobs.submit("fake", {"hold": str(hold)})
    jobs.submit("fake", {"hold": str(hold)})

    with pytest.raises(Busy, match="1 fake jobs are already waiting"):
        jobs.submit("fake", {})
    jobs.submit("other", {})
    hold.touch()
    await jobs.close()


async def test_closing_cancels_every_job(root: Path, tmp_path: Path) -> None:
    jobs = jobs_with(root)
    pid = tmp_path / "pid"
    running = jobs.submit("fake", {"hold": str(tmp_path / "never"), "pid": str(pid)})
    queued = jobs.submit("fake", {})
    await until(pid.exists)

    await jobs.close()

    assert state(jobs, running.id) is State.CANCELLED
    assert state(jobs, queued.id) is State.CANCELLED
    assert gone(int(pid.read_text()))


async def test_keeps_only_the_latest_finished_jobs(root: Path) -> None:
    jobs = Jobs(root, {}, keep=2)
    jobs.register(fake_kind(requires=("blender",)))

    ids = [jobs.submit("fake", {}).id for _ in range(3)]

    assert [job.id for job in jobs.list()] == ids[1:]


def test_never_writes_inside_content(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="content"):
        Jobs(CONTENT / "art", {})
    jobs = Jobs(CONTENT.parent, {})
    with pytest.raises(ValueError, match="content"):
        jobs.register(fake_kind("content"))
    for name in ("work", "Bad", "../up"):
        with pytest.raises(ValueError):
            Jobs(tmp_path, {}).register(fake_kind(name))


async def test_serves_only_files_its_kinds_publish(root: Path, tmp_path: Path) -> None:
    jobs = jobs_with(root)
    job = jobs.submit("fake", {"name": "sheet"})
    await until(lambda: state(jobs, job.id) is State.SUCCEEDED)
    (tmp_path / "secret.txt").write_text("secret")
    (root / "fake" / "link.txt").symlink_to(tmp_path / "secret.txt")
    (root / "fake" / "notes.md").write_text("notes")

    assert jobs.file("fake", "sheet.txt") == root / "fake" / "sheet.txt"
    for kind, name in [
        ("fake", "missing.txt"),
        ("fake", "link.txt"),
        ("fake", "notes.md"),
        ("fake", "../fake/sheet.txt"),
        ("other", "sheet.txt"),
    ]:
        assert jobs.file(kind, name) is None
