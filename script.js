const revealElements = document.querySelectorAll('.reveal');
const predictForm = document.getElementById('predict-form');
const output = document.getElementById('prediction-output');

function runReveal() {
  revealElements.forEach((el) => {
    if (el.getBoundingClientRect().top < window.innerHeight * 0.9) {
      el.classList.add('visible');
    }
  });
}

function pseudoScore(seed) {
  let hash = 0;
  for (let i = 0; i < seed.length; i += 1) {
    hash = (hash * 31 + seed.charCodeAt(i)) % 100000;
  }
  return hash;
}

predictForm.addEventListener('submit', (event) => {
  event.preventDefault();
  const ticker = document.getElementById('ticker').value.trim().toUpperCase();
  const horizon = document.getElementById('horizon').value;

  const score = pseudoScore(`${ticker}-${horizon}`);
  const confidence = 55 + (score % 40);
  const change = ((score % 1600) / 100) - 6;
  const trendUp = change >= 0;

  output.innerHTML = `
    <h3>Resultado da IA: ${ticker}</h3>
    <p class="${trendUp ? 'result-up' : 'result-down'}">
      Tendência ${trendUp ? 'de alta' : 'de baixa'} em ${horizon} dias (${change.toFixed(2)}%)
    </p>
    <p><strong>Confiança do modelo:</strong> ${confidence}%</p>
    <p class="muted"><strong>Sugestão de risco:</strong> ${confidence > 75 ? 'moderado' : 'conservador'} com stop técnico dinâmico.</p>
    <p class="muted">*Simulação demonstrativa para experiência do site.</p>
  `;
});

document.getElementById('year').textContent = new Date().getFullYear();
window.addEventListener('scroll', runReveal, { passive: true });
window.addEventListener('load', runReveal);
