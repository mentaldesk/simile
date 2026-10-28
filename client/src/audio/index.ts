import { SAMPLE_RATE, server } from '../net';
import { attackerOf } from '../side/attacker';
import { dialogue } from '../ui/dialogue';
import { fetchGreetings, Greeter, WebGreetings } from './greetings';
import { playHurts, webSound } from './hurt-sound';
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
  playHurts(webSound(context), () => context.state === 'running', () => attackerOf(positions.listenerPosition())?.creature.kind);
  const everyFrame = () => {
    player.update();
    requestAnimationFrame(everyFrame);
  };
  requestAnimationFrame(everyFrame);

  if (import.meta.env.DEV && new URLSearchParams(location.search).has('audio-harness')) {
    void import('./harness').then(({ startHarness }) => startHarness(context, player));
  }
}
