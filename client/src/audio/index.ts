import { SAMPLE_RATE, server } from '../net';
import { dialogue } from '../ui/dialogue';
import { fetchGreetings, Greeter, WebGreetings } from './greetings';
import { listen, VoicePlayer } from './player';
import { positions } from './positions';
import { resumeOnFirstGesture, WebAudioOutput } from './webaudio';

export { setPositionProvider, type PositionProvider } from './positions';

if (import.meta.env.MODE !== 'test') {
  const context = new AudioContext({ sampleRate: SAMPLE_RATE });
  const player = new VoicePlayer(new WebAudioOutput(context), positions);
  listen(server, player, () => context.state === 'running');
  resumeOnFirstGesture(context);
  const greeter = new Greeter(new WebGreetings(context), positions, fetchGreetings, {
    canPlay: () => context.state === 'running',
  });
  dialogue.onInvitation((npcId) => void greeter.greet(npcId));
  const everyFrame = () => {
    player.update();
    requestAnimationFrame(everyFrame);
  };
  requestAnimationFrame(everyFrame);

  if (import.meta.env.DEV && new URLSearchParams(location.search).has('audio-harness')) {
    void import('./harness').then(({ startHarness }) => startHarness(context, player));
  }
}
