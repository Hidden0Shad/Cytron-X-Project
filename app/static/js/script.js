const menuToggle = document.querySelector('.menu-toggle');
const mainNav = document.querySelector('.main-nav');

document.title = document.title.replace(/ImmuniWeb/g, 'Cybertron X');
document.querySelectorAll('.immuni-logo strong').forEach((logo) => {
    logo.textContent = 'Cybertron X';
});
document.querySelectorAll('.immuni-footer span').forEach((footerBrand) => {
    footerBrand.textContent = 'Cybertron X AI for Application Security';
});
document.querySelectorAll('.form-panel h2').forEach((heading) => {
    heading.textContent = heading.textContent.replace(/ImmuniWeb/g, 'Cybertron X');
});
document.querySelectorAll('.form-intro .hero-copy').forEach((copy) => {
    copy.textContent = copy.textContent.replace(/ImmuniWeb/g, 'Cybertron X');
});

if (menuToggle && mainNav) {
    menuToggle.addEventListener('click', () => {
        const isOpen = mainNav.classList.toggle('open');
        menuToggle.setAttribute('aria-expanded', String(isOpen));
    });
}

document.querySelectorAll('[data-demo-form]').forEach((form) => {
    form.addEventListener('submit', (event) => {
        event.preventDefault();
        const toast = document.querySelector('.toast');
        if (toast) {
            toast.textContent = 'Thanks. We will be in touch shortly.';
            toast.classList.add('show');
            window.setTimeout(() => toast.classList.remove('show'), 3500);
        }
        form.reset();
    });
});

const scanForm = document.querySelector('[data-scan-form]');
if (scanForm) {
    scanForm.addEventListener('submit', (event) => {
        event.preventDefault();
        const input = scanForm.querySelector('input[type="url"]');
        const toast = document.querySelector('.toast');
        if (toast) {
            toast.textContent = `Security test queued for ${input.value}`;
            toast.classList.add('show');
            window.setTimeout(() => toast.classList.remove('show'), 3500);
        }
    });
}
