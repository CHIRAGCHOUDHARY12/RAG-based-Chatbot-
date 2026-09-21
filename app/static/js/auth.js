(function () {
  "use strict";

  const toggle = document.getElementById("toggle-password");
  const password = document.getElementById("password");

  if (toggle && password) {
    toggle.addEventListener("click", () => {
      const isHidden = password.type === "password";
      password.type = isHidden ? "text" : "password";
      toggle.textContent = isHidden ? "Hide" : "Show";
      toggle.setAttribute("aria-label", isHidden ? "Hide password" : "Show password");
    });
  }

  // Register page only: live checklist and confirm-password hint.
  // These are hints; the server still validates everything.
  const rules = document.getElementById("pw-rules");
  if (rules && password) {
    const checks = {
      length: (v) => v.length >= 8,
      case: (v) => /[a-z]/.test(v) && /[A-Z]/.test(v),
      number: (v) => /\d/.test(v),
    };
    const update = () => {
      rules.querySelectorAll(".pw-rule").forEach((el) => {
        const test = checks[el.dataset.rule];
        el.classList.toggle("is-met", Boolean(test && test(password.value)));
      });
    };
    password.addEventListener("input", update);
    update();
  }

  const confirm = document.getElementById("confirm_password");
  const confirmHint = document.getElementById("confirm-hint");
  if (confirm && confirmHint && password) {
    const compare = () => {
      const mismatch = confirm.value.length > 0 && confirm.value !== password.value;
      confirmHint.hidden = !mismatch;
      confirm.setAttribute("aria-invalid", mismatch ? "true" : "false");
    };
    confirm.addEventListener("input", compare);
    password.addEventListener("input", compare);
  }

  const form = document.querySelector(".auth-form");
  const submitBtn = document.getElementById("submit-btn");
  if (form && submitBtn) {
    form.addEventListener("submit", () => {
      submitBtn.classList.add("is-loading");
      submitBtn.disabled = true;
    });
  }
})();
