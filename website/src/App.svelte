<script>
  import svelteLogo from './assets/svelte.svg'
  import viteLogo from './assets/vite.svg'
  import heroImg from './assets/hero.png'
  import Counter from './lib/Counter.svelte'
  import { AnimatedBeam } from '@/lib/components/magic/animated-beam'
  import { TextAnimate } from '@/lib/components/magic/text-animate'

  let beamContainerRef
  let beamFromRef
  let beamToRef
</script>

<section id="center">
  <div class="hero">
    <img src={heroImg} class="base" width="170" height="179" alt="" />
    <img src={svelteLogo} class="framework" alt="Svelte logo" />
    <img src={viteLogo} class="vite" alt="Vite logo" />
  </div>
  <div>
    <h1>Get started</h1>
    <p>Edit <code>src/App.svelte</code> and save to test <code>HMR</code></p>
  </div>
  <div class="animate-in fade-in zoom-in-95 slide-in-from-bottom-3 duration-500 rounded-xl border border-zinc-300/60 bg-white/80 px-4 py-2 text-sm font-medium text-zinc-800 shadow-sm dark:border-zinc-700/70 dark:bg-zinc-900/70 dark:text-zinc-100">
    Tailwind + tw-animate-css is active ✅
  </div>

  <TextAnimate
    content="Hello from Text Animate"
    animation="blurInUp"
    by="word"
    class="text-center text-2xl font-semibold text-zinc-900 dark:text-zinc-100"
  />

  <div
    bind:this={beamContainerRef}
    class="relative flex w-full max-w-md items-center justify-between rounded-xl border border-zinc-300/60 bg-white/70 px-10 py-8 dark:border-zinc-700/70 dark:bg-zinc-900/60"
  >
    <div bind:this={beamFromRef} class="z-10 rounded-full border border-zinc-300 bg-zinc-100 px-3 py-1 text-xs font-medium dark:border-zinc-700 dark:bg-zinc-800">Input</div>
    <div bind:this={beamToRef} class="z-10 rounded-full border border-zinc-300 bg-zinc-100 px-3 py-1 text-xs font-medium dark:border-zinc-700 dark:bg-zinc-800">Output</div>

    <AnimatedBeam
      containerRef={beamContainerRef}
      fromRef={beamFromRef}
      toRef={beamToRef}
      curvature={40}
      duration={3}
      pathColor="rgb(161 161 170)"
      gradientStartColor="#22d3ee"
      gradientStopColor="#a855f7"
    />
  </div>

  <Counter />
</section>

<div class="ticks"></div>

<section id="next-steps">
  <div id="docs">
    <svg class="icon" role="presentation" aria-hidden="true">
      <use href="/icons.svg#documentation-icon"></use>
    </svg>
    <h2>Documentation</h2>
    <p>Your questions, answered</p>
    <ul>
      <li>
        <a href="https://vite.dev/" target="_blank" rel="noreferrer">
          <img class="logo" src={viteLogo} alt="" />
          Explore Vite
        </a>
      </li>
      <li>
        <a href="https://svelte.dev/" target="_blank" rel="noreferrer">
          <img class="button-icon" src={svelteLogo} alt="" />
          Learn more
        </a>
      </li>
    </ul>
  </div>
  <div id="social">
    <svg class="icon" role="presentation" aria-hidden="true">
      <use href="/icons.svg#social-icon"></use>
    </svg>
    <h2>Connect with us</h2>
    <p>Join the Vite community</p>
    <ul>
      <li>
        <a href="https://github.com/vitejs/vite" target="_blank" rel="noreferrer">
          <svg class="button-icon" role="presentation" aria-hidden="true">
            <use href="/icons.svg#github-icon"></use>
          </svg>
          GitHub
        </a>
      </li>
      <li>
        <a href="https://chat.vite.dev/" target="_blank" rel="noreferrer">
          <svg class="button-icon" role="presentation" aria-hidden="true">
            <use href="/icons.svg#discord-icon"></use>
          </svg>
          Discord
        </a>
      </li>
      <li>
        <a href="https://x.com/vite_js" target="_blank" rel="noreferrer">
          <svg class="button-icon" role="presentation" aria-hidden="true">
            <use href="/icons.svg#x-icon"></use>
          </svg>
          X.com
        </a>
      </li>
      <li>
        <a href="https://bsky.app/profile/vite.dev" target="_blank" rel="noreferrer">
          <svg class="button-icon" role="presentation" aria-hidden="true">
            <use href="/icons.svg#bluesky-icon"></use>
          </svg>
          Bluesky
        </a>
      </li>
    </ul>
  </div>
</section>

<div class="ticks"></div>
<section id="spacer"></section>
