window.desenharGraficoOficina = function (totais) {
  const canvas = document.getElementById('grafico-oficina');
  if (!canvas) return;
  const labels = ['Na oficina', 'Disponíveis no Pátio', 'Entregues ao cliente'];
  const valores = [totais.final, totais.patio, totais.entregas];
  const cores = ['#5eb5ff', '#45ddb0', '#b59aff'];
  if (totais.outras) {
    labels.push('Outras saídas'); valores.push(totais.outras); cores.push('#71879a');
  }
  const rotulos = {
    id: 'quantidadesNasBarras',
    afterDatasetsDraw(chart) {
      const {ctx} = chart;
      ctx.save(); ctx.font = '700 18px sans-serif'; ctx.textBaseline = 'middle';
      chart.getDatasetMeta(0).data.forEach((barra, i) => {
        ctx.fillStyle = cores[i]; ctx.textAlign = 'left';
        ctx.fillText(String(valores[i]), barra.x + 12, barra.y);
      });
      ctx.restore();
    }
  };
  new Chart(canvas, {
    type: 'bar',
    data: {labels, datasets: [{data: valores, backgroundColor: cores,
      borderRadius: 8, borderSkipped: false, maxBarThickness: 36,
      categoryPercentage: .7, barPercentage: .85}]},
    plugins: [rotulos],
    options: {
      indexAxis: 'y', responsive: true, maintainAspectRatio: false,
      layout: {padding: {right: 40, top: 6, bottom: 6}},
      plugins: {
        legend: {display: false},
        tooltip: {backgroundColor: '#102431', titleColor: '#f0f7fc',
          bodyColor: '#c5d7e5', borderColor: '#294659', borderWidth: 1,
          padding: 14, cornerRadius: 10, displayColors: false,
          callbacks: {label: context => context.raw + (context.raw === 1 ? ' moto' : ' motos')}}
      },
      scales: {
        x: {beginAtZero: true, suggestedMax: Math.max(1, ...valores) * 1.15,
          border: {display: false}, grid: {color: 'rgba(137,169,192,.1)', drawTicks: false},
          ticks: {precision: 0, maxTicksLimit: 6, color: '#8ea9bc', padding: 10}},
        y: {border: {display: false}, grid: {display: false},
          ticks: {color: '#d9e8f2', font: {size: 12, weight: '600'}, padding: 12}}
      }
    }
  });
};
