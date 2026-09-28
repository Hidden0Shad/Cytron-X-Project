const schoolMenuToggle = document.querySelector(".school-mobile-toggle");
const schoolMenu = document.querySelector(".school-menu");

schoolMenuToggle?.addEventListener("click", () => {
  const isOpen = schoolMenu.classList.toggle("open");
  schoolMenuToggle.setAttribute("aria-expanded", String(isOpen));
});

document.querySelectorAll("[data-school-form]").forEach((form) => {
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const toast = document.querySelector(".school-toast");
    if (toast) {
      toast.textContent =
        "Thank you. The school office will be in touch shortly.";
      toast.classList.add("show");
      window.setTimeout(() => toast.classList.remove("show"), 3500);
    }
    form.reset();
  });
});
