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
    
    // Only initialize if the canvas exists and Three.js is loaded
    if (canvas && window.THREE) {
        const scene = new THREE.Scene();
        
        // Camera setup for deep perspective
        const camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.1, 1000);
        camera.position.z = 40;
        camera.position.y = 15;
        camera.lookAt(0, 0, 0);

        // WebGL Renderer with antialiasing
        const renderer = new THREE.WebGLRenderer({ canvas: canvas, alpha: true, antialias: true });
        renderer.setSize(window.innerWidth, window.innerHeight);
        renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));

        // Generate a Topographic Grid Geometry
        const particleCount = 2500;
        const geometry = new THREE.BufferGeometry();
        const positions = new Float32Array(particleCount * 3);
        const colors = new Float32Array(particleCount * 3);

        const colorBase = new THREE.Color('#3b82f6'); // Agora Blue
        const colorAlt = new THREE.Color('#10b981');  // Emerald

        const size = 120;
        const segments = Math.sqrt(particleCount);
        let i = 0;
        
        for (let x = 0; x < segments; x++) {
            for (let z = 0; z < segments; z++) {
                // Center the grid
                const px = (x / segments - 0.5) * size;
                const pz = (z / segments - 0.5) * size;
                
                // Initial mathematical height calculation
                const py = Math.sin(px * 0.2) * 2 + Math.cos(pz * 0.2) * 2;

                positions[i * 3] = px;
                positions[i * 3 + 1] = py;
                positions[i * 3 + 2] = pz;

                // Dynamically mix colors based on topographic height
                const mixedColor = colorBase.clone().lerp(colorAlt, (py + 4) / 8);
                colors[i * 3] = mixedColor.r;
                colors[i * 3 + 1] = mixedColor.g;
                colors[i * 3 + 2] = mixedColor.b;
                
                i++;
            }
        }

        geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
        geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));

        // Render as glowing data points
        const material = new THREE.PointsMaterial({
            size: 0.15,
            vertexColors: true,
            transparent: true,
            opacity: 0.6,
            blending: THREE.AdditiveBlending
        });

        const particles = new THREE.Points(geometry, material);
        scene.add(particles);

        // Interactive Spatial Data (Mouse Tracking)
        let mouseX = 0;
        let mouseY = 0;
        const windowHalfX = window.innerWidth / 2;
        const windowHalfY = window.innerHeight / 2;

        document.addEventListener('mousemove', (event) => {
            mouseX = (event.clientX - windowHalfX) * 0.001;
            mouseY = (event.clientY - windowHalfY) * 0.001;
        });

        const clock = new THREE.Clock();

        function animate() {
            requestAnimationFrame(animate);
            const elapsedTime = clock.getElapsedTime();

            // Real-time topographic wave recalculation
            const positions = particles.geometry.attributes.position.array;
            let index = 0;
            for (let x = 0; x < segments; x++) {
                for (let z = 0; z < segments; z++) {
                    const px = positions[index * 3];
                    const pz = positions[index * 3 + 2];
                    
                    // Complex sine/cosine interference pattern
                    positions[index * 3 + 1] = Math.sin(px * 0.15 + elapsedTime * 0.5) * 2.5 + 
                                               Math.cos(pz * 0.15 + elapsedTime * 0.4) * 2.5;
                    index++;
                }
            }
            particles.geometry.attributes.position.needsUpdate = true;

            // Subtle 3D tilt reacting to mouse position
            particles.rotation.x += 0.05 * (mouseY - particles.rotation.x);
            particles.rotation.y += 0.05 * (mouseX - particles.rotation.y);
            
            // Constant drift
            particles.rotation.y += 0.001;

            renderer.render(scene, camera);
        }

        animate();

        // Maintain structural integrity on screen resize
        window.addEventListener('resize', () => {
            camera.aspect = window.innerWidth / window.innerHeight;
            camera.updateProjectionMatrix();
            renderer.setSize(window.innerWidth, window.innerHeight);
        });
    }

    function animate() {
        requestAnimationFrame(animate);
        ctx.clearRect(0, 0, width, height);

        // Update and draw nodes
        for (let i = 0; i < particles.length; i++) {
            let p = particles[i];
            
            // Move nodes
            p.x += p.vx;
            p.y += p.vy;

            // Bounce off edges
            if (p.x < 0 || p.x > width) p.vx *= -1;
            if (p.y < 0 || p.y > height) p.vy *= -1;

            ctx.beginPath();
            ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2);
            ctx.fillStyle = 'rgba(148, 163, 184, 0.8)';
            ctx.fill();

            // Connect nodes using Euclidean distance
            for (let j = i + 1; j < particles.length; j++) {
                let p2 = particles[j];
                let dx = p.x - p2.x;
                let dy = p.y - p2.y;
                let distance = Math.sqrt(dx * dx + dy * dy);

                if (distance < 120) {
                    ctx.beginPath();
                    ctx.strokeStyle = `rgba(59, 130, 246, ${1 - distance / 120})`;
                    ctx.lineWidth = 0.5;
                    ctx.moveTo(p.x, p.y);
                    ctx.lineTo(p2.x, p2.y);
                    ctx.stroke();
                }
            }
        }
    }

    window.addEventListener('resize', init);
    init();
    animate();

// 4. Anti-Noise Experiential Scroll Trigger
    const noiseOverlay = document.getElementById('noise-overlay');
    if (noiseOverlay) {
        // Lock the background from scrolling while the noise wall is up
        document.body.style.overflow = 'hidden';

        const triggerShatter = () => {
            // Fire the wipe effect
            noiseOverlay.classList.add('shatter');
            
            // Unlock the background so the user can scroll the actual website
            document.body.style.overflow = '';

            // Remove the overlay from the DOM after the animation completes
            setTimeout(() => {
                if (noiseOverlay.parentNode) {
                    noiseOverlay.parentNode.removeChild(noiseOverlay);
                }
            }, 1500);
        };

        // Trigger the shatter on ANY user interaction (mouse scroll, mobile swipe, or click)
        window.addEventListener('wheel', triggerShatter, { once: true });
        window.addEventListener('touchstart', triggerShatter, { once: true });
        window.addEventListener('click', triggerShatter, { once: true });
    }

});