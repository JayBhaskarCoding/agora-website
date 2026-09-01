document.addEventListener("DOMContentLoaded", () => {
    // 1. Mouse Tracking Glow Effect for Bento Cards
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

    // 2. Dynamic Navbar Border Shadow on Scroll
    const nav = document.querySelector(".glass-nav");
    window.addEventListener("scroll", () => {
        if (window.scrollY > 30) {
            nav.classList.add("border-white/10", "shadow-2xl");
        } else {
            nav.classList.remove("border-white/10", "shadow-2xl");
        }
    });
});