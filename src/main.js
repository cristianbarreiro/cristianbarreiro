import lottie from 'lottie-web';
import './style.css';

const container = document.querySelector('#lottie-animation');
const toggleButton = document.querySelector('#toggle-animation');
const restartButton = document.querySelector('#restart-animation');
const status = document.querySelector('#animation-status');
const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');

const animation = lottie.loadAnimation({
  container,
  renderer: 'svg',
  loop: !reducedMotion.matches,
  autoplay: !reducedMotion.matches,
  path: '/animations/technology-orbit.json',
  rendererSettings: {
    preserveAspectRatio: 'xMidYMid meet',
    progressiveLoad: true,
  },
});

let isPlaying = !reducedMotion.matches;

animation.addEventListener('DOMLoaded', () => {
  status.textContent = reducedMotion.matches
    ? 'Animation is paused to respect your reduced-motion preference.'
    : 'Animation loaded and playing.';
});

animation.addEventListener('data_failed', () => {
  status.textContent = 'The animation could not be loaded. Check that the local JSON file is available.';
  toggleButton.disabled = true;
  restartButton.disabled = true;
});

toggleButton.addEventListener('click', () => {
  if (isPlaying) {
    animation.pause();
    toggleButton.textContent = 'Play animation';
    toggleButton.setAttribute('aria-pressed', 'true');
    status.textContent = 'Animation paused.';
  } else {
    animation.play();
    toggleButton.textContent = 'Pause animation';
    toggleButton.setAttribute('aria-pressed', 'false');
    status.textContent = 'Animation playing.';
  }

  isPlaying = !isPlaying;
});

restartButton.addEventListener('click', () => {
  animation.goToAndPlay(0, true);
  isPlaying = true;
  toggleButton.textContent = 'Pause animation';
  toggleButton.setAttribute('aria-pressed', 'false');
  status.textContent = 'Animation restarted.';
});

reducedMotion.addEventListener('change', ({ matches }) => {
  if (matches && isPlaying) {
    animation.pause();
    isPlaying = false;
    toggleButton.textContent = 'Play animation';
    toggleButton.setAttribute('aria-pressed', 'true');
    status.textContent = 'Animation paused to respect your reduced-motion preference.';
  }
});

window.addEventListener('pagehide', () => animation.destroy(), { once: true });
