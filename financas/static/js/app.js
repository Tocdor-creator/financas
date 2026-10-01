(function () {
  'use strict';

  var raiz = document.documentElement;

  function valoresOcultos() {
    return raiz.classList.contains('valores-ocultos');
  }

  function formatarBRL(valor, casas) {
    var digitos = casas === undefined ? 2 : casas;
    return valor.toLocaleString('pt-BR', {
      style: 'currency', currency: 'BRL', minimumFractionDigits: digitos, maximumFractionDigits: digitos,
    });
  }

  // Botão de olho: esconde os valores e lembra a escolha neste aparelho.
  var botaoValores = document.getElementById('alternar-valores');
  if (botaoValores) {
    botaoValores.setAttribute('aria-pressed', String(valoresOcultos()));
    botaoValores.addEventListener('click', function () {
      var ocultos = raiz.classList.toggle('valores-ocultos');
      botaoValores.setAttribute('aria-pressed', String(ocultos));
      try { localStorage.setItem('valoresOcultos', ocultos ? '1' : '0'); } catch (e) { /* armazenamento indisponível */ }
    });
  }

  // Formulários com data-confirmar pedem confirmação antes de enviar.
  document.querySelectorAll('form[data-confirmar]').forEach(function (form) {
    form.addEventListener('submit', function (evento) {
      if (!window.confirm(form.dataset.confirmar)) evento.preventDefault();
    });
  });

  // Links como /contas#nova abrem o bloco recolhível correspondente.
  if (location.hash) {
    var alvo = document.getElementById(location.hash.slice(1));
    if (alvo && alvo.tagName === 'DETAILS') alvo.open = true;
  }

  // Gráficos: <canvas data-grafico='{"tipo", "rotulos", "series": [{rotulo, dados, cor, tracejado}]}'>
  if (window.Chart) {
    var estilo = getComputedStyle(raiz);
    var cores = {
      positivo: estilo.getPropertyValue('--positivo').trim(),
      negativo: estilo.getPropertyValue('--negativo').trim(),
    };

    document.querySelectorAll('canvas[data-grafico]').forEach(function (canvas) {
      var config = JSON.parse(canvas.dataset.grafico);
      var linha = config.tipo === 'line';

      new window.Chart(canvas, {
        type: config.tipo,
        data: {
          labels: config.rotulos,
          datasets: config.series.map(function (serie) {
            var cor = cores[serie.cor] || serie.cor;
            return {
              label: serie.rotulo,
              data: serie.dados,
              backgroundColor: cor,
              borderColor: cor,
              borderDash: serie.tracejado ? [6, 4] : [],
              borderRadius: linha ? 0 : 4,
              tension: 0.3,
              pointRadius: linha ? 3 : 0,
            };
          }),
        },
        options: {
          maintainAspectRatio: false,
          plugins: {
            legend: { position: 'bottom', labels: { usePointStyle: true, boxWidth: 8 } },
            tooltip: {
              callbacks: {
                label: function (item) {
                  return item.dataset.label + ': ' + (valoresOcultos() ? 'R$ •••' : formatarBRL(item.parsed.y));
                },
              },
            },
          },
          scales: {
            x: { grid: { display: false } },
            y: {
              beginAtZero: true,
              ticks: {
                callback: function (valor) { return valoresOcultos() ? '' : formatarBRL(valor, 0); },
              },
            },
          },
        },
      });
    });
  }
})();
