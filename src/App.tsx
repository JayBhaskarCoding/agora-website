import { useEffect, useRef, useState, type ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ArrowDownRight, ArrowRight, Check, ChevronDown, Globe2, Layers3, LockKeyhole, Menu, Orbit, Radio, Terminal, Users, Waves, X, Zap } from 'lucide-react';
import { ErrorBoundary } from '@/components/error-boundary';
import { Toaster } from '@/components/ui/toaster';
import { TooltipProvider } from '@/components/ui/tooltip';
import NotFound from '@/pages/not-found';
import { Link, Route, Switch, Router as WouterRouter, useLocation } from 'wouter';

declare global {
  interface Window {
    THREE?: any;
    gsap?: any;
    ScrollTrigger?: any;
  }
}

const queryClient = new QueryClient();
const prefersReducedMotion = () => typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
let audioContext: AudioContext | null = null;
let masterGain: GainNode | null = null;
const EARLY_ACCESS_LINES = [
  '==================================================',
  '              AGORA: EARLY ACCESS',
  '==================================================',
  '',
  'You found the secret door.',
  '',
  'Thank you for requesting early access to Agora. We are currently putting the finishing touches on our Android app.',
  '',
  'Because you arrived before the public launch, your device is officially flagged for priority onboarding when our v1.0 release drops.',
  '',
  'Stay tuned. The public square is about to change.',
  '',
  '- The Agora Team',
  'https://www.auth-agora.info',
  '==================================================',
  '',
  'If you would like to support the progress of this project. You may contact: mail@auth-agora.info',
  '',
  'Your help is truly appreciated.',
];

function startAtmosphere() {
  if (prefersReducedMotion() || typeof window === 'undefined') return;
  if (!audioContext) {
    audioContext = new AudioContext();
    masterGain = audioContext.createGain();
    masterGain.gain.setValueAtTime(0, audioContext.currentTime);
    masterGain.gain.linearRampToValueAtTime(0.035, audioContext.currentTime + 1.8);
    masterGain.connect(audioContext.destination);
    const bass = audioContext.createOscillator();
    const air = audioContext.createOscillator();
    const bassGain = audioContext.createGain();
    const airGain = audioContext.createGain();
    bass.type = 'sine';
    air.type = 'sine';
    bass.frequency.value = 58.27;
    air.frequency.value = 116.54;
    bassGain.gain.value = 0.24;
    airGain.gain.value = 0.035;
    bass.connect(bassGain).connect(masterGain);
    air.connect(airGain).connect(masterGain);
    bass.start();
    air.start();
  }
  if (audioContext.state === 'suspended') void audioContext.resume();
}

function hoverHarmonic() {
  if (!audioContext || !masterGain || prefersReducedMotion()) return;
  const oscillator = audioContext.createOscillator();
  const gain = audioContext.createGain();
  const now = audioContext.currentTime;
  oscillator.type = 'sine';
  oscillator.frequency.setValueAtTime(392, now);
  oscillator.frequency.exponentialRampToValueAtTime(523.25, now + 0.16);
  gain.gain.setValueAtTime(0.0001, now);
  gain.gain.exponentialRampToValueAtTime(0.015, now + 0.02);
  gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.22);
  oscillator.connect(gain).connect(masterGain);
  oscillator.start(now);
  oscillator.stop(now + 0.24);
}

function useAmbientAudio() {
  useEffect(() => {
    const begin = () => startAtmosphere();
    window.addEventListener('pointerdown', begin, { once: true });
    window.addEventListener('keydown', begin, { once: true });
    return () => {
      window.removeEventListener('pointerdown', begin);
      window.removeEventListener('keydown', begin);
    };
  }, []);
}

function useReveal<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  useEffect(() => {
    if (!ref.current || prefersReducedMotion()) {
      ref.current?.classList.add('is-visible');
      return;
    }
    const observer = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) {
        entry.target.classList.add('is-visible');
        observer.disconnect();
      }
    }, { threshold: 0.14 });
    observer.observe(ref.current);
    return () => observer.disconnect();
  }, []);
  return ref;
}

function TransitionLink({ href, children, className, onNavigate }: { href: string; children: ReactNode; className?: string; onNavigate?: () => void }) {
  const [, setLocation] = useLocation();
  const handleClick = (event: any) => {
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    onNavigate?.();
    if (prefersReducedMotion()) {
      setLocation(href);
      return;
    }
    const transitionLayer = document.querySelector('.agora-transition-layer');
    if (window.gsap && transitionLayer) {
      window.gsap.killTweensOf(transitionLayer);
      window.gsap.to(transitionLayer, { opacity: 1, duration: 0.22, ease: 'power3.in' });
    }
    document.documentElement.classList.add('is-transitioning');
    window.setTimeout(() => {
      setLocation(href);
      window.setTimeout(() => {
        document.documentElement.classList.remove('is-transitioning');
        if (window.gsap && transitionLayer) window.gsap.to(transitionLayer, { opacity: 0, duration: 0.36, ease: 'power2.out' });
      }, 80);
    }, 260);
  };
  return <Link href={href} onClick={handleClick} className={className}>{children}</Link>;
}

