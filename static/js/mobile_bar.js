document.querySelector('.matiere-select').addEventListener('change', e => {
  const map={NSI : '💻',MATHS:'📘',SVT:'🧬','':'📚'};
  document.getElementById('matiere-emoji').textContent = map[e.target.value]||'📚';
});