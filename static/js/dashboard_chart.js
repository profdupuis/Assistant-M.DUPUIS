// static/js/dashboard_chart.js

document.addEventListener("DOMContentLoaded", function () {
    const canvas = document.getElementById('graph-evol-scenario');
    if (!canvas) return;
  
    const labels = JSON.parse(canvas.getAttribute("data-labels"));
    const data = JSON.parse(canvas.getAttribute("data-values"));
  
    const evolData = {
      labels: labels,
      datasets: [{
        label: "% de réussite",
        data: data,
        borderColor: "green",
        backgroundColor: "rgba(0,128,0,0.2)",
        fill: true,
        tension: 0.3
      }]
    };
  
    new Chart(canvas, {
      type: 'line',
      data: evolData,
      options: {
        scales: {
          y: { beginAtZero: true, max: 100 }
        }
      }
    });
  });
  