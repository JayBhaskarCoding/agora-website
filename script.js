document.addEventListener("DOMContentLoaded", () => {
    // 1. Scroll Reveal Animation
    const revealElements = document.querySelectorAll(".reveal");
    const revealObserver = new IntersectionObserver((entries, observer) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add("active");
                observer.unobserve(entry.target); 
            }
        });
    }, {
        threshold: 0.1,
        rootMargin: "0px 0px -50px 0px" 
    });

    revealElements.forEach(el => revealObserver.observe(el));

    // 2. Mouse Tracking Glow Effect for Bento Cards
    const cards = document.querySelectorAll(".bento-card");
    const grid = document.getElementById("bento-grid");

    if (grid && cards.length > 0) {
        grid.addEventListener("mousemove", (e) => {
            cards.forEach(card => {
                const rect = card.getBoundingClientRect();
                // Calculate mouse position relative to the card
                const x = e.clientX - rect.left;
                const y = e.clientY - rect.top;
                
                // Pass coordinates to CSS variables
                card.style.setProperty("--mouse-x", `${x}px`);
                card.style.setProperty("--mouse-y", `${y}px`);
            });
        });
    }
});