function GlowButton({ children, onClick, className = '', type = 'button', testId }: { children: ReactNode; onClick?: () => void; className?: string; type?: 'button' | 'submit'; testId: string }) {
  return (
    <button type={type} data-testid={testId} onClick={onClick} onMouseEnter={hoverHarmonic} className={`agora-glow group inline-flex items-center justify-center gap-3 rounded-full border border-cyan-200/30 bg-cyan-100 px-5 py-3 text-sm font-semibold text-slate-950 transition-transform duration-300 hover:-translate-y-0.5 hover:bg-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-200 ${className}`}>
      {children}
    </button>
  );
}

function ThreeSurface() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const canvas = canvasRef.current;
    const THREE = window.THREE;
    if (!canvas || !THREE) return;
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(36, 1, 0.1, 100);
    camera.position.set(0, 4.3, 7.2);
    camera.lookAt(0, 0, 0);
    const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    const group = new THREE.Group();
    scene.add(group);
    const size = 22;
    const divisions = 20;
    const positions = new Float32Array((divisions + 1) * divisions * 4 * 3);
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    const material = new THREE.LineBasicMaterial({ color: 0x62d9cd, transparent: true, opacity: 0.42 });
    const lines = new THREE.LineSegments(geometry, material);
    group.add(lines);
    const pointer = { x: 0, y: 0 };
    const target = { x: 0, y: 0 };
    const onPointer = (event: PointerEvent) => {
      target.x = (event.clientX / window.innerWidth - 0.5) * 0.7;
      target.y = (event.clientY / window.innerHeight - 0.5) * 0.42;
    };
    window.addEventListener('pointermove', onPointer, { passive: true });
    const resize = () => {
      const parent = canvas.parentElement;
      if (!parent) return;
      const width = parent.clientWidth;
      const height = parent.clientHeight;
      renderer.setSize(width, height, false);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
    };
    resize();
    window.addEventListener('resize', resize);
    let frame = 0;
    const render = (time: number) => {
      const t = time * 0.00034;
      const positionsArray = geometry.attributes.position.array as Float32Array;
      let index = 0;
      const point = (x: number, z: number) => {
        const wave = Math.sin(x * 1.18 + t) * 0.22 + Math.cos(z * 1.08 - t * 1.2) * 0.18;
        const swell = Math.exp(-((x - pointer.x * 3) ** 2 + (z + pointer.y * 3) ** 2) / 8) * 0.22;
        return wave + swell;
      };
      for (let i = 0; i <= divisions; i += 1) {
        const x = (i / divisions - 0.5) * size;
        for (let j = 0; j < divisions; j += 1) {
          const z1 = (j / divisions - 0.5) * size;
          const z2 = ((j + 1) / divisions - 0.5) * size;
          positionsArray[index++] = x; positionsArray[index++] = point(x, z1); positionsArray[index++] = z1;
          positionsArray[index++] = x; positionsArray[index++] = point(x, z2); positionsArray[index++] = z2;
        }
      }
      for (let j = 0; j <= divisions; j += 1) {
        const z = (j / divisions - 0.5) * size;
        for (let i = 0; i < divisions; i += 1) {
          const x1 = (i / divisions - 0.5) * size;
          const x2 = ((i + 1) / divisions - 0.5) * size;
          positionsArray[index++] = x1; positionsArray[index++] = point(x1, z); positionsArray[index++] = z;
          positionsArray[index++] = x2; positionsArray[index++] = point(x2, z); positionsArray[index++] = z;
        }
      }
      geometry.attributes.position.needsUpdate = true;
      pointer.x += (target.x - pointer.x) * 0.035;
      pointer.y += (target.y - pointer.y) * 0.035;
      group.rotation.x += ((-0.16 + pointer.y * 0.1) - group.rotation.x) * 0.025;
      group.rotation.y += ((pointer.x * 0.1) - group.rotation.y) * 0.025;
      renderer.render(scene, camera);
      frame = requestAnimationFrame(render);
    };
    frame = requestAnimationFrame(render);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener('resize', resize);
      window.removeEventListener('pointermove', onPointer);
      geometry.dispose();
      material.dispose();
      renderer.dispose();
    };
  }, []);
  return <canvas ref={canvasRef} aria-hidden="true" className="absolute inset-0 h-full w-full opacity-80" />;
}

