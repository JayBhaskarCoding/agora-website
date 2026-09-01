document.addEventListener("DOMContentLoaded", () => {
    // 1. Scroll Reveal Animation Logic
    const revealElements = document.querySelectorAll(".reveal");

    const revealObserver = new IntersectionObserver((entries, observer) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add("active");
                // Optional: Stop observing once revealed so it doesn't animate out
                observer.unobserve(entry.target); 
            }
        });
    }, {
        root: null,
        threshold: 0.15, // Trigger when 15% of the element is visible
        rootMargin: "0px 0px -50px 0px" 
    });

    revealElements.forEach(el => revealObserver.observe(el));

    // 2. Dynamic Navbar Shadow on Scroll
    const nav = document.querySelector(".glass-nav");
    window.addEventListener("scroll", () => {
        if (window.scrollY > 50) {
            nav.classList.add("shadow-lg");
        } else {
            nav.classList.remove("shadow-lg");
        }
    });
});