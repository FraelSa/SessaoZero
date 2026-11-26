/* Indicador de força da senha (partials/_forca_senha.html).

   Tamanho e "só números" são conferidos aqui mesmo, a cada tecla. Se a senha é
   "muito comum" depende da lista do Django, que fica no servidor: o script
   pergunta à rota verificar_senha depois de uma pausa na digitação. A barra só
   fica verde quando o servidor confirma as três regras, as mesmas que ele usa
   ao receber o formulário. */
(function () {
    var caixa = document.querySelector("[data-forca-senha]");
    if (!caixa) return;
    var form = caixa.closest("form");
    var senha = form && form.querySelector("[data-senha-nova]");
    if (!senha) return;
    var confirmar = form.querySelector("[data-senha-confirmar]");
    var estado = caixa.querySelector("[data-estado]");
    var token = form.querySelector("[name=csrfmiddlewaretoken]");
    var itens = {};
    caixa.querySelectorAll("[data-criterio]").forEach(function (li) {
        itens[li.dataset.criterio] = li;
    });

    var MIN = 8, MAX = 128, PAUSA_MS = 350;
    var conferida = null;   // senha que o servidor já avaliou
    var naoComum = null;    // resposta do servidor para ela (null = sem resposta)
    var falhou = false;
    var espera = null;

    if (!confirmar) itens.confere.hidden = true;
    var descritas = (senha.getAttribute("aria-describedby") || "").split(" ").filter(Boolean);
    descritas.push(caixa.id);
    senha.setAttribute("aria-describedby", descritas.join(" "));
    caixa.hidden = false;

    function marcar(nome, ok) {
        itens[nome].dataset.ok = ok === null ? "" : (ok ? "sim" : "nao");
    }

    function atualizar() {
        var valor = senha.value;
        var vazia = valor.length === 0;
        var tamanho = valor.length >= MIN && valor.length <= MAX;
        var letras = !/^\d+$/.test(valor);
        var comum = (!vazia && conferida === valor) ? naoComum : null;

        marcar("tamanho", vazia ? null : tamanho);
        marcar("letras", vazia ? null : letras);
        marcar("comum", comum);
        if (confirmar) {
            marcar("confere", vazia || !confirmar.value ? null : confirmar.value === valor);
        }

        var nivel = vazia ? 0 : [tamanho, letras, comum === true].filter(Boolean).length;
        var aceitavel = nivel === 3;
        caixa.dataset.nivel = String(nivel);
        caixa.dataset.aceitavel = aceitavel ? "sim" : "nao";

        var texto;
        if (vazia) texto = "Digite uma senha.";
        else if (aceitavel && confirmar && confirmar.value && confirmar.value !== valor) texto = "Senha aceitável, mas a confirmação está diferente.";
        else if (aceitavel) texto = "Senha aceitável.";
        else if (tamanho && letras && comum === null) texto = falhou ? "Não deu para conferir agora; o site confere ao enviar." : "Conferindo a senha…";
        else texto = "A senha ainda não atende a todas as regras.";
        if (estado.textContent !== texto) estado.textContent = texto;
    }

    function conferirNoServidor() {
        var valor = senha.value;
        if (!valor || valor === conferida) return;
        var dados = new FormData();
        dados.append("senha", valor);
        fetch(caixa.dataset.url, {
            method: "POST",
            body: dados,
            credentials: "same-origin",
            headers: { "X-CSRFToken": token ? token.value : "" }
        })
            .then(function (resposta) {
                if (!resposta.ok) throw new Error(resposta.status);
                return resposta.json();
            })
            .then(function (criterios) {
                falhou = false;
                if (senha.value !== valor) return; // a pessoa já digitou outra coisa
                conferida = valor;
                naoComum = criterios.comum === true;
                atualizar();
            })
            .catch(function () {
                falhou = true;
                atualizar();
            });
    }

    senha.addEventListener("input", function () {
        atualizar();
        clearTimeout(espera);
        espera = setTimeout(conferirNoServidor, PAUSA_MS);
    });
    if (confirmar) confirmar.addEventListener("input", atualizar);

    // Volta do servidor com erro: o navegador pode manter a senha digitada.
    atualizar();
    if (senha.value) conferirNoServidor();
})();