function NoiseIntro() {
  const [progress, setProgress] = useState(0);
  useEffect(() => {
    if (prefersReducedMotion()) {
      setProgress(1);
      return;
    }
    const gsap = window.gsap;
    const ScrollTrigger = window.ScrollTrigger;
    if (gsap && ScrollTrigger) {
      gsap.registerPlugin(ScrollTrigger);
      const scrubber = { value: Math.min(window.scrollY / 340, 1) };
      const tween = gsap.to(scrubber, {
        value: 1,
        ease: 'none',
        scrollTrigger: {
          trigger: document.body,
          start: 'top top',
          end: '340 top',
          scrub: 0.7,
        },
        onUpdate: () => setProgress(scrubber.value),
      });
      setProgress(scrubber.value);
      return () => {
        tween.scrollTrigger?.kill();
        tween.kill();
      };
    }
    const onScroll = () => setProgress(Math.min(window.scrollY / 340, 1));
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);
  return (
    <div aria-hidden="true" className="agora-threshold pointer-events-none fixed inset-0 z-30 overflow-hidden" style={{ opacity: Math.max(0, 1 - progress) }}>
      <div className="agora-threshold-glow absolute inset-0" />
      <div className="agora-threshold-grid absolute inset-0 opacity-50" />
      <div className="agora-orbit agora-orbit-one" />
      <div className="agora-orbit agora-orbit-two" />
      <div className="agora-orbit agora-orbit-three" />
      <div className="absolute inset-0 z-10 flex items-center justify-center px-6 text-center" style={{ opacity: Math.max(0, 1 - progress * 1.8), transform: `translateY(${-progress * 30}px)` }}>
        <div className="relative z-10">
          <div className="agora-signal-pulse mx-auto mb-8 flex h-12 w-12 items-center justify-center rounded-full border border-cyan-200/40">
            <span className="h-2 w-2 rounded-full bg-emerald-300 shadow-[0_0_24px_rgba(110,231,183,.9)]" />
          </div>
          <p className="font-mono-agora text-[10px] uppercase tracking-[.34em] text-cyan-200/70">a quieter signal / agora 01</p>
          <p className="mt-5 max-w-3xl text-3xl font-medium tracking-[-.05em] text-slate-100 sm:text-6xl">Leave the feed.<br /><span className="text-cyan-200">Enter the square.</span></p>
          <p className="mt-7 font-mono-agora text-[10px] uppercase tracking-[.2em] text-slate-500">scroll to enter</p>
        </div>
      </div>
    </div>
  );
}

function TerminalAccess({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [email, setEmail] = useState('');
  const [step, setStep] = useState<'input' | 'auth' | 'output'>('input');
  const [visibleLines, setVisibleLines] = useState(0);
  useEffect(() => {
    if (!open) {
      setStep('input');
      setEmail('');
      setVisibleLines(0);
    }
  }, [open]);
  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [open, onClose]);
  useEffect(() => {
    if (!open || step !== 'auth') return;
    const outputTimer = window.setTimeout(() => setStep('output'), 1450);
    return () => window.clearTimeout(outputTimer);
  }, [open, step]);
  useEffect(() => {
    if (!open || step !== 'output') return;
    if (prefersReducedMotion()) {
      setVisibleLines(EARLY_ACCESS_LINES.length);
      return;
    }
    setVisibleLines(0);
    const lineTimer = window.setInterval(() => {
      setVisibleLines((current) => {
        if (current >= EARLY_ACCESS_LINES.length) {
          window.clearInterval(lineTimer);
          return current;
        }
        return current + 1;
      });
    }, 58);
    return () => window.clearInterval(lineTimer);
  }, [open, step]);
  if (!open) return null;
  const submit = (event: any) => {
    event.preventDefault();
    if (email.trim()) setStep('auth');
  };
  return (
    <div role="dialog" aria-modal="true" aria-labelledby="terminal-title" className="terminal-reveal fixed inset-0 z-50 flex bg-[#020611]/90 backdrop-blur-md">
      <div className="terminal-context hidden flex-1 flex-col justify-between border-r border-cyan-200/10 p-10 lg:flex xl:p-16">
        <div>
          <span className="font-mono-agora text-[10px] uppercase tracking-[.24em] text-cyan-200/60">signal intercepted / 01</span>
          <h2 className="mt-8 max-w-md text-5xl font-medium leading-[.95] tracking-[-.06em] text-slate-100 xl:text-7xl">There is still a quiet door.</h2>
        </div>
        <div className="flex items-center gap-3 font-mono-agora text-[10px] uppercase tracking-[.2em] text-emerald-300/70"><span className="h-1.5 w-1.5 rounded-full bg-emerald-300" />priority channel open</div>
      </div>
      <div className="terminal-modal w-full max-w-3xl overflow-hidden lg:flex-1">
        <div className="flex items-center justify-between border-b border-slate-700/60 px-5 py-3 font-mono-agora text-[10px] uppercase tracking-[.18em] text-slate-500 sm:px-8">
          <span id="terminal-title" className="flex items-center gap-2"><Terminal size={13} /> agora.priority_access</span>
          <button type="button" data-testid="button-close-terminal" aria-label="Close priority access terminal" onClick={onClose} className="rounded-md p-1 text-slate-500 transition-colors hover:text-cyan-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-200"><X size={16} /></button>
        </div>
        <div className="min-h-[min(680px,calc(100vh-90px))] p-6 font-mono-agora text-sm sm:p-10">
          <div className="flex gap-2 text-emerald-300"><span>agora@local</span><span className="text-slate-600">:</span><span className="text-cyan-200">~</span><span className="text-slate-600">$</span><span>{step === 'input' ? 'connect' : 'authorize --priority'}</span></div>
          <div className="mt-7 space-y-3 leading-relaxed text-slate-300">
            {step === 'input' && <>
              <p className="agora-fade-up">You found the quiet door.</p>
              <p className="agora-fade-up agora-fade-up-delay-1 text-slate-500">Agora is opening in small, deliberate circles.</p>
              <form onSubmit={submit} className="mt-8 space-y-4">
                <label htmlFor="terminal-email" className="block text-slate-400">Enter an email for the first signal.</label>
                <div className="flex flex-col gap-3 sm:flex-row">
                  <div className="flex flex-1 items-center rounded-lg border border-slate-700 bg-slate-950/60 px-3 focus-within:border-cyan-200/70">
                    <span className="mr-2 text-cyan-200">$</span>
                    <input id="terminal-email" data-testid="input-terminal-email" autoFocus type="email" required value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@somewhere.com" className="w-full bg-transparent py-3 text-slate-100 outline-none placeholder:text-slate-700" />
                    <span className="agora-cursor text-cyan-200">▌</span>
                  </div>
                  <GlowButton type="submit" testId="button-terminal-continue" className="rounded-lg px-5 font-mono-agora text-xs">send signal <ArrowRight size={14} /></GlowButton>
                </div>
              </form>
            </>}
            {step === 'auth' && <div className="terminal-status mt-10 space-y-4 text-emerald-300">
              <p><span className="terminal-dot" />resolving session / {email}</p>
              <p><span className="terminal-dot terminal-dot-delay-1" />authenticating with Supabase edge</p>
              <p><span className="terminal-dot terminal-dot-delay-2" />flagging device for priority onboarding</p>
            </div>}
            {step === 'output' && <div className="terminal-output mt-8 max-h-[min(560px,70vh)] overflow-y-auto whitespace-pre-wrap text-[11px] leading-[1.65] text-slate-300 sm:text-xs">{EARLY_ACCESS_LINES.slice(0, visibleLines).map((line, index) => <div key={`${line}-${index}`} className="terminal-line">{line || '\u00a0'}</div>)}{visibleLines < EARLY_ACCESS_LINES.length && <span className="agora-cursor text-cyan-200">▌</span>}</div>}
          </div>
        </div>
        <div className="border-t border-slate-700/60 px-6 py-3 font-mono-agora text-[9px] uppercase tracking-[.18em] text-slate-600">simulated Supabase priority onboarding / no password required</div>
      </div>
    </div>
  );
}

function SiteShell({ children }: { children: ReactNode }) {
  const [location] = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);
  const [terminalOpen, setTerminalOpen] = useState(false);
  useAmbientAudio();
  useEffect(() => {
    let typed = '';
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      if (event.key.length === 1 && /[a-z]/i.test(event.key)) {
        typed = `${typed}${event.key.toUpperCase()}`.slice(-5);
        if (typed === 'AGORA') {
          setTerminalOpen(true);
          typed = '';
        }
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, []);
  const openTerminal = () => { setTerminalOpen(true); setMenuOpen(false); };
  const navClass = (path: string) => `relative py-2 text-xs uppercase tracking-[.16em] transition-colors ${location === path ? 'text-cyan-200' : 'text-slate-500 hover:text-slate-100'}`;
  return (
    <div className="agora-app">
      <header className="fixed left-0 right-0 top-0 z-40 border-b border-white/[.06] bg-[#030712]/72 backdrop-blur-xl">
        <div className="mx-auto flex h-[72px] max-w-[1400px] items-center justify-between px-5 sm:px-8 lg:px-12">
          <TransitionLink href="/" className="group flex items-center gap-3" onNavigate={() => setMenuOpen(false)}>
            <span className="relative flex h-8 w-8 items-center justify-center rounded-full border border-cyan-200/45 text-cyan-200"><Orbit size={17} strokeWidth={1.4} /><span className="absolute h-1 w-1 rounded-full bg-emerald-300" /></span>
            <span className="text-sm font-semibold tracking-[.28em] text-slate-100">AGORA</span>
          </TransitionLink>
          <nav className="hidden items-center gap-8 md:flex" aria-label="Main navigation">
            <TransitionLink href="/" className={navClass('/')}>The square</TransitionLink>
            <TransitionLink href="/features" className={navClass('/features')}>Principles</TransitionLink>
            <button type="button" data-testid="button-open-terminal-nav" onClick={openTerminal} onMouseEnter={hoverHarmonic} className="group inline-flex items-center gap-2 rounded-full border border-cyan-200/30 px-4 py-2 text-xs uppercase tracking-[.16em] text-cyan-100 transition-colors hover:bg-cyan-100 hover:text-slate-950 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-200">Early access <ArrowDownRight size={14} className="transition-transform group-hover:translate-x-0.5 group-hover:translate-y-0.5" /></button>
          </nav>
          <button type="button" data-testid="button-toggle-navigation" aria-label={menuOpen ? 'Close navigation menu' : 'Open navigation menu'} aria-expanded={menuOpen} onClick={() => setMenuOpen(!menuOpen)} className="rounded-lg p-2 text-slate-300 md:hidden focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-200">{menuOpen ? <X size={20} /> : <Menu size={20} />}</button>
        </div>
        {menuOpen && <nav className="border-t border-white/[.06] bg-[#030712] px-5 py-5 md:hidden" aria-label="Mobile navigation">
          <div className="flex flex-col gap-3">
            <TransitionLink href="/" onNavigate={() => setMenuOpen(false)} className="border-b border-white/[.07] py-3 text-sm text-slate-200">The square</TransitionLink>
            <TransitionLink href="/features" onNavigate={() => setMenuOpen(false)} className="border-b border-white/[.07] py-3 text-sm text-slate-200">Principles</TransitionLink>
            <button type="button" data-testid="button-open-terminal-mobile" onClick={openTerminal} className="py-3 text-left text-sm text-cyan-200">Open priority access <ArrowRight size={15} className="ml-2 inline" /></button>
          </div>
        </nav>}
      </header>
      <main key={location} className="agora-page-in">{children}</main>
      <div className="agora-transition-layer fixed inset-0 z-[45] bg-[#030712]" aria-hidden="true" />
      <TerminalAccess open={terminalOpen} onClose={() => setTerminalOpen(false)} />
    </div>
  );
}

function SectionLabel({ children, number }: { children: ReactNode; number: string }) {
  return <div className="mb-8 flex items-center gap-3 font-mono-agora text-[10px] uppercase tracking-[.25em] text-cyan-200/70"><span>{number}</span><span className="h-px w-8 bg-cyan-200/35" /><span>{children}</span></div>;
}

function Home() {
  const manifestoRef = useReveal<HTMLElement>();
  const timelineRef = useReveal<HTMLElement>();
  const bentoRef = useReveal<HTMLElement>();
  const quoteRef = useReveal<HTMLElement>();
  return (
    <>
      <NoiseIntro />
      <section className="relative flex min-h-[100svh] items-end overflow-hidden border-b border-white/[.07] px-5 pb-12 pt-32 sm:px-8 sm:pb-16 lg:px-12">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_68%_46%,rgba(40,110,135,.16),transparent_34%),radial-gradient(circle_at_24%_80%,rgba(30,97,108,.1),transparent_26%)]" />
        <div className="absolute inset-x-0 bottom-0 h-[70%] opacity-70"><ThreeSurface /></div>
        <div className="agora-scanlines pointer-events-none absolute inset-0 opacity-30" />
        <div className="relative z-10 mx-auto w-full max-w-[1400px]">
          <div className="max-w-5xl">
            <p className="agora-fade-up mb-6 flex items-center gap-3 font-mono-agora text-[10px] uppercase tracking-[.3em] text-emerald-300"><span className="h-1.5 w-1.5 rounded-full bg-emerald-300 shadow-[0_0_12px_rgba(110,231,183,.8)]" />a different kind of public square</p>
            <h1 className="agora-fade-up agora-fade-up-delay-1 text-balance text-[clamp(3.6rem,11vw,10.7rem)] font-semibold leading-[.86] tracking-[-.085em] text-slate-50">The internet,<br /><span className="text-cyan-200">with room</span><br />to think.</h1>
            <div className="agora-fade-up agora-fade-up-delay-2 mt-10 flex max-w-xl flex-col gap-7 sm:flex-row sm:items-end sm:justify-between">
              <p className="max-w-sm text-sm leading-7 text-slate-400">Agora is a human-first digital public square. A place to encounter ideas, follow time as it happens, and leave with more than you arrived with.</p>
              <div className="flex shrink-0 items-center gap-3 font-mono-agora text-[10px] uppercase tracking-[.22em] text-slate-500"><span className="flex h-9 w-9 items-center justify-center rounded-full border border-slate-700"><ChevronDown size={14} /></span>scroll to enter</div>
            </div>
          </div>
          <div className="mt-16 flex items-center justify-between border-t border-white/[.1] pt-4 font-mono-agora text-[9px] uppercase tracking-[.22em] text-slate-600"><span>webgl field / 01</span><span className="hidden sm:block">a slower signal for a faster world</span><span>03:17:42 utc</span></div>
        </div>
      </section>

      <section ref={manifestoRef} className="agora-reveal relative mx-auto grid max-w-[1400px] gap-12 px-5 py-28 sm:px-8 sm:py-36 lg:grid-cols-[.85fr_1.15fr] lg:gap-20 lg:px-12">
        <div><SectionLabel number="01">the invitation</SectionLabel><p className="max-w-xs text-sm leading-7 text-slate-500">Not another place to perform. A place to be present.</p></div>
        <div><h2 className="max-w-4xl text-balance text-4xl font-medium leading-[1.06] tracking-[-.055em] text-slate-100 sm:text-6xl">A public square should make you more curious, not more tired.</h2><p className="mt-9 max-w-2xl text-base leading-8 text-slate-400">We are building the social layer we wish existed: spacious by default, chronological by design, and accountable to the people inside it. No tricks to keep you scrolling. Just better reasons to stay.</p><div className="mt-10 h-px max-w-2xl bg-gradient-to-r from-cyan-200/50 to-transparent" /></div>
      </section>

      <section ref={timelineRef} className="agora-reveal border-y border-white/[.07] bg-[#07101d]">
        <div className="mx-auto grid max-w-[1400px] lg:grid-cols-[.85fr_1.15fr]">
          <div className="border-b border-white/[.07] px-5 py-20 sm:px-8 lg:border-b-0 lg:border-r lg:px-12 lg:py-28"><SectionLabel number="02">the rhythm</SectionLabel><h2 className="max-w-md text-4xl font-medium tracking-[-.055em] text-slate-100 sm:text-5xl">Time, without<br /><span className="text-emerald-300">the algorithm.</span></h2><p className="mt-8 max-w-sm text-sm leading-7 text-slate-400">Absolute Chronology is a small idea with a large consequence: the newest thing is simply the newest thing.</p></div>
          <div className="px-5 py-20 sm:px-8 lg:px-16 lg:py-28">
            {[
              ['01', 'Arrive', 'See the moment you are in. No invisible queue rearranging the room.'],
              ['02', 'Follow', 'Choose a person, place, or question. Keep the thread, not the bait.'],
              ['03', 'Return', 'The square remembers what happened. Your attention stays yours.'],
            ].map(([num, title, copy], index) => <div key={num} className={`group relative flex gap-6 border-b border-white/[.09] py-7 first:pt-0 last:border-0 last:pb-0 ${index === 1 ? 'lg:pl-16' : ''}`}><span className="font-mono-agora text-[10px] tracking-[.2em] text-cyan-200/70">{num}</span><div><h3 className="text-xl text-slate-100 transition-colors group-hover:text-cyan-200">{title}</h3><p className="mt-3 max-w-md text-sm leading-7 text-slate-500">{copy}</p></div></div>)}
          </div>
        </div>
      </section>

      <section ref={bentoRef} className="agora-reveal mx-auto max-w-[1400px] px-5 py-28 sm:px-8 sm:py-36 lg:px-12">
        <div className="flex flex-col justify-between gap-8 sm:flex-row sm:items-end"><div><SectionLabel number="03">the architecture</SectionLabel><h2 className="max-w-xl text-4xl font-medium tracking-[-.055em] text-slate-100 sm:text-6xl">Less machinery.<br /><span className="text-cyan-200">More meaning.</span></h2></div><p className="max-w-xs text-sm leading-7 text-slate-500">Every surface has a job. None of them are trying to capture you.</p></div>
        <div className="mt-16 grid gap-4 md:grid-cols-12 md:grid-rows-[240px_300px]">
          <BentoCard className="md:col-span-7 md:row-span-2" icon={<Globe2 size={20} />} eyebrow="01 / the room" title="A shared surface for shared attention." copy="Small circles, open doors. Agora makes space for the nuanced, the unfinished, and the wonderfully specific." visual="room" />
          <BentoCard className="md:col-span-5" icon={<LockKeyhole size={20} />} eyebrow="02 / the promise" title="Zero Ads." copy="Your attention is not inventory. It is the point." visual="zero" />
          <BentoCard className="md:col-span-5" icon={<Users size={20} />} eyebrow="03 / the signal" title="People over metrics." copy="No counts shouting from the walls. Presence is enough." visual="signal" />
        </div>
      </section>

      <section ref={quoteRef} className="agora-reveal relative overflow-hidden border-y border-white/[.07] bg-[#07111b] px-5 py-28 sm:px-8 sm:py-40 lg:px-12"><div className="absolute -right-20 top-1/2 h-80 w-80 -translate-y-1/2 rounded-full border border-cyan-200/10 sm:h-[34rem] sm:w-[34rem]" /><div className="absolute -right-10 top-1/2 h-60 w-60 -translate-y-1/2 rounded-full border border-emerald-200/10 sm:h-[25rem] sm:w-[25rem]" /><div className="relative mx-auto max-w-[1400px]"><SectionLabel number="04">a quiet thesis</SectionLabel><blockquote className="max-w-5xl text-balance text-4xl font-medium leading-[1.08] tracking-[-.06em] text-slate-100 sm:text-6xl lg:text-8xl">“If a room is worth being in, it should not need to beg you to stay.”</blockquote><p className="mt-10 font-mono-agora text-[10px] uppercase tracking-[.2em] text-emerald-300">— the agora team, on designing for return</p></div></section>

      <section className="mx-auto max-w-[1400px] px-5 py-28 sm:px-8 sm:py-36 lg:px-12"><div className="agora-glass relative overflow-hidden rounded-3xl p-7 sm:p-12 lg:p-16"><div className="absolute right-0 top-0 h-full w-1/2 bg-[radial-gradient(circle_at_70%_40%,rgba(94,234,212,.15),transparent_52%)]" /><div className="relative grid gap-12 lg:grid-cols-[1fr_auto] lg:items-end"><div><SectionLabel number="05">the next opening</SectionLabel><h2 className="max-w-3xl text-4xl font-medium tracking-[-.06em] text-slate-100 sm:text-6xl">Bring your curiosity.<br /><span className="text-emerald-300">Leave the noise.</span></h2></div><p className="max-w-xs text-sm leading-7 text-slate-400">Early access will arrive in small waves. Type <span className="font-mono-agora text-cyan-200">AGORA</span> anywhere to find the door.</p></div></div></section>
      <Footer />
    </>
  );
}

