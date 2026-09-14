// Goal Pacer, pareamento de um aparelho da rede local. Os textos já vêm na página (servidor, copy.pt-BR.md).
(function () {
  "use strict";
  document.addEventListener("DOMContentLoaded", function () {
    var form = document.getElementById("form-parear");
    var campo = document.getElementById("codigo");
    var erro = document.getElementById("erro");
    campo.focus();
    form.addEventListener("submit", function (ev) {
      ev.preventDefault();
      erro.hidden = true;
      var codigo = campo.value.replace(/\D/g, "");
      fetch("/api/parear", {
        method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ codigo: codigo })
      }).then(function (resp) {
        return resp.json().catch(function () { return { ok: false, erro: resp.statusText }; }).then(function (dados) {
          if (resp.ok && dados.ok) { window.location.replace("/"); return; }
          erro.textContent = dados.erro || resp.statusText;
          erro.hidden = false;
          campo.select();
        });
      }).catch(function (e) {
        erro.textContent = e.message;
        erro.hidden = false;
      });
    });
  });
})();
