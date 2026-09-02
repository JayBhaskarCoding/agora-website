document.addEventListener("DOMContentLoaded", () => {
    // 1. Interactive Mouse-Tracking Glow for Cards
    const cards = document.querySelectorAll(".bento-card");
    const grids = document.querySelectorAll("#bento-grid");

    grids.forEach(grid => {
        grid.addEventListener("mousemove", (e) => {
            cards.forEach(card => {
                const rect = card.getBoundingClientRect();
                const x = e.clientX - rect.left;
                const y = e.clientY - rect.top;
                card.style.setProperty("--mouse-x", `${x}px`);
                card.style.setProperty("--mouse-y", `${y}px`);
            });
        });
    });

    // 2. Dynamic Navbar Border Shadow
    const nav = document.querySelector(".glass-nav");
    if (nav) {
        window.addEventListener("scroll", () => {
            if (window.scrollY > 30) {
                nav.classList.add("border-white/10", "shadow-2xl");
            } else {
                nav.classList.remove("border-white/10", "shadow-2xl");
            }
        });
    }

    // 3. Mathematical Spatial Construct (Three.js Topographic Matrix)
    const canvas = document.getElementById('agora-network');
    
    if (canvas && window.THREE) {
        const scene = new THREE.Scene();
        
        const camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.1, 1000);
        camera.position.z = 40;
        camera.position.y = 15;
        camera.lookAt(0, 0, 0);

        const renderer = new THREE.WebGLRenderer({ canvas: canvas, alpha: true, antialias: true });
        renderer.setSize(window.innerWidth, window.innerHeight);
        renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));

        const particleCount = 2500;
        const geometry = new THREE.BufferGeometry();
        const positions = new Float32Array(particleCount * 3);
        const colors = new Float32Array(particleCount * 3);

        const colorBase = new THREE.Color('#3b82f6'); 
        const colorAlt = new THREE.Color('#10b981');  

        const size = 120;
        const segments = Math.sqrt(particleCount);
        let i = 0;
        
        for (let x = 0; x < segments; x++) {
            for (let z = 0; z < segments; z++) {
                const px = (x / segments - 0.5) * size;
                const pz = (z / segments - 0.5) * size;
                
                const py = Math.sin(px * 0.2) * 2 + Math.cos(pz * 0.2) * 2;

                positions[i * 3] = px;
                positions[i * 3 + 1] = py;
                positions[i * 3 + 2] = pz;

                const mixedColor = colorBase.clone().lerp(colorAlt, (py + 4) / 8);
                colors[i * 3] = mixedColor.r;
                colors[i * 3 + 1] = mixedColor.g;
                colors[i * 3 + 2] = mixedColor.b;
                
                i++;
            }
        }

        geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
        geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));

        const material = new THREE.PointsMaterial({
            size: 0.15,
            vertexColors: true,
            transparent: true,
            opacity: 0.6,
            blending: THREE.AdditiveBlending
        });

        const particles = new THREE.Points(geometry, material);
        scene.add(particles);

        let mouseX = 0;
        let mouseY = 0;
        const windowHalfX = window.innerWidth / 2;
        const windowHalfY = window.innerHeight / 2;

        document.addEventListener('mousemove', (event) => {
            mouseX = (event.clientX - windowHalfX) * 0.001;
            mouseY = (event.clientY - windowHalfY) * 0.001;
        });

        const clock = new THREE.Clock();

        function animateThreeJS() {
            requestAnimationFrame(animateThreeJS);
            const elapsedTime = clock.getElapsedTime();

            const positions = particles.geometry.attributes.position.array;
            let index = 0;
            for (let x = 0; x < segments; x++) {
                for (let z = 0; z < segments; z++) {
                    const px = positions[index * 3];
                    const pz = positions[index * 3 + 2];
                    
                    positions[index * 3 + 1] = Math.sin(px * 0.15 + elapsedTime * 0.5) * 2.5 + 
                                               Math.cos(pz * 0.15 + elapsedTime * 0.4) * 2.5;
                    index++;
                }
            }
            particles.geometry.attributes.position.needsUpdate = true;

            particles.rotation.x += 0.05 * (mouseY - particles.rotation.x);
            particles.rotation.y += 0.05 * (mouseX - particles.rotation.y);
            particles.rotation.y += 0.001;

            renderer.render(scene, camera);
        }

        animateThreeJS();

        window.addEventListener('resize', () => {
            camera.aspect = window.innerWidth / window.innerHeight;
            camera.updateProjectionMatrix();
            renderer.setSize(window.innerWidth, window.innerHeight);
        });
    }

    // 4. Interactive Anti-Noise Scroll Scrubbing
    const noiseOverlay = document.getElementById('noise-overlay');
    if (noiseOverlay) {
        document.body.style.overflow = '';
        noiseOverlay.style.transition = 'none';

        window.addEventListener('scroll', () => {
            const scrollY = window.scrollY;
            const shatterDistance = 400; 
            
            if (scrollY <= shatterDistance) {
                const progress = scrollY / shatterDistance;
                const scale = 1 + (progress * 0.4);      
                const opacity = 1 - (progress * 1.2);    
                const blur = progress * 30;              
                const yOffset = -(progress * 15);        
                
                noiseOverlay.style.transform = `scale(${scale}) translateY(${yOffset}%)`;
                noiseOverlay.style.opacity = opacity > 0 ? opacity : 0;
                noiseOverlay.style.filter = `blur(${blur}px)`;
                
                if (opacity > 0) {
                    noiseOverlay.style.pointerEvents = 'auto';
                    noiseOverlay.style.visibility = 'visible';
                } else {
                    noiseOverlay.style.pointerEvents = 'none';
                    noiseOverlay.style.visibility = 'hidden';
                }
            } else {
                noiseOverlay.style.opacity = 0;
                noiseOverlay.style.pointerEvents = 'none';
                noiseOverlay.style.visibility = 'hidden';
            }
        });
    }
});