function BentoCard({ icon, eyebrow, title, copy, visual, className }: { icon: ReactNode; eyebrow: string; title: string; copy: string; visual: 'room' | 'zero' | 'signal'; className?: string }) {
  return <article onMouseEnter={hoverHarmonic} className={`agora-glass group relative min-h-[240px] overflow-hidden rounded-2xl p-6 transition-transform duration-500 hover:-translate-y-1 sm:p-8 ${className || ''}`}><div className="absolute inset-0 opacity-0 transition-opacity duration-500 group-hover:opacity-100" style={{ background: visual === 'zero' ? 'radial-gradient(circle at 75% 20%, rgba(139,233,253,.12), transparent 42%)' : 'radial-gradient(circle at 40% 75%, rgba(110,231,183,.10), transparent 44%)' }} /><div className="relative flex h-full flex-col justify-between gap-12"><div><div className="flex items-center justify-between"><span className="text-cyan-200">{icon}</span><span className="font-mono-agora text-[9px] uppercase tracking-[.2em] text-slate-600">{eyebrow}</span></div><h3 className="mt-10 max-w-md text-2xl font-medium leading-tight tracking-[-.045em] text-slate-100 sm:text-3xl">{title}</h3><p className="mt-4 max-w-md text-sm leading-7 text-slate-500">{copy}</p></div><div className="flex items-center gap-2 text-[10px] uppercase tracking-[.2em] text-slate-600 transition-colors group-hover:text-cyan-200">explore principle <ArrowRight size={13} className="transition-transform group-hover:translate-x-1" /></div></div></article>;
}

