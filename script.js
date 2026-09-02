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

    // 3. Dynamic Node Network Background
    const canvas = document.getElementById('agora-network');
    if (!canvas) return;
    
    const ctx = canvas.getContext('2d');
    let width, height, particles;

    function init() {
        width = canvas.width = window.innerWidth;
        height = canvas.height = window.innerHeight;
        particles = [];
        
        // Create 80 nodes based on screen size
        const particleCount = Math.floor(width * height / 15000);
        
        for (let i = 0; i < particleCount; i++) {
            particles.push({
                x: Math.random() * width,
                y: Math.random() * height,
                vx: (Math.random() - 0.5) * 0.5, // Velocity X
                vy: (Math.random() - 0.5) * 0.5, // Velocity Y
                radius: Math.random() * 1.5 + 0.5
            });
        }
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
});