/* Formulário de campanha: o campo "Nome do sistema" só aparece quando a
   pessoa escolhe "Sistema Próprio". Sem JavaScript ele fica sempre visível. */
(function () {
    var lista = document.querySelector("select[data-sistema-proprio]");
    var campo = document.querySelector('[data-campo="sistema_proprio"]');
    if (!lista || !campo) return;
    var entrada = campo.querySelector("input");

    function atualizar(focar) {
        var proprio = lista.value === lista.dataset.sistemaProprio;
        campo.hidden = !proprio;
        entrada.required = proprio;
        if (proprio && focar) entrada.focus();
    }

    lista.addEventListener("change", function () { atualizar(true); });
    atualizar(false);
})();