function FeaturesPage() {
  const introRef = useReveal<HTMLElement>();
  const featureRef = useReveal<HTMLElement>();
  const detailRef = useReveal<HTMLElement>();
  return <><section ref={introRef} className="agora-reveal mx-auto max-w-[1400px] px-5 pb-28 pt-40 sm:px-8 sm:pb-40 lg:px-12"><SectionLabel number="01">the philosophy</SectionLabel><div className="grid gap-12 lg:grid-cols-[1.2fr_.8fr] lg:items-end"><h1 className="max-w-5xl text-balance text-[clamp(3.6rem,9vw,9rem)] font-semibold leading-[.88] tracking-[-.085em] text-slate-100">Designing a place<br />that <span className="text-cyan-200">doesn't</span><br />design you.</h1><p className="max-w-sm text-base leading-8 text-slate-400">Agora is not a feature list. It is a set of choices about what a public space owes the people who enter it.</p></div></section>
    <section ref={featureRef} className="agora-reveal border-y border-white/[.07] bg-[#07101d]"><div className="mx-auto grid max-w-[1400px] lg:grid-cols-2"><Principle number="01" title="Absolute Chronology" icon={<Waves size={21} />} copy="The timeline is a record, not a casino. Posts arrive in the order they were made — no engagement score, no hidden hand, no manufactured urgency." detail="The present is already interesting." /><Principle number="02" title="Zero Ads" icon={<Zap size={21} />} copy="Agora will never sell your attention back to you. No sponsored interruptions. No surveillance dressed up as relevance. The business model protects the room." detail="You are a person, not an impression." /></div></section>
    <section ref={detailRef} className="agora-reveal mx-auto max-w-[1400px] px-5 py-28 sm:px-8 sm:py-36 lg:px-12"><SectionLabel number="02">what this makes possible</SectionLabel><div className="grid gap-5 md:grid-cols-3"><DetailCard title="Follow a thought" copy="Save a question, not a streak. Return when you have something to add." icon={<Orbit size={19} />} /><DetailCard title="Find your people" copy="Interest can be a doorway without becoming a label. Build the circle slowly." icon={<Users size={19} />} /><DetailCard title="Keep your bearings" copy="A clear interface for a clear mind. Every interaction tells you where you are." icon={<Layers3 size={19} />} /></div><div className="mt-24 border-t border-white/[.09] pt-10"><div className="flex flex-col justify-between gap-6 sm:flex-row sm:items-center"><p className="max-w-xl text-2xl leading-tight tracking-[-.04em] text-slate-300">The best social product might feel less like a product.</p><span className="font-mono-agora text-[10px] uppercase tracking-[.2em] text-slate-600">agora / field notes 001</span></div></div></section><Footer /></>;
}

