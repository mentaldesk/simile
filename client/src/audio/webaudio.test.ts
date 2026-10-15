import { expect, it, vi } from 'vitest';
import { resumeOnFirstGesture } from './webaudio';

it('resumes the audio on the first key press, then stops listening', async () => {
  const page = new EventTarget();
  const context = { resume: vi.fn(() => Promise.resolve()) };
  resumeOnFirstGesture(context, page);
  expect(context.resume).not.toHaveBeenCalled();

  page.dispatchEvent(new Event('keydown'));
  expect(context.resume).toHaveBeenCalledOnce();
  await Promise.resolve();
  page.dispatchEvent(new Event('keydown'));
  page.dispatchEvent(new Event('pointerdown'));

  expect(context.resume).toHaveBeenCalledOnce();
});

it('tries again on the next gesture if the browser refuses', async () => {
  const page = new EventTarget();
  const context = { resume: vi.fn(() => Promise.reject(new Error('not allowed'))) };
  resumeOnFirstGesture(context, page);

  page.dispatchEvent(new Event('pointerdown'));
  await Promise.resolve();
  page.dispatchEvent(new Event('keydown'));

  expect(context.resume).toHaveBeenCalledTimes(2);
});
