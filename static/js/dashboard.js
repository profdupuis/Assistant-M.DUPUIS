// static/js/dashboard.js

document.addEventListener("DOMContentLoaded", function () {
    const sel = document.getElementById("studentSelect");
    if (sel) {
      sel.addEventListener("change", function () {
        const targetId = this.value;
        if (targetId) {
          window.location.href = "/dashboard/eleve/" + targetId;
        }
      });
    }
  });
  