function Principle({ number, title, icon, copy, detail }: { number: string; title: string; icon: ReactNode; copy: string; detail: string }) {
  return <article onMouseEnter={hoverHarmonic} className="group border-b border-white/[.07] p-7 sm:p-12 lg:border-b-0 lg:border-r lg:p-16 last:border-r-0"><div className="flex items-center justify-between text-cyan-200"><span>{icon}</span><span className="font-mono-agora text-[10px] tracking-[.2em] text-slate-600">{number}</span></div><h2 className="mt-20 max-w-md text-3xl font-medium tracking-[-.05em] text-slate-100 transition-colors group-hover:text-cyan-200 sm:text-5xl">{title}</h2><p className="mt-7 max-w-md text-sm leading-8 text-slate-400">{copy}</p><p className="mt-16 border-l border-emerald-300/60 pl-4 text-sm italic text-emerald-200/80">{detail}</p></article>;
}

function DetailCard({ title, copy, icon }: { title: string; copy: string; icon: ReactNode }) {
  return <div onMouseEnter={hoverHarmonic} className="rounded-2xl border border-white/[.1] bg-[#07101d] p-7 transition-colors hover:border-cyan-200/30"><span className="text-cyan-200">{icon}</span><h3 className="mt-16 text-xl text-slate-100">{title}</h3><p className="mt-3 text-sm leading-7 text-slate-500">{copy}</p></div>;
}

function DownloadPage() {
  const [email, setEmail] = useState('');
  const [joined, setJoined] = useState(false);
  const copyRef = useReveal<HTMLElement>();
  return <><section ref={copyRef} className="agora-reveal relative min-h-[78svh] overflow-hidden border-b border-white/[.07] px-5 pb-20 pt-40 sm:px-8 lg:px-12"><div className="absolute right-[12%] top-[28%] h-64 w-64 rounded-full border border-cyan-200/10 sm:h-[32rem] sm:w-[32rem]" /><div className="absolute right-[18%] top-[34%] h-48 w-48 rounded-full border border-emerald-200/10 sm:h-[24rem] sm:w-[24rem]" /><div className="relative mx-auto grid max-w-[1400px] gap-16 lg:grid-cols-[1fr_.7fr] lg:items-end"><div><SectionLabel number="early access">the first circle</SectionLabel><h1 className="max-w-5xl text-balance text-[clamp(3.7rem,10vw,9.5rem)] font-semibold leading-[.86] tracking-[-.09em] text-slate-100">The door is<br /><span className="text-emerald-300">almost</span><br />open.</h1></div><div className="max-w-sm"><p className="text-base leading-8 text-slate-400">We are inviting a small, curious group to help shape Agora before the lights come on. Leave a signal. We will send the coordinates.</p>{joined ? <div className="agora-glass mt-8 rounded-xl p-5 text-sm leading-7 text-emerald-200"><Check size={16} className="mr-2 inline" />You are on the list. Watch your inbox for a quiet signal.</div> : <form onSubmit={(event) => { event.preventDefault(); if (email.trim()) setJoined(true); }} className="mt-8 space-y-3"><label htmlFor="access-email" className="font-mono-agora text-[10px] uppercase tracking-[.2em] text-slate-500">your coordinates</label><div className="flex gap-2"><input id="access-email" data-testid="input-access-email" type="email" required value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@somewhere.com" className="min-w-0 flex-1 rounded-full border border-slate-700 bg-slate-950/70 px-4 py-3 text-sm text-slate-100 outline-none transition-colors placeholder:text-slate-600 focus:border-cyan-200/70" /><GlowButton type="submit" testId="button-request-access" className="shrink-0 px-4"><ArrowRight size={16} /></GlowButton></div><p className="font-mono-agora text-[9px] uppercase tracking-[.15em] text-slate-600">no password / no noise / just a first look</p></form>}</div></div></section>
    <section className="mx-auto max-w-[1400px] px-5 py-24 sm:px-8 sm:py-32 lg:px-12"><div className="grid gap-12 lg:grid-cols-[.7fr_1.3fr]"><div><SectionLabel number="the handoff">before you enter</SectionLabel><p className="max-w-xs text-sm leading-7 text-slate-500">A few things worth knowing about the place we are making.</p></div><div className="grid gap-0 border-t border-white/[.1]">{['Agora is intentionally small at the beginning.', 'Your feed will be chronological. That is the feature.', 'There will be nothing to buy and nothing to optimize.'].map((item, index) => <div key={item} className="flex gap-6 border-b border-white/[.1] py-6"><span className="font-mono-agora text-[10px] text-cyan-200/70">0{index + 1}</span><span className="text-lg tracking-[-.02em] text-slate-300">{item}</span></div>)}</div></div></section><Footer /></>;
}

function Footer() {
  return <footer className="border-t border-white/[.07] px-5 py-8 sm:px-8 lg:px-12"><div className="mx-auto flex max-w-[1400px] flex-col justify-between gap-5 font-mono-agora text-[9px] uppercase tracking-[.2em] text-slate-600 sm:flex-row"><span>Agora / a public square for people</span><span className="flex items-center gap-3"><Radio size={12} className="text-emerald-300" />signal stable</span><span>© 2026</span></div></footer>;
}

function Router() {
  return <SiteShell><ErrorBoundary><Switch><Route path="/" component={Home} /><Route path="/features" component={FeaturesPage} /><Route path="/download" component={DownloadPage} /><Route component={NotFound} /></Switch></ErrorBoundary></SiteShell>;
}

function App() {
  return <QueryClientProvider client={queryClient}><TooltipProvider><WouterRouter base={import.meta.env.BASE_URL.replace(/\/$/, '')}><Router /></WouterRouter><Toaster /></TooltipProvider></QueryClientProvider>;
}

export default App;